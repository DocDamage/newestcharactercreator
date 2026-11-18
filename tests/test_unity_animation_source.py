"""Pure job and Action clock controls. These fixtures establish no engine readiness."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from blender_bridge.unity_animation_take import extend_export_curves, validate_clock
from fixtures.target_action_logic import TargetFixture
from ucc.core.errors import ValidationError
from ucc.export.unity_animation_recipe import (
    INPUT_FILES, OUTPUT_LIMITS, POLICY, STAGE, VERIFY, output_option, validate_binding,
)
from ucc.jobs.protocol import JobRequest, JobResult


class _Points(list):
    def insert(self, frame, value, *, options):
        assert options == {'FAST'}
        point = SimpleNamespace(co=SimpleNamespace(x=frame, y=value), interpolation=None)
        self.append(point)
        return point


def _curve(channel, index, first):
    points = _Points(SimpleNamespace(co=SimpleNamespace(x=frame, y=first if frame == 1 else .2),
                                    interpolation='LINEAR') for frame in range(1, 301))
    return SimpleNamespace(data_path='pose.bones["UNIT"].'+channel, array_index=index,
                           keyframe_points=points, update=lambda: None)


class RegisteredUnityAnimationTests(unittest.TestCase):
    def test_worker_operations_have_closed_inputs_and_outputs(self):
        stage = {key:'a'*64 for key in (*INPUT_FILES.values(), 'source_sha256')}
        verify = {**stage, **{output_option(name):'c'*64 for name in OUTPUT_LIMITS}}
        files = {name:'c'*64 for name in OUTPUT_LIMITS}
        details = {'policy': POLICY, 'files': files, 'engine_import_verified': False}
        for operation, options, result in ((STAGE, stage, details), (VERIFY, verify,
                {**details, 'verification_sha256': 'b'*64, 'fbx_readback_sha256': 'b'*64})):
            job = JobRequest.new(operation, input_project='candidate.blend', options=options)
            JobResult(job.job_id, operation, 'ok', result)
            with self.assertRaises(ValidationError):
                JobResult(job.job_id, operation, 'ok', {**result, 'engine_import_verified':True})
            with self.assertRaises(ValidationError):
                JobResult(job.job_id, operation, 'ok', {**result, 'files': {}})
            for bad in ({**options, 'clock': 301}, {**options, 'source_sha256': True}):
                with self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=bad)
        with self.assertRaises(ValidationError):
            JobRequest.new(VERIFY, input_project='candidate.blend', options=stage)
        with self.assertRaises(ValidationError):
            JobRequest.new(STAGE, input_project='review_motion.blend', options=stage)

    def test_schemas_accept_only_new_scoped_approval(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema unavailable')
        root = Path(__file__).resolve().parents[1]/'docs/schemas'
        job_schema, result_schema = (Draft202012Validator(json.loads((root/f'worker-{kind}.v1.schema.json').read_bytes()))
                                     for kind in ('job','result'))
        options = {key:'a'*64 for key in (*INPUT_FILES.values(), 'source_sha256')}
        job = JobRequest.new(STAGE, input_project='candidate.blend', options=options)
        job_schema.validate(job.as_dict())
        details = {'policy': POLICY, 'files': {name:'b'*64 for name in OUTPUT_LIMITS}, 'engine_import_verified': False}
        result = JobResult(job.job_id, STAGE, 'ok', details).as_dict()
        result_schema.validate(result)
        self.assertFalse(result_schema.is_valid({**result, 'details': {**details, 'engine_import_verified': True}}))
        verify_options = options | {output_option(name): digest for name, digest in details['files'].items()}
        verify = JobRequest.new(VERIFY, input_project='candidate.blend', options=verify_options)
        job_schema.validate(verify.as_dict())
        verified_details = details | {'verification_sha256': 'a'*64, 'fbx_readback_sha256': 'b'*64}
        result_schema.validate(JobResult(verify.job_id, VERIFY, 'ok', verified_details).as_dict())

    def test_binding_rejects_swapped_native_proof_identity(self):
        with TemporaryDirectory() as tmp:
            fixture = TargetFixture(Path(tmp))
            _, binding = fixture.payload()
            files = binding.file_map
            options = {'target_binding_sha256': binding.sha256, 'source_sha256': binding.source.source_sha256,
                'master_sha256': binding.target.master_sha256, 'snapshot_sha256': binding.source.snapshot_sha256,
                'mapping_sha256': binding.mapping_sha256, 'review_sha256': files['body_first/review_motion.blend'].sha256,
                'timeline_sha256': files['body_first/target_timeline.json'].sha256}
            validate_binding(binding, options)
            for name in options:
                with self.subTest(name=name), self.assertRaises(ValidationError):
                    validate_binding(binding, {**options, name:'0'*64})

    def test_clock_and_virtual_frame_keep_sample_one_distinct_from_rest(self):
        rotation, location = _curve('rotation_quaternion', 0, .75), _curve('location', 1, -.125)
        original = [[(point.co.x, point.co.y) for point in curve.keyframe_points] for curve in (rotation, location)]
        extend_export_curves([rotation, location])
        for index, curve in enumerate((rotation, location)):
            points = curve.keyframe_points
            self.assertEqual([(p.co.x,p.co.y) for p in points[:300]], original[index])
            self.assertEqual((points[300].co.x, points[300].co.y), (0, float(index == 0)))
            self.assertEqual((points[301].co.x, points[301].co.y), (301, original[index][0][1]))
        clock = SimpleNamespace(frame_start=1, frame_end=300, render=SimpleNamespace(fps=30, fps_base=1.))
        action = SimpleNamespace(frame_range=(1., 300.))
        validate_clock(clock, action)
        for name, value in (('frame_start',0), ('frame_end',301)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_clock(SimpleNamespace(**{**vars(clock), name:value}), action)

    def test_rejection_leaves_copy_unchanged_for_bad_channel_or_clock(self):
        good = _curve('rotation_quaternion', 0, .7)
        missing = _curve('location', 0, 0.)
        missing.keyframe_points.pop()
        for bad in (_curve('scale', 0, 1.), missing, good):
            with self.assertRaises(ValueError):
                extend_export_curves([good, bad])
            self.assertEqual(len(good.keyframe_points), 300)
