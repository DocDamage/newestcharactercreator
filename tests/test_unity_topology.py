"""Topology identity/security logic; index fixtures are not Blender evidence."""
from copy import deepcopy
from dataclasses import replace
import unittest
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_topology import UnityQuadSource
from fixtures.unity_topology_logic import topology,excessive_valence_arguments


class UnityTopologyTests(unittest.TestCase):
    def test_roundtrip_covers_uv_duplicates_and_original_face_order(self):
        original=topology();self.assertEqual(UnityQuadSource.from_bytes(canonical_bytes(original.to_dict())),original)
        self.assertEqual(original.adjacency()[2],((0,2),(1,1)))
        self.assertNotEqual(original.sha256,replace(original,master_sha256='c'*64).sha256)

    def test_missing_bool_duplicate_degenerate_and_loose_ids_reject(self):
        original=topology()
        for changes in ({'native_source':(0,1,2,3,4,4)}, {'native_source':(True,1,2,3,4,5)},
                        {'quads':((0,1,2,2),)}, {'quads':(original.quads[0],)*2},
                        {'quads':(original.quads[0],)}, {'source_vertices':True}, {'source_vertices':100001},
                        {'bone_names':original.bone_names[:-1]}, {'shape_names':('bad',)*12},
                        {'bone_names':([],)*163}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):replace(original,**changes)

    def test_nonmanifold_and_inconsistent_winding_reject(self):
        original=topology()
        with self.assertRaisesRegex(ValidationError,'winding'):replace(original,quads=((0,1,2,3),(2,3,5,4)))
        with self.assertRaisesRegex(ValidationError,'nonmanifold'):
            replace(original,quads=(*original.quads,(2,3,4,0)))

    def test_wire_cannot_change_schema_identity_counts_or_inject_extra_fields(self):
        for key,value in [('schema_version',True),('native_vertices',99),('rig_family','UNIVERSAL'),('policy','other'),('extra',True)]:
            raw=deepcopy(topology().to_dict());raw[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):UnityQuadSource.from_dict(raw)
        for data in (b'{"schema_version":1,"schema_version":1}',b'{"source_vertices":NaN}',b'\xff'):
            with self.assertRaises(ValidationError):UnityQuadSource.from_bytes(data)

    def test_structurally_valid_ring_cannot_exceed_gpu_work_budget(self):
        with self.assertRaisesRegex(ValidationError,'work budget'):
            replace(topology(),**excessive_valence_arguments())
