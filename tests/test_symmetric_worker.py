"""Independent intake parity only; real mathutils is exercised in Blender CI."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from blender_bridge.native_symmetric_policy import parse_symmetric, load_symmetric
from ucc.animations.symmetric_fit import read_symmetric_plan
from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest
from ucc.animations.symmetric_fit import BASE_HASHES as LAYER_HASHES
from blender_bridge.native_fit_policy import checked_job, job_hashes
from fixtures.symmetric_fit_contract import fixture


def worker_base(base):
    return {'targets': list(base.targets), 'chain': base.chain, 'descendants': list(base.hand_descendants),
            'offsets': list(base.offsets), 'maximum': base.maximum_offset, 'fps': base.fps,
            'hand_rotations': base.hand_rotations, 'policy': base.policy, 'bindings': dict(base.bindings)}


class SymmetricWorkerTests(unittest.TestCase):
    def test_all_fitting_operations_require_the_complete_optional_base_identity(self):
        for operation in ('fit_native_fbx_body', 'measure_native_fit', 'verify_native_fit', 'cache_native_fit'):
            options = {k: 'a'*64 for k in job_hashes(operation) | LAYER_HASHES}
            request = JobRequest.new(operation, input_project='candidate.blend', options=options).as_dict()
            self.assertEqual(checked_job(request), options)
            for fault in ('missing_base', 'bad_base_hash', 'unknown', 'source_only', 'wrong_path'):
                bad = deepcopy(request)
                if fault == 'missing_base': del bad['options']['base_fitted_sha256']
                if fault == 'bad_base_hash': bad['options']['base_fitted_sha256'] = True
                if fault == 'unknown': bad['options']['allow_overlap'] = True
                if fault == 'source_only': del bad['options']['fit_sha256']
                if fault == 'wrong_path': bad['input_project'] = 'base_fitted_motion.blend'
                with self.subTest(operation=operation, fault=fault):
                    with self.assertRaises(ValidationError): JobRequest.from_dict(bad)
                    with self.assertRaises(ValueError): checked_job(bad)

    def test_all_anatomical_operations_keep_source_and_layer_boundaries_closed(self):
        from blender_bridge import body_contact_review, body_contact_areas, skin_inclusion_review, anatomical_review, complete_anatomical_review
        families = ((body_contact_review, body_contact_review.checked_body_job),
                    (body_contact_areas, body_contact_areas.checked_area_job),
                    (skin_inclusion_review, skin_inclusion_review.checked_skin_job),
                    (anatomical_review, anatomical_review.checked_anatomical_job),
                    (complete_anatomical_review, complete_anatomical_review.checked_complete_job))
        for module, check in families:
            for operation, fields in module.OPERATIONS.items():
                options = {k: 'a'*64 for k in fields | LAYER_HASHES}
                request = {'job_id': '66513899-f4e4-4738-82e5-0e22cd97a191', 'operation': operation,
                           'protocol_version': 1, 'input_project': 'candidate.blend', 'options': options}
                if 'native' in operation:
                    with self.subTest(operation=operation):
                        with self.assertRaises(ValidationError): JobRequest.from_dict(request)
                        with self.assertRaises(ValueError): check(request)
                    continue
                JobRequest.from_dict(request); self.assertEqual(check(request), options)
                bad = deepcopy(request); del bad['options']['base_fit_report_sha256']
                with self.subTest(operation=operation):
                    with self.assertRaises(ValidationError): JobRequest.from_dict(bad)
                    with self.assertRaises(ValueError): check(bad)

    def test_published_job_schema_agrees_with_complete_optional_base_hashes(self):
        try: from jsonschema import Draft202012Validator
        except ImportError: self.skipTest('Optional JSON Schema validator unavailable')
        schema = Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text()))
        from blender_bridge.complete_anatomical_review import OPERATIONS
        families = {operation: job_hashes(operation) for operation in ('fit_native_fbx_body', 'measure_native_fit', 'verify_native_fit', 'cache_native_fit')}
        families.update({k: v for k, v in OPERATIONS.items() if 'fitted' in k})
        for operation, fields in families.items():
            options = {k: 'a'*64 for k in fields | LAYER_HASHES}
            request = JobRequest.new(operation, input_project='candidate.blend', options=options).as_dict()
            schema.validate(request)
            for key in LAYER_HASHES:
                bad = deepcopy(request); del bad['options'][key]
                with self.subTest(operation=operation, key=key): self.assertTrue(list(schema.iter_errors(bad)))

    def test_published_layer_schema_rejects_unknown_and_partial_control_structures(self):
        try: from jsonschema import Draft202012Validator
        except ImportError: self.skipTest('Optional JSON Schema validator unavailable')
        schema = Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/native-symmetric-fit.v1.schema.json').read_text()))
        data = fixture()[0]; schema.validate(data)
        for fault in ('unknown', 'missing_base', 'missing_side', 'missing_clavicle', 'bool', 'cropped', 'extra_row'):
            bad = deepcopy(data)
            if fault == 'unknown': bad['allow_collision'] = True
            if fault == 'missing_base': del bad['bindings']['base_fitted_sha256']
            if fault == 'missing_side': del bad['chains']['left']
            if fault == 'missing_clavicle': del bad['frames'][1]['left_clavicle_rotation_world_degrees']
            if fault == 'bool': bad['frames'][1]['left_offset_world'][0] = True
            if fault == 'cropped': bad['frames'] = bad['frames'][:4]
            if fault == 'extra_row': bad['frames'][1]['scale'] = [1., 1., 1.]
            with self.subTest(fault=fault): self.assertTrue(list(schema.iter_errors(bad)))

    def test_independent_intakes_agree_on_both_complete_branches(self):
        data, bindings, baseline, profile, parents, base, *_ = fixture()
        core = read_symmetric_plan(data, bindings, baseline, profile, parents, base)
        worker = parse_symmetric(data, bindings, baseline, profile, parents, worker_base(base))
        self.assertEqual(worker['targets'], list(core.targets))
        self.assertEqual(worker['active_frames'], list(core.active_frames))
        self.assertEqual(worker['render_frames'], list(core.render_frames))
        for name in ('left', 'right'):
            side = getattr(core, name); actual = worker[name]
            self.assertEqual(actual['chain'], side.arm.chain)
            self.assertEqual(actual['clavicle'], side.clavicle)
            self.assertEqual(actual['branch'], list(side.branch))
            self.assertEqual(actual['descendants'], list(side.arm.hand_descendants))
            self.assertEqual(actual['offsets'], list(side.arm.offsets))
            self.assertEqual(actual['clavicle_rotations'], list(side.rotations))
            self.assertEqual(tuple(actual['hand_rotations']), side.arm.hand_rotations)

    def test_independent_worker_rejects_wrong_identity_hierarchy_and_controls(self):
        cases = ('source', 'base_sha', 'missing_sha', 'bad_sha', 'schema_bool', 'fps_bool', 'space', 'policy',
                 'base_identity', 'base_order', 'base_policy', 'base_overlap', 'cross_arm', 'cycle', 'two_roots',
                 'missing_helper', 'extra_descendant', 'chain_root', 'chain_hand', 'skin', 'neutral', 'cropped',
                 'reordered', 'frame_bool', 'unknown', 'noop', 'vector_bool', 'nan', 'inf', 'huge', 'wrong_vector',
                 'offset_bound', 'angle_bound', 'endpoint', 'speed', 'acceleration', 'angular_speed', 'angular_accel',
                 'missing_renders', 'render_bool', 'render_duplicate', 'render_inactive')
        for case in cases:
            data, bindings, baseline, profile, parents, base, *_ = deepcopy(fixture())
            if case == 'source': data['bindings']['source_sha256'] = 'c'*64
            if case == 'base_sha': data['bindings']['base_fitted_sha256'] = 'c'*64
            if case == 'missing_sha': del bindings['base_fit_report_sha256']
            if case == 'bad_sha': bindings['base_fit_report_sha256'] = 'X'*64
            if case == 'schema_bool': data['schema_version'] = True
            if case == 'fps_bool': data['fps'] = True
            if case == 'space': data['coordinate_space'] = 'LOCAL'
            if case == 'policy': data['policy'] = 'DISABLE_CHECKS'
            if case == 'base_identity': base = replace(base, bindings=tuple((k, 'c'*64) for k, _ in base.bindings))
            if case == 'base_order': base = replace(base, targets=tuple(reversed(base.targets)))
            if case == 'base_policy': base = replace(base, policy='UNKNOWN')
            if case == 'base_overlap': data['frames'][2]['left_clavicle_rotation_world_degrees'] = [.0001, 0., 0.]
            if case == 'cross_arm': parents['lowerL'] = 'upperR'
            if case == 'cycle': parents['helperL'] = 'handL'
            if case == 'two_roots': parents['clavL'] = None
            if case == 'missing_helper': del parents['helperL']
            if case == 'extra_descendant': parents['head'] = 'clavL'
            if case == 'chain_root': data['chains']['left']['clavicle'] = 'root'
            if case == 'chain_hand': data['chains']['left']['hand'] = 'handR'
            if case == 'skin': profile['skin_deformation_policy'] = 'NONE'
            if case == 'neutral': profile['mesh_strain_reference'] = 'FIRST_POSE'
            if case == 'cropped': data['frames'].pop()
            if case == 'reordered': data['frames'].reverse()
            if case == 'frame_bool': data['frames'][0]['frame'] = True
            if case == 'unknown': data['frames'][0]['scale'] = [1., 1., 1.]
            if case == 'noop':
                for row in data['frames']:
                    for key in row:
                        if key != 'frame': row[key] = [0., 0., 0.]
            values = {'vector_bool': [True, 0., 0.], 'nan': [float('nan'), 0., 0.], 'inf': [float('inf'), 0., 0.],
                      'huge': [10**400, 0., 0.], 'wrong_vector': [0., 0.], 'offset_bound': [.081, 0., 0.]}
            if case in values: data['frames'][13]['left_offset_world'] = values[case]
            if case == 'angle_bound': data['frames'][13]['left_clavicle_rotation_world_degrees'] = [9., 9., 9.]
            if case == 'endpoint': data['frames'][-1]['left_offset_world'] = [.0001, 0., 0.]
            if case in ('speed', 'acceleration', 'angular_speed', 'angular_accel'):
                angular = case.startswith('angular')
                key = 'left_clavicle_rotation_world_degrees' if angular else 'left_offset_world'
                amount = {'speed': .02, 'acceleration': .004, 'angular_speed': 6., 'angular_accel': 2.}[case]
                for row in data['frames']: row[key] = [0., 0., 0.]
                data['frames'][13][key] = [amount, 0., 0.]
            if case == 'missing_renders': data['render_frames'] = None
            if case == 'render_bool': data['render_frames'][0] = True
            if case == 'render_duplicate': data['render_frames'][1] = 1
            if case == 'render_inactive': data['render_frames'] = [1, 2, 3, 4, 5]
            with self.subTest(case=case):
                with self.assertRaises(ValidationError): read_symmetric_plan(data, bindings, baseline, profile, parents, base)
                with self.assertRaises(ValueError): parse_symmetric(data, bindings, baseline, profile, parents, worker_base(base))

    def test_staged_loader_hashes_and_revalidates_base_before_layer(self):
        data, bindings, baseline, profile, parents, base, *_ = fixture()
        base_document = {'schema_version': 1, 'policy': base.policy, 'bindings': dict(base.bindings),
                         'coordinate_space': 'BLENDER_WORLD_METERS', 'fps': base.fps,
                         'chain': {'side': 'right', **dict(zip(('upper_arm', 'forearm', 'hand'), base.chain))},
                         'frames': [{'frame': i, 'offset_world': list(v)} for i, v in enumerate(base.offsets, 1)]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); payload = json.dumps(base_document).encode()
            bindings['base_fit_policy_sha256'] = sha256(payload).hexdigest(); data['bindings'] = dict(bindings)
            (root/'base_contact_fit.json').write_bytes(payload)
            payload = json.dumps(data).encode(); (root/'contact_fit.json').write_bytes(payload)
            options = {**bindings, 'fit_sha256': sha256(payload).hexdigest()}
            self.assertEqual(load_symmetric(root, options, baseline, profile, parents)['policy'], data['policy'])
            (root/'base_contact_fit.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'SHA-256'): load_symmetric(root, options, baseline, profile, parents)


if __name__ == '__main__': unittest.main()
