"""Malicious accessor and preservation checks; fixtures are not MPFB proof."""
from pathlib import Path
import json
import struct
import tempfile
import unittest

from fixtures.godot_skin_glb import skin_document, write_skin
from ucc.export.godot_skin_evidence import inspect_diagnostic_skin, GodotSkinEvidenceError


class GodotSkinEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'synthetic_skin_accessors_only.glb'

    def test_packed_scalar_indices_support_uint8_uint16_uint32_and_boundaries(self):
        from ucc.export.godot_skin_evidence import _DenseSkin
        for component, fmt in [(5121,'B'),(5123,'H'),(5125,'I')]:
            document,binary,_=skin_document()
            while len(binary)%4:binary.append(0)
            offset=len(binary);payload=struct.pack('<'+fmt*3,0,1,2);binary.extend(payload)
            document['buffers'][0]['byteLength']=len(binary)
            view=len(document['bufferViews']);document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(payload)})
            accessor=len(document['accessors']);document['accessors'].append({'bufferView':view,'componentType':component,'count':3,'type':'SCALAR'})
            write_skin(self.path,document,binary)
            self.assertEqual(_DenseSkin(self.path).rows(accessor,'SCALAR',(5121,5123,5125)),[(0,),(1,),(2,)])
            document['accessors'][accessor]['count']=4;write_skin(self.path,document,binary)
            with self.assertRaises(GodotSkinEvidenceError):_DenseSkin(self.path).rows(accessor,'SCALAR',(component,))
            document['accessors'][accessor]['count']=3;document['bufferViews'][view]['byteStride']=3;write_skin(self.path,document,binary)
            with self.assertRaises(GodotSkinEvidenceError):_DenseSkin(self.path).rows(accessor,'SCALAR',(component,))

    def test_all_eight_weights_and_split_vertex_identity_are_preserved(self):
        document, binary, source = skin_document(); write_skin(self.path, document, binary)
        proof, actual = inspect_diagnostic_skin(self.path, source)
        self.assertEqual(proof['serialized_vertices'], 3)
        self.assertEqual(proof['source_vertices'], 2)
        self.assertEqual(proof['max_weight_serialization_error'], 0.)
        self.assertEqual(actual, [dict(row) for row in source])
        self.assertIs(proof['engine_import_verified'], False)

    def test_positive_influence_loss_cannot_hide_behind_valid_container(self):
        document, binary, source = skin_document()
        offset = document['bufferViews'][3]['byteOffset']; struct.pack_into('<f', binary, offset, 0.)
        write_skin(self.path, document, binary)
        with self.assertRaisesRegex(GodotSkinEvidenceError, 'dropped'):
            inspect_diagnostic_skin(self.path, source)

    def test_nonfinite_and_changed_serialized_weights_reject(self):
        for value in (float('nan'), float('inf'), -.1, .15):
            document, binary, source = skin_document()
            struct.pack_into('<f', binary, document['bufferViews'][3]['byteOffset'], value)
            write_skin(self.path, document, binary)
            with self.subTest(value=value), self.assertRaises(GodotSkinEvidenceError):
                inspect_diagnostic_skin(self.path, source)

    def test_view_escapes_misalignment_bad_strides_and_boolean_offsets_reject(self):
        corruptions = [('byteOffset', 1000000), ('byteOffset', True), ('byteOffset', -1),
                       ('byteOffset', 1), ('byteStride', 3), ('byteStride', 256), ('byteLength', 1)]
        for key, value in corruptions:
            document, binary, source = skin_document(); document['bufferViews'][0][key] = value
            write_skin(self.path, document, binary)
            with self.subTest(key=key, value=value), self.assertRaises(GodotSkinEvidenceError):
                inspect_diagnostic_skin(self.path, source)

    def test_external_buffer_duplicate_fields_and_malformed_asset_reject(self):
        for fault in ('external', 'duplicate', 'asset'):
            document, binary, source = skin_document(); text = None
            if fault == 'external': document['buffers'][0]['uri'] = '../outside.bin'
            if fault == 'asset': document['asset'] = []
            if fault == 'duplicate': text = json.dumps(document).replace('"version": "2.0"', '"version":"2.0","version":"2.0"')
            write_skin(self.path, document, binary, json_text=text)
            with self.subTest(fault=fault), self.assertRaises(GodotSkinEvidenceError):
                inspect_diagnostic_skin(self.path, source)

    def test_noncanonical_original_evidence_and_duplicate_bones_reject(self):
        for fault in ('nan', 'bool', 'duplicate_source', 'nonunit', 'bone_name', 'joint_id'):
            document, binary, source = skin_document()
            if fault == 'nan': source[0][0][1] = float('nan')
            if fault == 'bool': source[0][0][1] = True
            if fault == 'duplicate_source': source[0][1][0] = source[0][0][0]
            if fault == 'nonunit': source[0][0][1] = .25
            if fault == 'bone_name': document['nodes'][1]['name'] = 'bone0'
            if fault == 'joint_id': document['skins'][0]['joints'][1] = 0
            write_skin(self.path, document, binary)
            with self.subTest(fault=fault), self.assertRaises(GodotSkinEvidenceError):
                inspect_diagnostic_skin(self.path, source)

    def test_missing_source_vertex_is_not_accepted_as_smaller_success(self):
        document, binary, source = skin_document()
        struct.pack_into('<2f', binary, 8, 0., 1.)
        write_skin(self.path, document, binary)
        with self.assertRaisesRegex(GodotSkinEvidenceError, 'lost source vertices'):
            inspect_diagnostic_skin(self.path, source)

    def test_json_float_component_type_and_boolean_buffer_reference_reject(self):
        for fault in ('component_float', 'buffer_bool'):
            document, binary, source = skin_document()
            if fault == 'component_float':
                document['accessors'][0]['componentType'] = 5126.0
            else:
                document['bufferViews'][0]['buffer'] = False
            write_skin(self.path, document, binary)
            with self.subTest(fault=fault), self.assertRaises(GodotSkinEvidenceError):
                inspect_diagnostic_skin(self.path, source)


if __name__ == '__main__':
    unittest.main()
