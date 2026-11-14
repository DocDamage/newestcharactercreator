"""Synthetic protocol/state boundaries; real MPFB inspection is a separate gate."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

from blender_bridge.neutral_master import animation_audit, checked_job, neutral_pose_and_keys
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.neutral_master import HASHES, FALSE_FLAGS, POLICY, checked_observation, inspect_saved_neutral_master
from ucc.jobs.protocol import JobRequest, JobResult


def observation(master_sha, expression_count=0):
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': master_sha, 'blender_version': '5.3.0',
        'mpfb_version': '2.0.18', 'bone_count': 163, 'full_vertex_count': 19158, 'visible_vertex_count': 13380,
        'inspected_datablocks': 90, 'action_count': 0, 'driven_datablocks': 0, 'nla_tracks': 0,
        'bone_constraints': 0, 'exact_identity_pose_basis': True, 'expression_key_count': expression_count,
        'source_state_preserved': True, **{name: 'b'*64 for name in HASHES}, **{name: False for name in FALSE_FLAGS}}


class NeutralContractTests(unittest.TestCase):
    def test_host_and_independent_worker_require_only_fixed_candidate_and_exact_hash(self):
        job = JobRequest.new('inspect_mpfb_neutral_master', input_project='candidate.blend', options={'master_sha256': 'a'*64})
        checked_job(job.as_dict())
        for project, options in ((None, {'master_sha256': 'a'*64}), ('other.blend', {'master_sha256': 'a'*64}),
                ('candidate.blend', {}), ('candidate.blend', {'master_sha256': True}),
                ('candidate.blend', {'master_sha256': 'A'*64}), ('candidate.blend', {'master_sha256': 'a'*64, 'repair': True})):
            with self.subTest(project=project, options=options):
                with self.assertRaises(ValidationError): JobRequest.new('inspect_mpfb_neutral_master', input_project=project, options=options)
                with self.assertRaises(ValueError): checked_job({**job.as_dict(), 'input_project': project, 'options': options})

    def test_observation_types_counts_hashes_and_false_approval_flags_are_closed(self):
        for name, value in (('schema_version', True), ('action_count', False), ('bone_count', 162),
                ('expression_key_count', 12), ('master_sha256', 'c'*64), ('state_sha256', 'bad'),
                ('inspected_datablocks', 0), ('blender_version', '5.2.0'), ('source_provenance_verified', True),
                ('project_action_admission_verified', True), ('extra', True)):
            data = observation('a'*64); data[name] = value
            with self.subTest(name=name), self.assertRaises(ValidationError): checked_observation(data, 'a'*64, 0)

    def test_every_loaded_id_and_embedded_node_tree_are_checked_without_muting(self):
        class Block:
            library = override_library = animation_data = node_tree = None
            def as_pointer(self): return id(self)
        material = Block(); tree = Block(); material.node_tree = tree
        fake = NS(data=NS(actions=[], libraries=[], materials=[material],
            bl_rna=NS(properties=[NS(type='COLLECTION', identifier='materials')])), types=NS(ID=Block))
        self.assertEqual(animation_audit(fake), 2)
        tree.animation_data = NS(action=None, drivers=['fixture'], nla_tracks=[])
        with self.assertRaisesRegex(ValueError, 'datablock'): animation_audit(fake)
        self.assertEqual(tree.animation_data.drivers, ['fixture'])
        tree.animation_data = NS(action=None, drivers=[], nla_tracks=['muted fixture track'])
        with self.assertRaisesRegex(ValueError, 'datablock'): animation_audit(fake)
        fake.data.actions.append('unused fixture Action')
        with self.assertRaisesRegex(ValueError, 'unused Actions'): animation_audit(fake)

    def test_exact_pose_and_muted_constraint_checks_never_reset_saved_channels(self):
        matrix = [[float(i == j) for j in range(4)] for i in range(4)]
        bone = NS(matrix_basis=matrix, constraints=[])
        rig = NS(data=NS(pose_position='POSE'), pose=NS(bones=[bone]))
        human = NS(data=NS(shape_keys=NS(key_blocks=[])))
        self.assertEqual(neutral_pose_and_keys(rig, human), 0)
        matrix[0][3] = 1e-12
        with self.assertRaisesRegex(ValueError, 'exact identity'): neutral_pose_and_keys(rig, human)
        self.assertEqual(matrix[0][3], 1e-12)
        matrix[0][3] = 0.; bone.constraints.append(NS(mute=True, influence=0.))
        with self.assertRaisesRegex(ValueError, 'muted constraints'): neutral_pose_and_keys(rig, human)


class NeutralCoordinatorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.store = ProjectStore(self.root/'character')
        self.original = b'BLENDER'+b'SYNTHETIC_HEADER_ONLY_NOT_BLENDER'*70
        self.master_sha = sha256(self.original).hexdigest()
        self.relative = 'master/versions/'+self.master_sha+'.blend'
        self.master = self.store.root/self.relative; self.master.parent.mkdir(parents=True)
        self.master.write_bytes(self.original)
        self.project = self.store.save(replace(CharacterProject.new('Neutral boundary'),
            master_blend=self.relative, geometry_state='generated_unverified'))
        self.executable = self.root/'unit-only-executable'; self.executable.write_bytes(b'NOT_EXECUTED')
        self.script = self.root/'unit-only-bridge.py'; self.script.write_bytes(b'# NOT EXECUTED')
        self.runs = 0; self.fault = None

    def worker(self, request, **kwargs):
        self.runs += 1; folder = self.store.root/'.ucc-jobs'/request.job_id; folder.mkdir(parents=True)
        (folder/'candidate.blend').write_bytes(self.original)
        report = observation(self.master_sha)
        if self.fault == 'disagree' and self.runs == 2: report['state_sha256'] = 'c'*64
        if self.fault == 'staged': (folder/'candidate.blend').write_bytes(b'tampered')
        if self.fault == 'approval': report['source_provenance_verified'] = True
        if self.fault == 'master': self.master.write_bytes(b'BLENDER'+b'changed fixture'*100)
        if self.fault == 'project': self.store.save(replace(self.project, name='External edit', revision=self.project.revision+1), expected_revision=self.project.revision)
        if self.fault == 'cancel': kwargs['cancel'].set()
        return JobResult(request.job_id, request.operation, 'ok', report), folder

    def invoke(self, **kwargs):
        with patch('ucc.jobs.neutral_master.BlenderJobRunner.run', side_effect=self.worker):
            return inspect_saved_neutral_master(self.store, blender_exe=self.executable, worker_script=self.script,
                expected_project_id=self.project.project_id, expected_revision=self.project.revision,
                expected_master_blend=self.relative, **kwargs)

    def test_invalid_timeout_values_reject_before_any_staging_or_worker(self):
        for value in (True, False, 0, -1, 3601, float('nan'), float('inf'), None):
            with self.subTest(value=value), self.assertRaises(ValidationError): self.invoke(timeout_s=value)
        self.assertEqual(self.runs, 0)
        self.assertFalse((self.store.root/'.ucc-jobs').exists())

    def test_missing_or_redirected_executable_rejects_before_any_worker(self):
        self.executable.unlink()
        with self.assertRaises(ValidationError): self.invoke()
        self.executable.write_bytes(b'NOT_EXECUTED')
        with patch.object(Path, 'is_symlink', return_value=True), self.assertRaises(ValidationError): self.invoke()
        self.assertEqual(self.runs, 0)

    def test_two_workers_agree_without_master_or_project_mutation(self):
        metadata = self.store.file.read_bytes(); result = self.invoke()
        self.assertEqual(self.runs, 2); self.assertEqual(len(set(result.worker_job_ids)), 2)
        self.assertEqual(result.master_sha256, self.master_sha)
        self.assertEqual(result.project_metadata_sha256, sha256(metadata).hexdigest())
        self.assertEqual(self.master.read_bytes(), self.original); self.assertEqual(self.store.file.read_bytes(), metadata)
        self.assertFalse(result.observation['source_provenance_verified'])
        self.assertFalse(result.observation['project_action_admission_verified'])

    def test_metadata_clip_ids_are_not_confused_with_actual_animated_master_permission(self):
        self.project = self.store.save(replace(self.project, animations=('catalog-source#clip-0000',),
            revision=self.project.revision+1), expected_revision=self.project.revision)
        result = self.invoke()
        self.assertEqual(self.store.load().animations, ('catalog-source#clip-0000',))
        self.assertFalse(result.observation['project_action_admission_verified'])

    def test_independent_state_disagreement_cannot_produce_neutral_proof(self):
        self.fault = 'disagree'
        with self.assertRaisesRegex(ValidationError, 'disagree'): self.invoke()

    def test_changed_staged_input_and_unsupported_approval_do_not_modify_original(self):
        for fault in ('staged', 'approval'):
            self.fault = fault
            with self.subTest(fault=fault), self.assertRaises((ProjectStorageError, ValidationError)): self.invoke()
            self.assertEqual(self.master.read_bytes(), self.original)
            self.assertEqual(self.store.load(), self.project)

    def test_external_project_change_is_detected_before_second_worker(self):
        self.fault = 'project'
        with self.assertRaises(ProjectConflict): self.invoke()
        self.assertEqual(self.runs, 1); self.assertEqual(self.master.read_bytes(), self.original)

    def test_external_master_change_is_detected_before_second_worker(self):
        self.fault = 'master'
        with self.assertRaises(ProjectStorageError): self.invoke()
        self.assertEqual(self.runs, 1); self.assertEqual(self.store.load(), self.project)

    def test_cancellation_after_first_worker_returns_no_neutral_proof(self):
        self.fault = 'cancel'
        with self.assertRaises(ProjectStorageError): self.invoke(cancel=Event())
        self.assertEqual(self.runs, 1); self.assertEqual(self.master.read_bytes(), self.original)
