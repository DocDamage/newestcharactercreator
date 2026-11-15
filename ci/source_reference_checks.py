"""Actual saved-master, rights, cancellation and concurrent-save guards."""
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
import json
import os
import shutil
import subprocess
import time

from ci.regional_sources import require, digest, expected
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.storage import ProjectStore
from ucc.jobs.project_animation_references import detach_catalog_reference
from ucc.jobs.reference_hand_revision import apply_referenced_hand_revision
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError


def clone(source: ProjectStore, root: Path) -> ProjectStore:
    root.mkdir(exist_ok=False)
    for role in ('master', 'parts', 'expressions', 'animations'):
        path = source.root/role
        if path.exists():
            require(not path.is_symlink(), 'Reference fixture source is redirected')
            shutil.copytree(path, root/role)
    store = ProjectStore(root)
    store.save(replace(source.load(), revision=0))
    return store


def children() -> list[tuple[int, str]]:
    """Read only this host's immediate Blender children; never scan assets."""
    if os.name == 'nt':
        query = ("Get-CimInstance Win32_Process -Filter \"Name='blender.exe' AND ParentProcessId="
                 +str(os.getpid())+"\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
        text = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                                        '-Command', query], timeout=10).decode('utf-8').strip()
        records = json.loads(text) if text else []
        if isinstance(records, dict): records = [records]
        return [(row['ProcessId'], row['CommandLine']) for row in records or []]
    text = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,args='], text=True, timeout=10)
    found = []
    for line in text.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[1] == str(os.getpid()) and '--background' in fields[2]:
            found.append((int(fields[0]), fields[2]))
    return found


def transaction_guards(source: ProjectStore, database: Path, identity: str, common: dict,
                         root: Path, faults: Path) -> dict:
    results = {}
    policy = clone(source, root/'NoAI-binding')
    clip = policy.load().animations[0]
    from hashlib import sha256
    binding = policy.root/'animations/references'/(sha256(clip.encode()).hexdigest()+'.json')
    data = json.loads(binding.read_text(encoding='utf-8')); data['license']['no_ai'] = False
    binding.write_text(json.dumps(data, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
    before = policy.file.read_bytes()
    try:
        apply_referenced_hand_revision(policy, database, manifest_sha256=identity, selection='longer',
                                       **common, **expected(policy.load()))
    except AssetPolicyError: pass
    else: raise RuntimeError('Actual coherent NoAI binding change gained editing permission')
    require(policy.file.read_bytes() == before and not (policy.root/'.ucc-jobs').exists(),
            'Policy rejection changed the active project or launched workers')
    results['NoAI_binding'] = True
    for kind, message in [('assigned_action', 'contains existing Actions'),
                          ('tiny_pose', 'exact identity'),
                          ('unregistered_neutral', 'no registered revision receipt')]:
        store = clone(source, root/kind); project = store.load()
        stage_unverified_master(store, faults/(kind+'.blend'), authorized_source_root=faults,
            expected_project=project, expected_revision=project.revision)
        before = store.file.read_bytes(); current = store.load(); master = store.root/current.master_blend
        sha = digest(master)
        try:
            if kind == 'unregistered_neutral':
                apply_referenced_hand_revision(store, database, manifest_sha256=identity, selection='longer',
                                               **common, **expected(current))
            else:
                options = {key: value for key, value in common.items() if key != 'mpfb_data_dir'}
                detach_catalog_reference(store, clip, **options, **expected(current))
        except (ProjectStorageError, WorkerFailure) as error:
            require(message in str(error), 'Wrong actual reference guard failure: '+str(error))
        else: raise RuntimeError('Actual saved fault was accepted: '+kind)
        require(store.file.read_bytes() == before and digest(master) == sha,
                'Saved-fault rejection changed its active project/master')
        if kind == 'unregistered_neutral':
            operations = []
            for request in (store.root/'.ucc-jobs').glob('*/request.json'):
                reply = json.loads((request.parent/'result.json').read_text(encoding='utf-8'))
                require(reply['status'] == 'ok', 'Foreign neutral observation did not actually pass')
                operations.append(json.loads(request.read_text(encoding='utf-8'))['operation'])
            require(operations.count('inspect_fbx_animation') == 2 and
                    operations.count('inspect_mpfb_neutral_master') == 2 and len(operations) == 4,
                    'Foreign master must fail provenance after genuine neutral/source observations')
        results[kind] = True
    for mode in ('cancel_live_neutral', 'external_revision'):
        store = clone(source, root/mode); project = store.load(); before = store.file.read_bytes()
        master_sha = digest(store.root/project.master_blend); history = store.list_backups()
        cancel = Event(); observations = []; errors = []
        def observe():
            try:
                deadline = time.monotonic()+45
                while time.monotonic() < deadline:
                    requests = [p for p in (store.root/'.ucc-jobs').glob('*/request.json')
                        if json.loads(p.read_text(encoding='utf-8'))['operation'] == 'inspect_mpfb_neutral_master']
                    for pid, command in children():
                        if any(str(p.resolve()).casefold() in command.casefold() for p in requests):
                            observations.append(pid)
                            if mode == 'cancel_live_neutral': cancel.set()
                            else:
                                store.save(replace(project, name='Actual concurrent metadata save',
                                    revision=project.revision+1), expected_revision=project.revision)
                            return
                    time.sleep(.05)
                raise RuntimeError('No live neutral worker was observed')
            except BaseException as error:
                errors.append(str(error)); cancel.set()
        observer = Thread(target=observe); observer.start()
        try:
            apply_referenced_hand_revision(store, database, manifest_sha256=identity, selection='longer',
                                           cancel=cancel, **common, **expected(project))
        except (WorkerFailure, ProjectStorageError, ProjectConflict) as error:
            require(('cancel' if mode == 'cancel_live_neutral' else 'project') in str(error).lower(),
                    'Wrong actual concurrent-operation failure: '+str(error))
        else: raise RuntimeError('Live cancellation or concurrent save was overwritten')
        finally: observer.join(timeout=15)
        require(not observer.is_alive() and not errors and len(observations) == 1,
                'Actual worker observation failed: '+str(errors))
        require(digest(store.root/project.master_blend) == master_sha, 'Original master changed')
        if mode == 'cancel_live_neutral':
            require(store.file.read_bytes() == before and store.list_backups() == history,
                    'Cancellation changed project/history')
            require(observations[0] not in [pid for pid, _ in children()], 'Cancelled Blender is still live')
        else:
            require(store.load() == replace(project, name='Actual concurrent metadata save',
                    revision=project.revision+1), 'Concurrent saved revision was not preserved')
        results[mode] = True
    return results
