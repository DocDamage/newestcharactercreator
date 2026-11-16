"""Analytic generated source/native mathematical faults; no engine execution."""
import math
import unittest
from fixtures.unreal_bind_evidence import fixture_data
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.export.unreal_native_data import decode_native
from ucc.export.unreal_bind_math import geometry,verify_bind,morphs,verify_corner_normals,verify_numeric_weights


class UnrealBindMathTests(unittest.TestCase):
    def setUp(self):
        self.source,self.normals,raw,self.spec=fixture_data();self.native=decode_native(raw)
        self.names=self.source['source_to_unreal_bone_names'];self.mapping=list(range(6))

    def test_declared_axes_units_and_oriented_surface(self):
        mapping,report=geometry(self.source,self.native)
        self.assertEqual(mapping,self.mapping);self.assertEqual(report['maximum_correspondence_error_cm'],0)

    def test_winding_reversal_not_erased_by_sorting(self):
        self.native['indices'][1],self.native['indices'][2]=self.native['indices'][2],self.native['indices'][1]
        with self.assertRaises(ValidationError):geometry(self.source,self.native)

    def test_exact_uv_rejects_one_float32_ulp(self):
        self.native['uv0'][0]=(.2500000298023224,.25)
        with self.assertRaises(ValidationError):geometry(self.source,self.native)

    def test_missing_or_ambiguous_source_correspondence_rejected(self):
        self.source['vertices'][1]=self.source['vertices'][0]
        with self.assertRaises(ValidationError):geometry(self.source,self.native)

    def test_full_bone_frames_and_inverse_from_declared_source(self):
        report=verify_bind(self.source,self.native,self.names)
        self.assertEqual(report['maximum_native_full_bind_basis_endpoint_error_cm'],0)

    def test_changed_valid_bone_orientation_rejected(self):
        self.native['bones'][0]['local_trs_float64_quaternion_xyzw_translation_scale'][:4]=[0,0,math.sin(.01),math.cos(.01)]
        with self.assertRaises(ValidationError):verify_bind(self.source,self.native,self.names)

    def test_inverse_bind_tamper_rejected_with_unchanged_heads(self):
        row=list(self.native['inverse_bind_matrices'][0]);row[0]=1.01;self.native['inverse_bind_matrices'][0]=tuple(row)
        with self.assertRaises(ValidationError):verify_bind(self.source,self.native,self.names)

    def test_morph_sparse_omission_is_checked_as_zero(self):
        self.native['morphs']['UCC_TestControl']={}
        with self.assertRaises(ValidationError):morphs(self.source,self.native,self.mapping)

    def test_normal_direction_flip_rejected(self):
        self.native['normals'][0]=tuple(-v for v in self.native['normals'][0])
        with self.assertRaises(ValidationError):verify_corner_normals(self.source,self.native,self.mapping,self.normals)

    def test_original_unnormalized_source_weights_are_normalized(self):
        result=verify_numeric_weights(self.source,self.native,self.mapping,self.names)
        self.assertTrue(result['passed']);self.assertEqual(result['maximum_normalized_weight_error'],0)

    def test_sum_preserving_weight_tamper_exceeds_fixed_cap(self):
        self.native['influences'][0]=[(0,27214),(1,38321)]
        self.assertFalse(verify_numeric_weights(self.source,self.native,self.mapping,self.names)['passed'])

    def test_math_checkpoint_interrupts_without_data_normalization(self):
        def cancelled():raise ProjectStorageError('cancelled')
        with self.assertRaises(ProjectStorageError):geometry(self.source,self.native,check=cancelled)


if __name__=='__main__':unittest.main()
