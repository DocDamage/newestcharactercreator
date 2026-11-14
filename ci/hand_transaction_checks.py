"""Real hand cancellation, timeout, conflict and unknown-master adoption checks."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from threading import Event,Thread
import time

from ucc.core.errors import ProjectConflict,ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.jobs.hand_revision import apply_hand_revision
from ucc.jobs.runner import WorkerFailure


def require(value,message):
    if not value:raise RuntimeError(message)


def apply(store,identity,common,**extra):
    current=store.load()
    return apply_hand_revision(store,manifest_sha256=identity,selection='longer',
        expected_project_id=current.project_id,expected_revision=current.revision,
        expected_master_blend=current.master_blend,**common,**extra)


def after_stage(store,action):
    jobs=store.root/'.ucc-jobs';old={p.name for p in jobs.iterdir()} if jobs.exists() else set()
    stopped=Event();triggered=[];errors=[]
    def watch():
        while not stopped.wait(.02):
            for path in jobs.glob('*/result.json'):
                if path.parent.name in old:continue
                try:
                    request=json.loads((path.parent/'request.json').read_text())
                    result=json.loads(path.read_text())
                    if request['operation']=='stage_mpfb_hand_revision' and result['status']=='ok':
                        action();triggered.append(True);return
                except (json.JSONDecodeError,FileNotFoundError):continue
                except Exception as error:errors.append(str(error));return
    thread=Thread(target=watch,daemon=True);thread.start()
    return stopped,thread,triggered,errors


def verify_transactions(store,identity,common,shorter_result,out):
    baseline=store.file.read_bytes();current=store.load();master=store.root/current.master_blend
    master_sha=sha256(master.read_bytes()).hexdigest()
    cancel=Event();cancel.set()
    try:apply(store,identity,common,cancel=cancel)
    except ProjectStorageError:pass
    else:raise RuntimeError('Pre-cancelled hand revision was accepted')
    require(store.file.read_bytes()==baseline,'Pre-cancel changed project')
    cancel=Event();stopped,thread,triggered,errors=after_stage(store,cancel.set)
    try:
        try:apply(store,identity,common,cancel=cancel)
        except (WorkerFailure,ProjectStorageError) as error:
            require('cancel' in str(error).lower(),'Post-stage cancel failed for another reason')
        else:raise RuntimeError('Post-stage hand cancellation published a result')
    finally:stopped.set();thread.join(3)
    require(triggered and not errors and store.file.read_bytes()==baseline,'Actual post-stage cancel did not preserve authority')
    try:apply(store,identity,common,timeout_s=.05)
    except WorkerFailure as error:require('timed out' in str(error).lower(),'Expected real Blender timeout')
    else:raise RuntimeError('Hand worker unexpectedly survived the bounded startup timeout')
    require(store.file.read_bytes()==baseline,'Hand timeout changed project')
    external=[]
    def edit():
        saved=store.load();store.save(replace(saved,name='Concurrent hand acceptance editor',revision=saved.revision+1),expected_revision=saved.revision)
        external.append(store.file.read_bytes())
    stopped,thread,triggered,errors=after_stage(store,edit)
    try:
        try:apply(store,identity,common)
        except ProjectConflict:pass
        else:raise RuntimeError('Hand revision overwrote a real post-stage external save')
    finally:stopped.set();thread.join(3)
    require(triggered and not errors and external and store.file.read_bytes()==external[0],
            'External hand save was not preserved')
    require(sha256(master.read_bytes()).hexdigest()==master_sha,'Original master changed during transaction checks')
    # A rehashed external file must not become an accepted hand master just
    # because its metadata names the right registered part.
    root=out/'unknown-external-master';root.mkdir()
    shutil.copyfile(store.file,root/'project.ucc.json')
    for relative in ('parts/objects','parts/manifests'):
        shutil.copytree(store.root/relative,root/relative)
    (root/current.master_blend).parent.mkdir(parents=True);shutil.copyfile(master,root/current.master_blend)
    adopted=ProjectStore(root);saved=adopted.load()
    blob=(store.root/shorter_result.project.master_blend).read_bytes()+b'externally-rehashed-hand-file'
    digest=sha256(blob).hexdigest();relative='master/versions/'+digest+'.blend';(root/relative).write_bytes(blob)
    adopted.save(replace(saved,master_blend=relative,parts=shorter_result.project.parts,revision=saved.revision+1),expected_revision=saved.revision)
    before=adopted.file.read_bytes()
    try:apply(adopted,identity,common)
    except ProjectStorageError as error:require('receipt' in str(error).lower(),'Unknown hand file failed for another reason')
    else:raise RuntimeError('Unknown rehashed external hand master was accepted')
    require(adopted.file.read_bytes()==before,'Unknown external master rejection changed metadata')
    return {'pre_cancel_preserved_project':True,'actual_post_stage_cancel_preserved_project':True,
            'real_worker_timeout_preserved_project':True,'actual_post_stage_external_save_preserved':True,
            'unknown_rehashed_external_master_rejected':True,'all_previous_master_bytes_preserved':True}
