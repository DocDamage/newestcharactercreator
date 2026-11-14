"""Nonshipping policy/math boundaries; not real animation or skin evidence."""
from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from fixtures.contact_fit_contract import fixture
from ucc.animations.contact_fit import BODY_POLICY,POLICY,read_fit_plan,fit_frame,verify_fitted_sequence
from ucc.animations.hand_fit import POLICY as HAND_POLICY
from ucc.core.errors import ValidationError
from blender_bridge.native_fit_policy import parse_fit


def body_fixture(amplitude=.08):
    values=list(deepcopy(fixture()));data,_,base,_,_,_=values
    count=61;data['policy']=BODY_POLICY;base['source_frame_count']=count;rows=[]
    for i in range(count):
        factor=0. if i in (0,count-1) else math.sin(math.pi*i/(count-1))**2
        rows.append({'frame':i+1,'offset_world':[amplitude*factor,0.,0.],
                     'hand_rotation_local_degrees':[15.*factor,0.,0.]})
    data['frames']=rows
    return values


class BodyShapeFitTests(unittest.TestCase):
    def test_explicit_body_policy_uses_fixed_world_and_body_span_limits(self):
        values=body_fixture();core=read_fit_plan(*values[:5]);worker=parse_fit(*values[:5])
        self.assertEqual(core.policy,BODY_POLICY);self.assertEqual(core.maximum_offset,.08)
        self.assertEqual(worker['maximum'],core.maximum_offset);self.assertEqual(worker['hand_rotations'],list(core.hand_rotations))
        smaller=body_fixture(.04);smaller[2]['target_anatomical_landmarks']['head']=[0.,0.,-.2]
        self.assertAlmostEqual(read_fit_plan(*smaller[:5]).maximum_offset,.04)
        self.assertAlmostEqual(parse_fit(*smaller[:5])['maximum'],.04)

    def test_existing_arm_and_hand_modes_retain_their_30mm_limit(self):
        for policy in (POLICY,HAND_POLICY):
            values=body_fixture();values[0]['policy']=policy
            if policy==POLICY:
                for row in values[0]['frames']:del row['hand_rotation_local_degrees']
            for intake,error in ((read_fit_plan,ValidationError),(parse_fit,ValueError)):
                with self.subTest(policy=policy,intake=intake.__name__),self.assertRaises(error):intake(*values[:5])

    def test_complete_pose_path_preserves_endpoints_finger_length_and_unrelated_bones(self):
        values=body_fixture();plan=read_fit_plan(*values[:5]);poses=values[-1]
        source=[deepcopy(poses) for _ in plan.offsets];actual=[fit_frame(plan,p,i) for i,p in enumerate(source,1)]
        audit=verify_fitted_sequence(plan,source,actual);self.assertEqual(audit['frames'],61)
        self.assertEqual(actual[0],poses);self.assertEqual(actual[-1],poses)
        head=lambda m:tuple(m[i] for i in (3,7,11))
        for row in actual:
            self.assertEqual(row[0],poses[0]);self.assertEqual(row[5],poses[5])
            self.assertAlmostEqual(math.dist(head(row[3]),head(row[4])),.1)
        actual[30][3][0]+=.001
        with self.assertRaises(ValidationError):verify_fitted_sequence(plan,source,actual)

    def test_relative_norm_speed_acceleration_and_fixed_schema_cannot_be_overridden(self):
        for fault in ('absolute','relative','norm','speed','acceleration','hand','missing','override','endpoint','binding','short'):
            values=body_fixture();data,bindings,base,*_=values;rows=data['frames']
            if fault=='absolute':rows[30]['offset_world']=[.081,0.,0.]
            if fault=='relative':base['target_anatomical_landmarks']['head']=[0.,0.,-.2]
            if fault=='norm':rows[30]['offset_world']=[.06,.06,0.]
            if fault in ('speed','acceleration'):
                for row in rows:row['offset_world']=[0.,0.,0.]
                rows[30]['offset_world']=[.08 if fault=='speed' else .004,0.,0.]
            if fault=='hand':rows[30]['hand_rotation_local_degrees']=[16.,0.,0.]
            if fault=='missing':del rows[30]['hand_rotation_local_degrees']
            if fault=='override':data['maximum_offset_world']=1.
            if fault=='endpoint':rows[0]['offset_world']=[.001,0.,0.]
            if fault=='binding':data['bindings']={**bindings,'source_sha256':'b'*64}
            if fault=='short':base['source_frame_count']=3;data['frames']=rows[:3]
            for intake,error in ((read_fit_plan,ValidationError),(parse_fit,ValueError)):
                with self.subTest(fault=fault,intake=intake.__name__),self.assertRaises(error):intake(*values[:5])

    def test_world_hand_angular_motion_still_requires_full_sequence_validation(self):
        values=body_fixture();plan=read_fit_plan(*values[:5]);poses=values[-1]
        source=[deepcopy(poses) for _ in plan.offsets]
        for matrix in source[30][3:5]:
            for i,v in zip((0,1,4,5),(-1.,0.,0.,-1.)):matrix[i]=v
        actual=[fit_frame(plan,p,i) for i,p in enumerate(source,1)]
        with self.assertRaisesRegex(ValidationError,'angular'):verify_fitted_sequence(plan,source,actual)

    def test_json_schema_keeps_legacy_offsets_closed_and_requires_hand_rows(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/native-fit.v1.schema.json').read_text(encoding='utf-8'))
        validator=Draft202012Validator(schema);values=body_fixture();validator.validate(values[0])
        values[0]['policy']=HAND_POLICY;self.assertTrue(list(validator.iter_errors(values[0])))
        values=body_fixture();del values[0]['frames'][30]['hand_rotation_local_degrees']
        self.assertTrue(list(validator.iter_errors(values[0])))


if __name__=='__main__':unittest.main()
