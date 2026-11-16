"""Independent per-corner/seam UV logic; fixtures do not certify real exports."""
from copy import deepcopy
import unittest
from ucc.core.errors import ValidationError
from ucc.export.godot_surface_uv import verify_corner_uvs,glb_corner_reference
from fixtures.godot_uv_logic import POLYGONS,UVS,IDS,IMPORTED_UVS,TRIANGLES


class SurfaceUVTests(unittest.TestCase):
    def verify(self,**changes):
        values=dict(polygons=POLYGONS,corner_uvs=UVS,imported_ids=IDS,imported_uvs=IMPORTED_UVS,triangle_indices=TRIANGLES)
        values.update(changes)
        return verify_corner_uvs(**values,check=lambda:None)

    def test_complete_seam_sides_and_v_convention_have_closed_observations(self):
        result=self.verify();self.assertEqual(result['maximum_uv_component_error'],0.)
        self.assertEqual((result['source_polygons'],result['source_corners'],result['source_vertex_uv_pairs'],result['imported_vertices']),(2,8,8,8))
        self.assertFalse(result['material_appearance_verified']);self.assertFalse(result['engine_import_verified'])

    def test_collapsed_seam_or_wrong_v_cannot_pass_global_uv_coverage(self):
        changed=list(IMPORTED_UVS);changed[4]=changed[1]
        with self.assertRaisesRegex(ValidationError,'corner differs'):self.verify(imported_uvs=changed)
        with self.assertRaisesRegex(ValidationError,'corner differs'):self.verify(imported_uvs=UVS)
        changed=list(IMPORTED_UVS);changed[4],changed[1]=changed[1],changed[4]
        self.assertEqual(set(changed),set(IMPORTED_UVS))
        with self.assertRaises(ValidationError):self.verify(imported_uvs=changed)

    def test_missing_unused_ambiguous_and_out_of_range_geometry_reject(self):
        cases=[{'triangle_indices':TRIANGLES[:-3]}, {'imported_ids':IDS+(0,), 'imported_uvs':IMPORTED_UVS+(IMPORTED_UVS[0],)},
            {'triangle_indices':TRIANGLES[:-1]+(999,)}, {'imported_ids':IDS[:-1]+(999,)},
            {'polygons':((0,1,2,3),(0,1,2,3))}, {'polygons':((0,1,2,2),(1,4,5,2))}]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ValidationError):self.verify(**case)

    def test_nonfinite_unbounded_malformed_uv_data_reject(self):
        for bad in ((float('nan'),0.),(float('inf'),0.),(101.,0.),(True,0.),(0.,),None):
            changed=list(IMPORTED_UVS);changed[0]=bad
            with self.subTest(bad=bad),self.assertRaises(ValidationError):self.verify(imported_uvs=changed)
        with self.assertRaises(ValidationError):self.verify(polygons=None)

    def test_cancellation_callback_interrupts_before_admission(self):
        def stop():raise RuntimeError('UNIT_CANCELLED')
        with self.assertRaisesRegex(RuntimeError,'UNIT_CANCELLED'):
            verify_corner_uvs(POLYGONS,UVS,IDS,IMPORTED_UVS,TRIANGLES,check=stop)

    def test_glb_reference_keeps_each_seam_side_for_engine_comparison(self):
        reference=glb_corner_reference(POLYGONS,list(IDS),list(IMPORTED_UVS),list(TRIANGLES),check=lambda:None)
        self.assertEqual(tuple(reference),UVS)
        self.assertNotEqual(reference[1],reference[4])

    def test_glb_reference_rejects_inconsistent_uvs_within_one_polygon(self):
        ids=list(IDS)+( [0] );uvs=list(IMPORTED_UVS)+[(.2,1.)];triangles=list(TRIANGLES);triangles[3]=8
        with self.assertRaisesRegex(ValidationError,'corner UV reference'):
            glb_corner_reference(POLYGONS,ids,uvs,triangles,check=lambda:None)


if __name__=='__main__':unittest.main()
