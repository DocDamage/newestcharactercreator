"""NONSHIPPING invented files/worker replies; no native, asset or rights proof."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import UUID

from fixtures.authored_idle_contract import saved_project
from fixtures.authored_idle_mapping import evidence, matrix
from ucc.core.authored_idle import AuthoredIdleInspectionRequest, AuthoredIdleRequest, IdleAuthoringPermission
from ucc.core.storage import ProjectStore
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import canonical_bytes, document_sha256
from ucc.jobs.authored_idle_evidence import INSPECT, AUTHOR, VERIFY, PROFILE, FRAME_PROFILE, QUALITY, QUALITY_EXECUTION, OUTPUTS, STATUS
from ucc.jobs.authored_idle_io import private_bytes
from ucc.jobs.authored_idle_policy import IdleSourcePolicyRecord, FLAGS as POLICY_FLAGS, POLICY
from ucc.jobs.authored_idle_sources import inspect_idle_authoring_sources
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.protocol import JobResult


def pin(payload): return sha256(payload).hexdigest()


class HostFixture:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.store = ProjectStore(self.root/'project')
        payload = b'BLENDER'+b'NONSHIPPING_NOT_A_BLEND'*90
        self.master_sha = pin(payload)
        project = replace(saved_project(hand=False, expression=False),
            master_blend='master/versions/'+self.master_sha+'.blend', revision=0)
        self.master = self.store.root/project.master_blend
        self.master.parent.mkdir(parents=True); self.master.write_bytes(payload)
        self.project = self.store.save(project)
        (self.store.root/'animations').mkdir()
        (self.store.root/'animations/NEVER_CONSUME.motion').write_bytes(b'NONSHIPPING_EXISTING_MOTION_MUST_NOT_BE_STAGED')
        self.database = self.root/'catalog.db'; self.database.write_bytes(b'NONSHIPPING_OPAQUE_CATALOG_NO_SQL')
        self.blender = self.root/'installed/blender.exe'; self.blender.parent.mkdir()
        self.blender.write_bytes(b'NONSHIPPING_NOT_EXECUTABLE')
        for folder, names in (
            ('addons_core/io_scene_fbx', ('__init__.py','import_fbx.py','export_fbx_bin.py','fbx_utils.py','parse_fbx.py')),
            ('modules/bpy_extras', ('__init__.py','anim_utils.py','io_utils.py','node_shader_utils.py','image_utils.py'))):
            directory = self.blender.parent/'5.3/scripts'/folder; directory.mkdir(parents=True)
            for name in names: (directory/name).write_bytes(b'# NONSHIPPING layout marker\n')
        (self.blender.parent/'5.3/scripts/modules/rna_prop_ui.py').write_bytes(b'# NONSHIPPING\n')
        self.worker = self.root/'worker/blender_bridge/entrypoint.py'; self.worker.parent.mkdir(parents=True)
        self.worker.write_bytes(b'# NONSHIPPING boundary only\n'); (self.worker.parent/'__init__.py').write_bytes(b'')
        output = self.root/'outputs'; output.mkdir(); self.destination = plan_destination(output/'candidate', self.store.root)
        source, = inspect_idle_authoring_sources(self.store)
        policy = {'schema_version': 1, 'policy': POLICY, 'asset_id': source.asset_id,
            'source_sha256': source.sha256, 'provenance_sha256': source.provenance_sha256,
            'review_note': 'NONSHIPPING invented policy, never actual permission', **POLICY_FLAGS}
        self.policy = self.root/'source-policy.json'; self.policy.write_bytes(canonical_bytes(policy))
        self.records = (IdleSourcePolicyRecord(source.asset_id, self.policy, pin(self.policy.read_bytes())),)
        permission = IdleAuthoringPermission(source.asset_id, source.sha256, self.records[0].sha256,
            'NONSHIPPING explicit synthetic per-use review only', True)
        self.inspection = AuthoredIdleInspectionRequest(str(UUID(int=801)), canonical_bytes(self.project.to_dict()),
            (permission,), 'NONSHIPPING synthetic original idle host boundary', True, True)
        self.calls = []; self.after = None; self.mutate = None

    def args(self):
        return dict(inspection_request=self.inspection, source_policy_records=self.records,
            database_path=self.database, destination=self.destination, blender_exe=self.blender, worker_script=self.worker)

    def run(self, job, *, staged_inputs, timeout_s, cancel):
        """Explicit test double replacing the process boundary, not product code."""
        self.calls.append(job); folder = self.store.root/'.ucc-jobs'/job.job_id; folder.mkdir()
        for name, source in staged_inputs.items(): shutil.copyfile(source, folder/name)
        (folder/'request.json').write_text(json.dumps(job.as_dict()), encoding='utf-8')
        inspect = job.operation == INSPECT
        request = (AuthoredIdleInspectionRequest if inspect else AuthoredIdleRequest).from_bytes(
            (folder/('idle_inspection_request.json' if inspect else 'idle_authoring_request.json')).read_bytes())
        target = TargetActionTarget(self.project.project_id, self.project.revision,
            document_sha256(self.project.to_dict()), self.master_sha, 'd'*64, 'e'*64) if inspect else request.target
        frame = self.frame(target) if inspect else json.loads((folder/'idle_anatomical_frame.json').read_bytes())
        frame_sha = pin(private_bytes(frame)); fingerprint = frame['skeleton_fingerprint']
        header = {'schema_version': 1, 'status': STATUS[job.operation], 'anatomical_frame_sha256': frame_sha,
            'authoring_request_sha256': request.sha256, 'target': target.to_dict(), 'skeleton_fingerprint': fingerprint}
        def write(name, value): (folder/name).write_bytes(private_bytes(value))
        def row(name):
            payload = (folder/name).read_bytes(); return {'name': name, 'bytes': len(payload), 'sha256': pin(payload)}
        if inspect:
            write('idle_anatomical_frame.json', frame)
            write('idle_inspection_report.json', {'schema_version': 1, 'status': STATUS[INSPECT],
                'inspection_request_sha256': request.sha256, 'target': target.to_dict(),
                'anatomical_frame': row('idle_anatomical_frame.json'), 'source_profile': PROFILE,
                'skeleton_fingerprint': fingerprint, 'bone_count': 163, 'existing_action_count': 0,
                'existing_motion_read': False, 'authoring_performed': False, **QUALITY})
        elif job.operation == AUTHOR:
            (folder/'original_idle.fbx').write_bytes(b'NONSHIPPING_NOT_FBX_SOURCE')
            (folder/'authored_idle_review.blend').write_bytes(b'NONSHIPPING_NOT_REVIEW_BLEND')
            construction = {'baseline_quaternions': {b['name']: [1.,0.,0.,0.] for b in frame['anatomy']['bones']},
                'periodic_axes': {name: {'kind': kind, 'axis': [1.,0.,0.]} for name,kind in
                    (('spine03','torso'),('head','head'),('lowerarm01.L','elbow'),('lowerarm01.R','elbow'))},
                'baseline_max_anatomical_direction_residual': 0.}
            write('authored_idle_recipe.json', {'schema_version': 1, 'profile': PROFILE,
                'authoring_request_sha256': request.sha256, 'anatomical_frame_sha256': frame_sha,
                'target': target.to_dict(), 'skeleton_fingerprint': fingerprint, 'construction': construction,
                'source_samples': 300, 'source_first_frame': 2, 'source_last_frame': 301, 'fps': 30,
                'review_first_frame': 1, 'review_last_frame': 300, 'virtual_source_frame302_stored': False,
                'existing_motion_read': False, 'armature_only_source': True, **QUALITY})
            write('authored_idle_report.json', {**header, 'sample_count': 300, 'numeric_observations': numeric(),
                'files': [row(name) for name in OUTPUTS[AUTHOR][:3]], 'saved_reopen_verified': False,
                'private_geometry_metrics_not_for_model_output': True, **QUALITY})
        else:
            snapshot = json.loads(evidence()[1]['snapshot_json'])
            snapshot['source_sha256'] = job.options['source_sha256']
            # Preserve the bridge's legacy unsorted snapshot bytes deliberately.
            (folder/'authored_idle_source_snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
            zero_velocity = {'position_m_s': 0., 'rotation_matrix_s': 0.}
            write('authored_idle_verification.json', {**header, 'direct_recipe': numeric(),
                'saved_review': {'saved_review_samples': 300, 'maximum_recipe_world_matrix_residual': 0.,
                    'maximum_saved_neutral_sole_drift_m': 0., 'actual_stored_review_frames': [1,300],
                    'wrapped_same_interval_velocity_residual': zero_velocity},
                'actual_fbx_source': {'source_samples': 300, 'actual_source_frames': [2,301], 'fps': 30,
                    'maximum_source_recipe_world_matrix_residual': 0., 'wrapped_same_interval_velocity_residual': zero_velocity,
                    'source_bone_count': 163, 'source_snapshot': row('authored_idle_source_snapshot.json'),
                    'armature_only': True, 'automatic_retarget_family_admission': False},
                'original_inputs_preserved': True, 'private_geometry_metrics_not_for_model_output': True,
                'required_quality_execution': dict(QUALITY_EXECUTION),
                'independent_root_nine_worker_and_human_review_required': True, **QUALITY})
        summary = {'schema_version': 1, 'status': STATUS[job.operation], 'operation': job.operation,
            'request_sha256': request.sha256, 'target': target.to_dict(), 'anatomical_frame_sha256': frame_sha,
            'source_profile': PROFILE, 'skeleton_fingerprint': fingerprint, 'bone_count': 163,
            'outputs': [row(name) for name in OUTPUTS[job.operation]], 'sample_count': 0 if inspect else 300,
            'source_first_frame': None if inspect else 2, 'source_last_frame': None if inspect else 301,
            'fps': None if inspect else 30, **QUALITY}
        if self.mutate: self.mutate(job, folder, summary)
        result = JobResult(job.job_id, job.operation, 'ok', summary)
        (folder/'result.json').write_text(json.dumps(result.as_dict()), encoding='utf-8')
        if self.after: self.after(job, folder)
        return result, folder

    @staticmethod
    def frame(target):
        frame = deepcopy(json.loads(evidence()[1]['frame_json'])); frame['target'] = target.to_dict()
        frame['anatomy']['axes'] = {'right': [-1.,0.,0.], 'up': [0.,0.,1.], 'forward': [0.,-1.,0.]}
        frame['anatomy']['hands'] = {side: {'direction': [1.,0.,0.], 'normal': [0.,1.,0.],
            'flex_axis': [0.,0.,1.]} for side in ('L','R')}
        frame['sole_patches'] = {side: {'indices': [0,1,2], 'neutral_world': [[0.,0.,0.]]*3} for side in ('L','R')}
        frame['neutral'] = {'rig_name': 'NONSHIPPING_rig', 'human_name': 'NONSHIPPING_human',
            'rig_world': matrix(0.), 'human_world': matrix(0.), 'stable_invariants_sha256': 'a'*64,
            'full_vertex_count': 19158, 'full_skin_sha256': 'b'*64, 'visible_skin_sha256': 'c'*64,
            'weights_sha256': 'd'*64, 'key_state_sha256': 'e'*64}
        return frame


def numeric():
    return {'direct_samples': 300, 'maximum_neutral_sole_drift_m': 0.,
        'analytic_virtual_seam_quaternion_residual': 0., 'analytic_virtual_seam_first_derivative_residual_rad_s': 0.,
        'virtual_seam_was_stored': False, 'human_review_approved': False}
