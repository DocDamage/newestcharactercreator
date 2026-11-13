"""Nonshipping hand-policy boundary/math cases; no animation-pack claim."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ucc.animations.contact_fit import read_fit_plan,fit_frame,verify_fitted_frame,verify_fitted_sequence
from ucc.animations.hand_fit import POLICY
from ucc.core.errors import ValidationError
from blender_bridge.native_fit_policy import parse_fit
from blender_bridge.native_hand_fit import changed,angular_bones
from fixtures.contact_fit_contract import fixture


def hand_fixture():
    values=deepcopy(fixture());values[0]['policy']=POLICY
    for row,degrees in zip(values[0]['frames'],(0.,.1,.2,.1,0.)):
        row['hand_rotation_local_degrees']=[degrees,0.,0.]
    return values


class HandFitTests(unittest.TestCase):
    def test_optional_json_schema_closes_both_policy_row_contracts(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/native-fit.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        validator.validate(fixture()[0]);values=hand_fixture();validator.validate(values[0])
        del values[0]['frames'][2]['hand_rotation_local_degrees']
        self.assertTrue(list(validator.iter_errors(values[0])))
        values=hand_fixture();values[0]['policy']='BOUNDED_NATIVE_ARM_IK_V1'
        self.assertTrue(list(validator.iter_errors(values[0])))

    def test_local_axis_pivot_finger_rigidity_and_unrelated_bones(self):
        values=hand_fixture();poses=values[-1]
        # A rolled posed hand: local X points along world Y.
        for matrix in poses[3:5]:
            for i,v in zip((0,1,4,5),(0.,-1.,1.,0.)):matrix[i]=v
        preserved=deepcopy(poses)
        plan=read_fit_plan(*values[:5]);result=fit_frame(plan,poses,3)
        arm=deepcopy(values);arm[0]['policy']='BOUNDED_NATIVE_ARM_IK_V1'
        for row in arm[0]['frames']:del row['hand_rotation_local_degrees']
        before=fit_frame(read_fit_plan(*arm[:5]),poses,3)
        self.assertEqual(result[:3],before[:3]);self.assertEqual(result[5],poses[5])
        head=lambda m:tuple(m[i] for i in (3,7,11))
        self.assertEqual(head(result[3]),head(before[3]))
        self.assertAlmostEqual(math.dist(head(result[3]),head(result[4])),.1)
        self.assertAlmostEqual(result[4][3]-result[3][3],.1*math.sin(math.radians(.2)))
        self.assertAlmostEqual(result[4][7]-result[3][7],0.)
        verify_fitted_frame(plan,poses,result,3)
        bad=deepcopy(result);bad[4][3]+=.001
        with self.assertRaises(ValidationError):verify_fitted_frame(plan,poses,bad,3)
        self.assertEqual(poses,preserved)

    def test_screening_cache_never_reuses_a_different_hand_orientation(self):
        from blender_bridge.contact_area_probe import AreaCandidateProbe
        probe=AreaCandidateProbe.__new__(AreaCandidateProbe)
        probe._queries={};probe._cache_enabled=True;probe.cache_hits=0
        probe.area_guard=SimpleNamespace(frames=[])
        plan={'chain':('u','l','h'),'offsets':[(.01,0.,0.)],'hand_rotations':[(0.,0.,1.)]}
        with patch('blender_bridge.native_contact_probe.CandidateProbe.frame',return_value=0) as actual:
            probe.frame(plan,1);probe.frame(plan,1)
            self.assertEqual(actual.call_count,1)
            plan['hand_rotations']=[(0.,0.,2.)];probe.frame(plan,1)
            self.assertEqual(actual.call_count,2)
            plan['hand_rotations']=[];probe.frame(plan,1)
            self.assertEqual(actual.call_count,3)

    def test_hand_correction_with_zero_translation_and_fixed_endpoints(self):
        values=hand_fixture();values[0]['frames'][1]['offset_world']=[0.,0.,0.]
        core=read_fit_plan(*values[:5]);worker=parse_fit(*values[:5])
        self.assertTrue(changed(worker,2));self.assertFalse(changed(worker,1))
        self.assertEqual(angular_bones(worker),('upper','lower','hand'))
        result=fit_frame(core,values[-1],2)
        self.assertNotEqual(result[3],values[-1][3]);self.assertEqual(result[:3],values[-1][:3])
        for frame in (1,5):self.assertEqual(fit_frame(core,values[-1],frame),values[-1])

    def test_both_independent_intakes_reject_malformed_or_unbounded_rotation(self):
        cases=([True,0.,0.],[float('nan'),0.,0.],[float('inf'),0.,0.],[16.,0.,0.],[10.,10.,10.],
               [10**400,0.,0.],[0.,0.],None)
        for bad in cases:
            values=hand_fixture();values[0]['frames'][2]['hand_rotation_local_degrees']=bad
            for intake,error in ((read_fit_plan,ValidationError),(parse_fit,ValueError)):
                with self.subTest(bad=bad,intake=intake.__name__),self.assertRaises(error):intake(*values[:5])
        for mode in ('missing','extra','endpoint','zero','speed','acceleration','legacy_extra'):
            values=hand_fixture();rows=values[0]['frames']
            if mode=='missing':del rows[2]['hand_rotation_local_degrees']
            if mode=='extra':rows[2]['hand_scale']=2.
            if mode=='endpoint':rows[0]['hand_rotation_local_degrees']=[.1,0.,0.]
            if mode=='zero':
                for row in rows:row['hand_rotation_local_degrees']=[0.,0.,0.]
            if mode=='speed':rows[2]['hand_rotation_local_degrees']=[10.,0.,0.]
            if mode=='acceleration':rows[2]['hand_rotation_local_degrees']=[1.,0.,0.]
            if mode=='legacy_extra':values[0]['policy']='BOUNDED_NATIVE_ARM_IK_V1'
            for intake,error in ((read_fit_plan,ValidationError),(parse_fit,ValueError)):
                with self.subTest(mode=mode,intake=intake.__name__),self.assertRaises(error):intake(*values[:5])

    def test_hand_is_included_in_independent_full_sequence_angular_audit(self):
        values=hand_fixture();plan=read_fit_plan(*values[:5]);poses=values[-1]
        originals=[deepcopy(poses) for _ in range(5)]
        actuals=[fit_frame(plan,p,i) for i,p in enumerate(originals,1)]
        audit=verify_fitted_sequence(plan,originals,actuals)
        self.assertEqual(audit['frames'],5)
        self.assertAlmostEqual(audit['max_correction_angular_speed_degrees_s'],3.)
        self.assertGreater(audit['max_correction_angular_acceleration_degrees_s2'],170.)
        # The local path passes intake but changing posed local axes can still
        # make the additional WORLD rotation discontinuous. Audit must reject.
        values[0]['frames'][2]['hand_rotation_local_degrees']=[.5,0.,0.]
        plan=read_fit_plan(*values[:5])
        for matrix in originals[2][3:5]:
            for i,v in zip((0,1,4,5),(-1.,0.,0.,-1.)):matrix[i]=v
        actuals=[fit_frame(plan,p,i) for i,p in enumerate(originals,1)]
        with self.assertRaisesRegex(ValidationError,'angular'):verify_fitted_sequence(plan,originals,actuals)
