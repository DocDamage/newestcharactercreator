"""Adversarial independent worker-policy tests; no mocked geometry approval."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from blender_bridge.face_policy import recipe, read_json, check_inputs
from ucc.core.facial import build_face_recipe, validate_face_recipe
from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest


class FaceWorkerPolicyTests(unittest.TestCase):
    def test_asset_inspection_has_no_user_paths_or_options(self):
        self.assertIsNone(JobRequest.new('inspect_mpfb_face_assets').input_project)
        for path, options in (('candidate.blend', {}), (None, {'data_dir': '../elsewhere'})):
            with self.assertRaises(ValidationError):
                JobRequest.new('inspect_mpfb_face_assets', input_project=path, options=options)

    def test_desktop_worker_request_requires_pinned_complete_bindings(self):
        from ucc.core.facial import NOSE_TARGETS
        for operation in ('stage_mpfb_face', 'verify_mpfb_face'):
            options = {'master_sha256': 'a'*64, 'recipe_sha256': 'b'*64,
                       **{t.role+'_target_sha256': t.sha256 for t in NOSE_TARGETS}}
            if operation.startswith('verify'):
                options.update(face_sha256='c'*64, report_sha256='d'*64)
            job = JobRequest.new(operation, input_project='candidate.blend', options=options)
            for field in options:
                partial = dict(options); del partial[field]
                with self.subTest(operation=operation, field=field), self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=partial)
            for bad in (dict(options, narrow_target_sha256='e'*64), dict(options, extra='a'*64)):
                with self.assertRaises(ValidationError):
                    JobRequest.new(operation, input_project='candidate.blend', options=bad)
            with self.assertRaises(ValidationError):
                JobRequest.new(operation, input_project='elsewhere.blend', options=options)

    def test_independent_recipe_agrees_across_bounded_range(self):
        for value in (0., .01, .2, .5, .51, .8, 1.):
            raw = build_face_recipe('a'*64, {'nose_width': value})
            self.assertEqual(recipe(json.loads(json.dumps(raw)), 'a'*64), raw)

    def test_both_validators_reject_coherent_or_partial_substitutions(self):
        original = build_face_recipe('a'*64, {'nose_width': .8})
        changes = [
            lambda r: r.update(schema_version=True),
            lambda r: r['parameters'].update(nose_width=True),
            lambda r: r['parameters'].update(nose_width=float('nan')),
            lambda r: r['parameters'].update(nose_width=10**1000),
            lambda r: r['bindings'].update(base_sha256='b'*64),
            lambda r: r['bindings'].update(rig_sha256='b'*64),
            lambda r: r['bindings'].pop('base_sha256'),
            lambda r: r['targets'][0].update(file='../../elsewhere.gz'),
            lambda r: r['targets'][0].update(weight=False),
            lambda r: r['targets'][1].update(weight=.2),
            lambda r: r['targets'][0].update(weight=.1),
            lambda r: r['targets'].reverse(),
            lambda r: r.update(extra='unexpected'),
        ]
        for index, change in enumerate(changes):
            raw = deepcopy(original); change(raw)
            with self.subTest(case=index):
                with self.assertRaises(ValueError):
                    recipe(raw, 'a'*64)
                with self.assertRaises(ValidationError):
                    validate_face_recipe(raw)

    def test_worker_rejects_original_master_substitution(self):
        with self.assertRaises(ValueError):
            recipe(build_face_recipe('a'*64, {'nose_width': .8}), 'b'*64)

    def test_complete_bindings_required_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            for raw in ({}, {'master_sha256': 'a'*64}, {'unknown': '../asset.gz'}, []):
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    check_inputs(Path(directory), raw)

    def test_duplicate_and_nonfinite_json_rejected_even_with_matching_hash(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'face_recipe.json'
            for data in ('{"nose_width":0,"nose_width":1}', '{"nose_width":NaN}'):
                path.write_text(data)
                with self.assertRaises(ValueError):
                    read_json(path, sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
