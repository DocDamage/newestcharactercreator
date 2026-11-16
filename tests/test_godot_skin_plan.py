"""Skin encoding logic only; synthetic accessors are never MPFB evidence."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from fixtures.godot_skin_glb import skin_document, write_skin
from ucc.export.godot_skin_plan import build_skin_plan, unit_sum_codes, GodotSkinPlanError


class GodotSkinPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'synthetic_accessor_plan_only.glb'

    def test_uv_independent_duplicate_vertices_share_only_identical_corrections(self):
        doc, binary, _ = skin_document()
        del doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_1']
        write_skin(self.path, doc, binary)
        plan = build_skin_plan(self.path)
        self.assertEqual(plan.vertex_count, 3)
        self.assertEqual(sorted(row['count'] for row in plan.entries.values()), [1, 2])
        self.assertEqual(sum(row['count'] for row in plan.entries.values()), 3)
        for row in plan.entries.values():
            self.assertEqual(sum(row['codes'].values()), 65535)
            self.assertEqual(len(row['codes']), 8)
            self.assertTrue(all(code > 0 for code in row['codes'].values()))
        self.assertIs(plan.to_dict()['diagnostic_UV_required'], False)
        self.assertIs(plan.to_dict()['engine_import_verified'], False)
        self.assertEqual(json.loads(json.dumps(plan.to_dict()))['schema_version'], 1)

    def test_corrective_names_require_explicit_complete_frame_admission(self):
        from ucc.core.expressions import TARGETS
        doc, binary, _ = skin_document()
        names = [target.key_name for target in TARGETS]
        names += [f'UCC_POSE_CORRECTION_V1_f{frame:04d}' for frame in range(1, 301)]
        doc['meshes'][0]['extras'] = {'targetNames': names}
        write_skin(self.path, doc, binary)
        with self.assertRaises(GodotSkinPlanError): build_skin_plan(self.path)
        self.assertEqual(build_skin_plan(self.path, corrective_frames=300).vertex_count, 3)
        for frames in (True, -1, 601, 300., 299):
            with self.subTest(frames=frames), self.assertRaises(GodotSkinPlanError):
                build_skin_plan(self.path, corrective_frames=frames)
        doc['meshes'][0]['extras']['targetNames'][-1] = 'arbitrary_script_metadata'
        write_skin(self.path, doc, binary)
        with self.assertRaises(GodotSkinPlanError): build_skin_plan(self.path, corrective_frames=300)

    def test_dense_scalar_times_share_bounds_and_nonfinite_rejection(self):
        from ucc.export.godot_skin_evidence import _DenseSkin, GodotSkinEvidenceError
        doc, binary, _ = skin_document()
        position_index = doc['meshes'][0]['primitives'][0]['attributes']['POSITION']
        accessor = doc['accessors'][position_index]
        accessor['type'] = 'SCALAR'
        view = doc['bufferViews'][accessor['bufferView']]
        view['byteStride'] = 12
        write_skin(self.path, doc, binary)
        decoded = _DenseSkin(self.path).rows(position_index, 'SCALAR', (5126,))
        self.assertEqual(len(decoded), 3)
        self.assertEqual(decoded, [(struct.unpack_from('<f', binary, view['byteOffset']+index*12)[0],) for index in range(3)])
        struct.pack_into('<f', binary, view['byteOffset'], float('nan'))
        write_skin(self.path, doc, binary)
        with self.assertRaisesRegex(GodotSkinEvidenceError, 'Nonfinite'):
            _DenseSkin(self.path).rows(position_index, 'SCALAR', (5126,))

    def test_equal_import_signatures_with_different_required_codes_reject(self):
        doc, binary, _ = skin_document()
        struct.pack_into('<f', binary, doc['bufferViews'][3]['byteOffset']+2*16, .1249995)
        struct.pack_into('<f', binary, doc['bufferViews'][4]['byteOffset']+2*16+12, .1250005)
        write_skin(self.path, doc, binary)
        with self.assertRaisesRegex(GodotSkinPlanError, 'Ambiguous'):
            build_skin_plan(self.path)

    def test_vertex_permutation_does_not_change_match_entries(self):
        doc, binary, _ = skin_document(); write_skin(self.path, doc, binary)
        before = build_skin_plan(self.path)
        for view in doc['bufferViews']:
            start = view['byteOffset']; width = view['byteLength']//3
            rows = [binary[start+i*width:start+(i+1)*width] for i in range(3)]
            binary[start:start+view['byteLength']] = rows[2]+rows[0]+rows[1]
        write_skin(self.path, doc, binary)
        after = build_skin_plan(self.path)
        self.assertEqual(before.entries, after.entries)
        self.assertNotEqual(before.candidate_sha256, after.candidate_sha256)

    def test_unrepresentable_original_influence_never_disappears(self):
        with self.assertRaisesRegex(GodotSkinPlanError, 'never prune'):
            unit_sum_codes({'root': 1-1e-12, 'finger.L': 1e-12})

    def test_sum_error_is_removed_without_dropping_or_reassigning_bones(self):
        weights = {f'bone{i}': .125 for i in range(8)}
        codes = unit_sum_codes(weights)
        self.assertEqual(set(codes), set(weights))
        self.assertEqual(sum(codes.values()), 65535)
        self.assertEqual(codes['bone7'], 8191)
        self.assertTrue(all(codes[f'bone{i}'] == 8192 for i in range(7)))
        self.assertEqual(codes, unit_sum_codes(dict(reversed(list(weights.items())))))

    def test_malformed_weights_and_unsafe_match_names_reject(self):
        for weights in [{}, {'root': True}, {'root': float('nan')}, {'root': float('inf')},
                        {'root': -.1}, {'root': .9}, {'root=1;other': 1.},
                        {f'bone{i}': 1/9 for i in range(9)}]:
            with self.subTest(weights=weights), self.assertRaises(GodotSkinPlanError):
                unit_sum_codes(weights)

    def test_missing_positions_required_extensions_and_duplicate_bones_reject(self):
        for fault in ['position', 'extension', 'bone_name', 'duplicate_joint', 'mode']:
            doc, binary, _ = skin_document()
            if fault == 'position':
                del doc['meshes'][0]['primitives'][0]['attributes']['POSITION']
            if fault == 'extension':
                doc['extensionsRequired'] = ['KHR_draco_mesh_compression']
            if fault == 'bone_name':
                doc['nodes'][1]['name'] = doc['nodes'][0]['name']
            if fault == 'duplicate_joint':
                doc['skins'][0]['joints'][1] = 0
            if fault == 'mode':
                doc['meshes'][0]['primitives'][0]['mode'] = 1
            write_skin(self.path, doc, binary)
            with self.subTest(fault=fault), self.assertRaises(GodotSkinPlanError):
                build_skin_plan(self.path)

    def test_external_images_optional_extensions_and_script_extras_reject(self):
        for fault in ['external_image', 'extension', 'extras']:
            doc, binary, _ = skin_document()
            if fault == 'external_image':
                doc['images'] = [{'uri': '../../private/outside.png'}]
            if fault == 'extension':
                doc['extensionsUsed'] = ['UNREVIEWED_engine_plugin']
            if fault == 'extras':
                doc['nodes'][0]['extras'] = {'script': 'res://unreviewed.gd'}
            write_skin(self.path, doc, binary)
            with self.subTest(fault=fault), self.assertRaises(GodotSkinPlanError):
                build_skin_plan(self.path)

    def test_only_closed_canonical_mesh_morph_name_extras_are_admitted(self):
        from ucc.core.expressions import TARGETS
        doc, binary, _ = skin_document()
        doc['meshes'][0]['extras'] = {'targetNames': [target.key_name for target in TARGETS]}
        write_skin(self.path, doc, binary)
        self.assertEqual(build_skin_plan(self.path).vertex_count, 3)
        doc['meshes'][0]['extras']['script'] = 'res://unreviewed.gd'
        write_skin(self.path, doc, binary)
        with self.assertRaises(GodotSkinPlanError):
            build_skin_plan(self.path)


if __name__ == '__main__':
    unittest.main()
