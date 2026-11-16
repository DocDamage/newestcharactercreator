"""Scalar native storage/source-derived bounds, no model or engine fixtures."""
from math import nextafter,inf
import unittest
from ucc.core.errors import ValidationError
from ucc.export.unity_skin_precision import (validate_native_weights,deformation_error_bound,validate_deformation_error,
    MAX_DEFORMATION_ERROR_M,ARITHMETIC_POSITION_BOUND_M)


class UnitySkinPrecisionTests(unittest.TestCase):
    def test_preserves_small_positive_bones_and_complete_identity(self):
        source=(('head',.9999),('eye',.0001))
        validate_native_weights(source,source)
        for actual in ((('head',1.),),(('head',.9999),('other',.0001))):
            with self.assertRaisesRegex(ValidationError,'lost or reassigned'):validate_native_weights(source,actual)

    def test_nonunit_duplicate_zero_nonfinite_and_broad_errors_reject(self):
        source=(('a',.5),('b',.5))
        for actual in ((('a',.5),('a',.5)),(('a',1.),('b',0.)),(('a',.4),('b',.4)),(('a',True),),
                (('a',float('nan')),('b',.5)),(('a',.51),('b',.49)),tuple((str(i),1/9) for i in range(9))):
            with self.subTest(actual=actual),self.assertRaises(ValidationError):validate_native_weights(source,actual)

    def test_native_remainder_budget_is_not_exact_float_claim(self):
        source=(('a',.5),('b',.5));actual=(('a',32768/65535),('b',32767/65535))
        result=validate_native_weights(source,actual)
        self.assertGreater(result.maximum_error,0);self.assertLess(result.absolute_error_sum,result.absolute_error_bound)

    def test_source_derived_position_bound_cancels_common_translation(self):
        source=(('a',.5),('b',.5));actual=(('a',32768/65535),('b',32767/65535))
        points={'a':(0.,0.,0.),'b':(.1,0.,0.)}
        bound=deformation_error_bound(source,actual,points)
        shifted=deformation_error_bound(source,actual,{'a':(100.,2.,3.),'b':(100.1,2.,3.)})
        self.assertAlmostEqual(bound,shifted,places=15)
        self.assertAlmostEqual(bound,abs(actual[0][1]-.5)*.1+ARITHMETIC_POSITION_BOUND_M)
        with self.assertRaises(ValidationError):deformation_error_bound(source,actual,{'a':(0.,0.,0.)})

    def test_both_spatial_and_weight_derived_limits_are_enforced(self):
        validate_deformation_error(1e-6,2e-6)
        with self.assertRaises(ValidationError):validate_deformation_error(3e-6,2e-6)
        with self.assertRaises(ValidationError):validate_deformation_error(nextafter(MAX_DEFORMATION_ERROR_M,inf),1.)
        for bad in (float('nan'),True,-1.):
            with self.assertRaises(ValidationError):validate_deformation_error(bad,1.)

    def test_missing_or_nonfinite_pose_boundary_is_explicit(self):
        row=(('root',1.),)
        for points in (None,[],{'root':(float('inf'),0.,0.)},{'root':[0.,0.,0.]},{'root':(True,0.,0.)}):
            with self.subTest(points=points),self.assertRaises(ValidationError):deformation_error_bound(row,row,points)
