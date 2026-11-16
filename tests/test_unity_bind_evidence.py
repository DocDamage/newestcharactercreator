"""Logic-only boundary checks; actual body admission is recorded separately."""
from copy import deepcopy
import unittest
from ucc.core.errors import ValidationError
from ucc.export.unity_bind_evidence import triangle,cyclic,number,vector,correspondence,compare_saved_bind
from fixtures.unity_bind_logic import SOURCE_POINTS,NATIVE_POINTS


class UnityBindLogicTests(unittest.TestCase):
    def test_triangle_rotation_keeps_orientation_and_rejects_invalid_indices(self):
        self.assertEqual(cyclic((2,4,1)),cyclic((4,1,2)))
        self.assertNotEqual(cyclic((2,4,1)),cyclic((2,1,4)))
        for value in ([0,1,1],[True,1,2],[0,1,5],[0,1],['0',1,2],[[0],1,2]):
            with self.assertRaises(ValidationError):triangle(value,5)

    def test_numbers_vectors_reject_nonfinite_boolean_unknown_or_missing_components(self):
        for value in (True,None,float('nan'),float('inf'),10**10000):
            with self.assertRaises(ValidationError):number(value)
        for value in ({'x':0,'y':0},{'x':0,'y':0,'z':0,'w':1},[0,0,0],{'x':False,'y':0,'z':0}):
            with self.assertRaises(ValidationError):vector(value)

    def test_correspondence_preserves_seams_and_requires_complete_unique_source_coverage(self):
        ids,error=correspondence(SOURCE_POINTS,NATIVE_POINTS)
        self.assertEqual(ids,(2,0,1,0));self.assertEqual(error,0)
        for source,native in [(SOURCE_POINTS,SOURCE_POINTS[:2]),(SOURCE_POINTS,[(1.,0.,0.)]),
                              ([SOURCE_POINTS[0],SOURCE_POINTS[0]],[SOURCE_POINTS[0]])]:
            with self.assertRaises(ValidationError):correspondence(source,native)

    def test_saved_native_data_exact_and_component_required_while_rest_values_are_separate(self):
        before={'mode':'stage','baked':'evaluated separately','runtime_component_present':False,'native':{'weights':[1,2]}}
        after={**deepcopy(before),'mode':'reopen','runtime_component_present':True,'baked':'fresh evaluation'}
        compare_saved_bind(before,after)
        after['native']['weights'][0]=3
        with self.assertRaises(ValidationError):compare_saved_bind(before,after)
        with self.assertRaises(ValidationError):compare_saved_bind(before,deepcopy(before))
