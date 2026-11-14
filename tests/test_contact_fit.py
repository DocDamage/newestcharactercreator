"""Nonshipping analytic and malformed-input tests; not clip compatibility proof."""
from copy import deepcopy
from dataclasses import replace
import math
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from ucc.animations.contact_fit import POLICY, HASHES, read_contact_fit, read_fit_plan, fit_frame, verify_fitted_frame,verify_fitted_sequence
from ucc.core.errors import ValidationError
from fixtures.contact_fit_contract import fixture,matrix


class ContactFitTests(unittest.TestCase):
    def plan(self, values):return read_fit_plan(*values[:5])

    def test_analytic_lengths_endpoint_pole_and_unrelated_branch_are_preserved(self):
        v=fixture();plan=self.plan(v);original=v[-1];out=fit_frame(plan,original,3)
        head=lambda p:tuple(p[i*4+3] for i in range(3))
        a,b,c=map(head,out[1:4])
        self.assertAlmostEqual(math.dist(a,b),1.,places=10)
        self.assertAlmostEqual(math.dist(b,c),1.,places=10)
        self.assertEqual(c,(.002,1.,1.));self.assertGreater(b[1],.99)
        self.assertEqual(out[0],original[0]);self.assertEqual(out[5],original[5])
        self.assertEqual(head(out[4]),(.002,1.,1.1))
        self.assertEqual([out[3][i] for i in (0,1,2,4,5,6,8,9,10)], [original[3][i] for i in (0,1,2,4,5,6,8,9,10)])
        self.assertEqual(original,fixture()[-1]);verify_fitted_frame(plan,original,out,3)

    def test_unchanged_endpoints_return_equal_independent_copies(self):
        v=fixture();plan=self.plan(v)
        for frame in (1,5):
            out=fit_frame(plan,v[-1],frame)
            self.assertEqual(out,v[-1]);self.assertIsNot(out,v[-1]);self.assertIsNot(out[0],v[-1][0])
        with self.assertRaises(AttributeError):plan.fps=60.

    def test_wrong_bindings_policy_fields_fps_or_coverage_reject(self):
        for case in ('hash','extra','bool_version','policy','space','fps','bool_fps','cropped','reordered','bool_frame','extra_frame'):
            v=deepcopy(fixture());d=v[0]
            if case=='hash':d['bindings']=dict(d['bindings'],source_sha256='b'*64)
            if case=='extra':d['override']=True
            if case=='bool_version':d['schema_version']=True
            if case=='policy':d['policy']='NONE'
            if case=='space':d['coordinate_space']='SOURCE_LOCAL'
            if case=='fps':d['fps']=24.
            if case=='bool_fps':d['fps']=True
            if case=='cropped':d['frames'].pop()
            if case=='reordered':d['frames'].reverse()
            if case=='bool_frame':d['frames'][0]['frame']=True
            if case=='extra_frame':d['frames'][0]['unbounded_scale']=1.
            with self.subTest(case=case),self.assertRaises(ValidationError):self.plan(v)

    def test_nonfinite_bool_offsets_endpoints_and_fixed_bounds_reject(self):
        for value in ([True,0.,0.],[10**400,0.,0.],[float('nan'),0.,0.],[float('inf'),0.,0.],[.031,0.,0.],[.02,.02,.02],[0.,0.]):
            v=deepcopy(fixture());v[0]['frames'][2]['offset_world']=value
            with self.subTest(value=value),self.assertRaises(ValidationError):self.plan(v)
        for endpoint in (0,4):
            v=deepcopy(fixture());v[0]['frames'][endpoint]['offset_world']=[.0001,0.,0.]
            with self.assertRaises(ValidationError):self.plan(v)
        v=deepcopy(fixture())
        for row in v[0]['frames']:row['offset_world']=[0.,0.,0.]
        with self.assertRaises(ValidationError):self.plan(v)

    def test_speed_and_acceleration_are_separate_fixed_guards(self):
        for amount,phrase in ((.02,'speed'),(.004,'acceleration')):
            v=deepcopy(fixture());v[0]['frames'][2]['offset_world']=[amount,0.,0.]
            with self.subTest(amount=amount),self.assertRaisesRegex(ValidationError,phrase):self.plan(v)

    def test_actual_hierarchy_side_missing_helpers_and_unrequested_skin_reject(self):
        for case in ('side','swap','cross','cycle','missing','two_roots','skin','reference'):
            v=deepcopy(fixture());d,b,base,p,parents,_=v
            if case=='side':d['chain']['side']='left'
            if case=='swap':d['chain']['upper_arm']='lower';d['chain']['forearm']='upper'
            if case=='cross':parents['hand']='other'
            if case=='cycle':parents['helper']='hand'
            if case=='missing':del parents['helper']
            if case=='two_roots':parents['other']=None
            if case=='skin':p['skin_deformation_policy']='MASTER_MODIFIERS_V1'
            if case=='reference':p['mesh_strain_reference']='FIRST_POSE_AND_NEUTRAL_V1'
            with self.subTest(case=case),self.assertRaises(ValidationError):self.plan(v)

    def test_unreachable_or_straight_limbs_and_large_rotation_corrections_reject(self):
        v=fixture();plan=self.plan(v)
        straight=deepcopy(v[-1]);straight[3]=matrix((0.,2.,0.))
        with self.assertRaises(ValidationError):fit_frame(plan,straight,3)
        axial=replace(plan,offsets=((0.,0.,0.),(0.,0.,0.),(0.,-.002,0.),(0.,0.,0.),(0.,0.,0.)))
        with self.assertRaisesRegex(ValidationError,'pole'):fit_frame(axial,straight,3)
        too_small=deepcopy(v[-1]);too_small[2]=matrix((0.,.001,0.));too_small[3]=matrix((0.,.001,.001))
        with self.assertRaises(ValidationError):fit_frame(plan,too_small,3)
        with self.assertRaises(ValidationError):fit_frame(plan,v[-1],True)
        with self.assertRaises(ValidationError):fit_frame(plan,v[-1],0)

    def test_actual_pose_substitutions_reflection_scale_or_unrelated_motion_reject(self):
        v=fixture();plan=self.plan(v);out=fit_frame(plan,v[-1],3)
        for case in ('head','hand_rotation','other','reflection','scale','missing','huge','bool'):
            bad=deepcopy(out)
            if case=='head':bad[2][3]+=.001
            if case=='hand_rotation':bad[3][0]=math.cos(.01);bad[3][1]=-math.sin(.01);bad[3][4]=math.sin(.01);bad[3][5]=math.cos(.01)
            if case=='other':bad[5][7]+=.001
            if case=='reflection':bad[0][0]=-1.
            if case=='scale':bad[0][0]=2.
            if case=='missing':bad.pop()
            if case=='huge':bad[0][0]=10**400
            if case=='bool':bad[0][0]=True
            with self.subTest(case=case),self.assertRaises(ValidationError):verify_fitted_frame(plan,v[-1],bad,3)

    def test_world_rotation_and_translation_do_not_change_the_solution(self):
        v=fixture();plan=self.plan(v);expected=fit_frame(plan,v[-1],3)
        # A proper quarter turn around Z, followed by translation.
        def transform(poses):
            result=[]
            for m in poses:
                q=list(m)
                for j in range(3):q[j]=-m[4+j];q[4+j]=m[j]
                q[3]=3-m[7];q[7]=4+m[3];q[11]=5+m[11];result.append(q)
            return result
        d,b,base,p,parents,poses=deepcopy(v)
        for row in d['frames']:
            x,y,z=row['offset_world'];row['offset_world']=[-y,x,z]
        rotated=read_fit_plan(d,b,base,p,parents)
        actual=fit_frame(rotated,transform(poses),3)
        for a,e in zip(actual,transform(expected)):
            for x,y in zip(a,e):self.assertAlmostEqual(x,y,places=10)

    def test_file_intake_binds_actual_bytes_and_freezes_selected_inputs(self):
        v=fixture();data,*args=v[:5]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'contact_fit.json';payload=json.dumps(data).encode();path.write_bytes(payload)
            plan=read_contact_fit(path,sha256(payload).hexdigest(),*args)
            self.assertEqual(plan,self.plan(v))
            path.write_text('{}')
            with self.assertRaises(ValidationError):read_contact_fit(path,sha256(payload).hexdigest(),*args)
            data['frames'][2]['offset_world'][0]=999.
            self.assertEqual(plan.offsets[2],(.002,0.,0.))

    def test_duplicate_nonfinite_invalid_and_oversized_files_reject(self):
        v=fixture();args=v[1:5]
        for payload in (b'{"frames":[],"frames":[]}',b'{"frames":[NaN]}',b'\xff',b'{',b' '*524289):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'contact_fit.json';path.write_bytes(payload)
                with self.subTest(size=len(payload)),self.assertRaises(ValidationError):
                    read_contact_fit(path,sha256(payload).hexdigest(),*args)

    def test_cancelled_intake_does_not_parse_or_publish_a_plan(self):
        v=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'contact_fit.json';payload=json.dumps(v[0]).encode();path.write_bytes(payload)
            def cancelled():raise RuntimeError('cancelled')
            with self.assertRaisesRegex(RuntimeError,'cancelled'):
                read_contact_fit(path,sha256(payload).hexdigest(),*v[1:5],cancel_check=cancelled)

    def test_anatomical_span_limits_smaller_characters_without_overriding_meter_cap(self):
        v=deepcopy(fixture());points=v[2]['target_anatomical_landmarks']
        points['head']=[0.,0.,.2];points['left_foot']=[.1,0.,0.];points['right_foot']=[-.1,0.,0.]
        v[0]['frames'][2]['offset_world']=[.005,0.,0.]
        with self.assertRaisesRegex(ValidationError,'displacement'):self.plan(v)

    def test_complete_sequence_separates_additional_rotation_from_original_motion(self):
        v=fixture();plan=self.plan(v);originals=[deepcopy(v[-1]) for _ in plan.offsets]
        fitted=[fit_frame(plan,p,i) for i,p in enumerate(originals,1)]
        audit=verify_fitted_sequence(plan,originals,fitted)
        self.assertEqual(audit['frames'],5)
        self.assertLess(audit['max_correction_angular_speed_degrees_s'],90.)
        with self.assertRaises(ValidationError):verify_fitted_sequence(plan,originals[:-1],fitted)

    def test_nearly_straight_pole_flip_rejects_despite_smooth_small_offsets(self):
        v=fixture()
        for row,amount in zip(v[0]['frames'],(0.,.0009,.0009,.0009,0.)):row['offset_world']=[0.,-amount,0.]
        plan=self.plan(v);originals=[]
        for sign in (1.,1.,-1.,-1.,-1.):
            poses=deepcopy(v[-1]);poses[2]=matrix((sign*.002,1.,0.));poses[3]=matrix((0.,2.,0.));originals.append(poses)
        fitted=[fit_frame(plan,p,i) for i,p in enumerate(originals,1)]
        with self.assertRaisesRegex(ValidationError,'angular'):verify_fitted_sequence(plan,originals,fitted)


if __name__=='__main__':unittest.main()
