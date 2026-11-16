"""One guarded local-preview transaction composed from the existing workers."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import _lock
from ucc.core.target_action import TargetActionBinding, TargetActionFile, TargetActionProducer, TargetActionTarget
from ucc.core.target_action_format import RETAINED_FILES, canonical_bytes, document_sha256, SKIN_POLICY
from ucc.core.target_action_request import TargetActionRequest
from .export_destination import rename_new
from .expression_storage import safe_directory
from .godot_candidate_inputs import identity
from .master_preview import _digest
from .native_body import preview_native_body
from .native_playback import prepare_native_playback
from .neutral_master import inspect_saved_neutral_master
from .target_action_context import operation_budget, source_review, require_review, protected
from .target_action_storage import action_root, load_target_action, source_state, seal, ancestry
from .worker_resources import worker_dependency_files
from .target_action_resources import (blender_helper_resources, blender_helper_inventory,
    host_code_snapshot, worker_namespace_snapshot)


def copy_file(source, target, budget):
    protected(source); budget.check()
    expected = (identity(source), _digest(source, budget.cancel))
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as reader, target.open('xb') as writer:
        while True:
            budget.check()
            block = reader.read(1024*1024)
            if not block: break
            writer.write(block)
    if (identity(source), _digest(source, budget.cancel)) != expected or _digest(target, budget.cancel) != expected[1]:
        raise ProjectStorageError('Target preview copy raced a source/proof change')


def prepare_target_action(store, *, database_path, clip_id, expected_source_sha256,
        expected_policy, mapping_profile, expected_mapping_sha256, expected_project_id,
        expected_revision, expected_master_blend, expected_project_sha256,
        expected_source_binding_sha256, expected_catalog_record_sha256,
        blender_exe, worker_script, purpose, local_preview_confirmed,
        cancel=None, timeout_s=1800, progress=None):
    with operation_budget(cancel, timeout_s) as budget:
        return _prepare(store, Path(database_path), clip_id, expected_source_sha256, expected_policy,
            Path(mapping_profile), expected_mapping_sha256, expected_project_id, expected_revision,
            expected_master_blend, expected_project_sha256, expected_source_binding_sha256,
            expected_catalog_record_sha256, Path(blender_exe), Path(worker_script), purpose,
            local_preview_confirmed, budget, progress)


def _prepare(store, database, clip_id, source_sha, policy, mapping, mapping_sha, project_id,
        revision, master_blend, project_sha, source_binding_sha, catalog_sha,
        blender, worker, purpose, consent, budget, progress):
    def phase(name):
        budget.check()
        if progress: progress(name)
        budget.check()
    phase('SOURCE_REVIEW')
    review = source_review(store, database, clip_id, project_id, revision, master_blend, project_sha, budget)
    require_review(review, source_binding_sha, catalog_sha)
    if review.source.source_sha256 != source_sha or review.policy != policy:
        raise ProjectConflict('Target preparation differs from the explicitly reviewed source or policy')
    protected(mapping); protected(blender); protected(worker)
    if _digest(mapping, budget.cancel) != mapping_sha:
        raise ProjectConflict('Explicit reviewed target mapping changed')
    profile, _ = read_native_profile(mapping, source_sha, review.source.snapshot_sha256, review.master_sha256)
    if profile.get('skin_deformation_policy') != SKIN_POLICY:
        raise ValidationError('Registered target preview currently requires bound corrective skin V1')
    from .target_action_evidence import validate_retained_target_action
    host_state = host_code_snapshot(budget)
    worker_state = worker_namespace_snapshot(worker, budget)
    resources = worker_dependency_files(worker)|{worker}
    helpers = blender_helper_resources(blender, budget)
    helper_state = blender_helper_inventory(blender, budget)
    protected_inputs = resources|set(helpers.values())|{blender, mapping}
    resource_hashes = {}
    hashes = {}
    identities = {}
    for path in sorted(protected_inputs, key=str):
        protected(path); budget.check()
        hashes[path] = _digest(path, budget.cancel); identities[path] = identity(path)
        if path in resources:
            # Relative first-party names are portable metadata; absolute paths stay private.
            roots = (worker.parent, worker.parent.parent)
            root = next((p for p in roots if path.is_relative_to(p)), None)
            if root is None: raise ProjectStorageError('Worker resource escaped its declared bundle')
            name = path.relative_to(worker.parent.parent).as_posix()
            resource_hashes[name] = hashes[path]
    resource_hashes.update({name:hashes[path] for name,path in helpers.items()})
    resource_hashes.update({'host/'+name:value[1] for name,value in host_state.items()
        if isinstance(value,tuple) and len(value)==2 and isinstance(value[1],str)})
    resources_sha = document_sha256(resource_hashes)
    request = TargetActionRequest(str(uuid4()), project_id, revision, project_sha, review.master_sha256,
        review.source, mapping_sha, profile.get('root_motion_policy', 'ARMATURE_ORIGIN_DISPLACEMENT_V1'),
        hashes[blender], resources_sha, purpose, consent)
    root = action_root(store, create=True)
    baseline = source_state(store, budget)
    authorities = ancestry((store.root, review.source_path, database, *protected_inputs))
    authorities[database] = (*identity(database)[:2], 0, 0)
    def guard(exclude=None):
        budget.check()
        if host_code_snapshot(budget) != host_state:
            raise ProjectStorageError('Target preview host code or executable closure changed')
        if (worker_namespace_snapshot(worker, budget) != worker_state
                or worker_dependency_files(worker)|{worker} != resources):
            raise ProjectStorageError('Target preview worker code namespace changed')
        if blender_helper_resources(blender, budget) != helpers or blender_helper_inventory(blender, budget) != helper_state:
            raise ProjectStorageError('Selected Blender FBX helper closure changed')
        current = source_review(store, database, clip_id, project_id, revision, master_blend, project_sha, budget)
        if current != review or source_state(store, budget, exclude) != baseline:
            raise ProjectConflict('Registered target project/source/proof ancestry changed')
        for path, digest in hashes.items():
            protected(path)
            if identity(path) != identities[path] or _digest(path, budget.cancel) != digest:
                raise ProjectStorageError('Target preview tool, mapping or worker resource changed')
        for path, stamp in authorities.items():
            now = identity(protected(path))
            if (now[:2] != stamp[:2] if path == database else now != stamp):
                raise ProjectStorageError('Target preview source/tool/catalog ancestor identity changed')
    guard()
    work = safe_directory(store, '.ucc-jobs', create=True)/('target-action-'+request.job_id)
    work.mkdir(exist_ok=False); payload = work/'payload'; payload.mkdir()
    (payload/'preparation_request.json').write_bytes(canonical_bytes(request.to_dict()))
    published = None
    def pair(job_id, folder):
        actual = store.root/'.ucc-jobs'/job_id
        protected(actual)
        if folder != actual or not actual.is_dir():
            raise ProjectStorageError('Target preview producer folder differs from its actual job')
        for name in ('request.json', 'result.json'):
            copy_file(actual/name, payload/folder_role[job_id]/name, budget)
    folder_role = {}
    intakes = []
    def observe(job, result, folder):
        guard()
        role = ('source_intake_first', 'source_intake_second')[len(intakes)]
        folder_role[job.job_id] = role
        pair(job.job_id, folder)
        if result.job_id != job.job_id or result.operation != 'inspect_fbx_animation':
            raise ValidationError('Observed source result differs from its actual request')
        intakes.append((job.job_id, folder, result.details))
    try:
        phase('NEUTRAL_MASTER')
        neutral = inspect_saved_neutral_master(store, blender_exe=blender, worker_script=worker,
            expected_project_id=project_id, expected_revision=revision, expected_master_blend=master_blend,
            cancel=budget.cancel, timeout_s=budget.remaining(), source_guard=guard)
        guard()
        for label, job_id in zip(('first', 'second'), neutral.worker_job_ids):
            for kind in ('request', 'result'):
                copy_file(store.root/'.ucc-jobs'/job_id/(kind+'.json'), payload/'neutral'/(label+'_'+kind+'.json'), budget)
        phase('NATIVE_TARGET')
        preview = preview_native_body(store, source_fbx=review.source_path, mapping_profile=mapping,
            blender_exe=blender, worker_script=worker, permission=policy,
            expected_project_id=project_id, expected_revision=revision, expected_master_blend=master_blend,
            cancel=budget.cancel, timeout_s=budget.remaining(), source_intake_observer=observe, source_guard=guard)
        guard()
        if len(intakes) != 2 or preview.source_intake_worker_job_ids != tuple(row[0] for row in intakes):
            raise ValidationError('Actual source-intake producer identities are incomplete')
        for _, folder, details in intakes:
            record = details['snapshot']
            if record['sha256'] != review.source.snapshot_sha256 or _digest(folder/'source_snapshot.json', budget.cancel) != record['sha256']:
                raise ValidationError('Fresh native intake differs from the registered source receipt')
        first = store.root/'.ucc-jobs'/preview.worker_job_ids[0]
        copy_file(first/'source_snapshot.json', payload/'source_snapshot.json', budget)
        copy_file(mapping, payload/'native_mapping.json', budget)
        for role, job_id in zip(('body_first', 'body_second'), preview.worker_job_ids):
            folder_role[job_id] = role; folder = store.root/'.ucc-jobs'/job_id; pair(job_id, folder)
            for name in ('target_timeline.json', 'review_motion.blend'):
                copy_file(folder/name, payload/role/name, budget)
        folder_role[preview.private_reopen_job_id] = 'body_reopen'
        pair(preview.private_reopen_job_id, store.root/'.ucc-jobs'/preview.private_reopen_job_id)
        for name in RETAINED_FILES:
            prefix = 'body_first/review_frames/'
            if name.startswith(prefix): copy_file(first/name.removeprefix('body_first/'), payload/name, budget)
        phase('PLAYBACK_CACHE')
        playback = prepare_native_playback(store, preview, source_fbx=review.source_path,
            permission=policy, blender_exe=blender, worker_script=worker,
            cancel=budget.cancel, timeout_s=budget.remaining(), source_guard=guard)
        guard()
        if not playback.surface_verification_job_id:
            raise ValidationError('Registered target preview requires current complete cache/surface verification')
        for role, job_id in (('playback', playback.job_id), ('surface_verify', playback.surface_verification_job_id)):
            folder_role[job_id] = role; pair(job_id, store.root/'.ucc-jobs'/job_id)
        for name in ('motion_skin.json', 'motion_skin.bin', 'motion_contacts.json'):
            copy_file(store.root/'.ucc-jobs'/playback.job_id/name, payload/'playback'/name, budget)
        producer = TargetActionProducer(hashes[blender], resources_sha, neutral.worker_job_ids,
            preview.source_intake_worker_job_ids, preview.worker_job_ids, preview.private_reopen_job_id,
            playback.job_id, playback.surface_verification_job_id)
        binding = TargetActionBinding(request.sha256, review.source,
            TargetActionTarget(project_id, revision, project_sha, review.master_sha256,
                neutral.observation['state_sha256'], neutral.observation['rest_sha256']),
            mapping_sha, request.root_motion_policy, producer,
            tuple(TargetActionFile(name, _digest(payload/name, budget.cancel), (payload/name).stat().st_size)
                  for name in sorted(RETAINED_FILES)))
        (payload/'binding.json').write_bytes(canonical_bytes(binding.to_dict()))
        phase('RETAINED_VALIDATION')
        sealed = seal(payload, binding, budget)
        validate_retained_target_action(payload, binding, cancel_check=budget.check)
        guard()
        if seal(payload, binding, budget) != sealed:
            raise ProjectStorageError('Target preview proof payload changed during retained validation')
        phase('PERSISTING')
        destination = root/binding.sha256
        with _lock(store.root/'.project.ucc.lock', timeout_s=min(3., budget.remaining())):
            guard()
            rename_new(payload, destination); published = destination
        phase('RECORD_COMMITTED')
        guard(destination)
        result = load_target_action(store, binding_sha256=binding.sha256, database_path=database,
            expected_project_id=project_id, expected_revision=revision, expected_master_blend=master_blend,
            expected_project_sha256=project_sha, expected_clip_id=clip_id,
            expected_source_binding_sha256=source_binding_sha, expected_catalog_record_sha256=catalog_sha,
            cancel=budget.cancel, timeout_s=budget.remaining(), progress=progress)
        return replace(result, workdir=work)
    except BaseException as error:
        error.add_note('Target preview diagnostics retained in '+str(work))
        # A fully committed immutable record remains discoverable after a late UI/
        # caller failure. Its current eligibility is always revalidated by Load.
        if published is not None:
            error.add_note('Completed private target binding retained at '+str(published))
        raise
