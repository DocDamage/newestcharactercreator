"""Nonshipping numeric correction contracts; not skin or pack compatibility proof."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from ucc.animations.symmetric_fit import read_symmetric_plan, read_symmetric_fit
from ucc.animations.contact_fit import MAX_FIT_BYTES
from ucc.animations.symmetric_math import fit_symmetric_frame, verify_symmetric_sequence
from ucc.core.errors import ValidationError
from fixtures.symmetric_fit_contract import fixture


class SymmetricFitTests(unittest.TestCase):
    def plan(self,v): return read_symmetric_plan(*v[:6])

    def test_both_branches_keep_lengths_root_other_limbs_and_base_frames(self):
        v=fixture();plan=self.plan(v);originals,bases=v[-2:]
        actual=[fit_symmetric_frame(plan,p,b,f) for f,(p,b) in enumerate(zip(originals,bases),1)]
        index={n:i for i,n in enumerate(plan.targets)}
        point=lambda m:[m[j*4+3] for j in range(3)]
        changed=set(plan.left.branch)|set(plan.right.branch)
        for frame,(source,base,fitted) in enumerate(zip(originals,bases,actual),1):
            if not plan.active_frames[frame-1]:
                self.assertEqual(fitted,base);self.assertIsNot(fitted,base);self.assertIsNot(fitted[0],base[0]);continue
            for n,i in index.items():
                if n not in changed:self.assertEqual(source[i],fitted[i])
            for side in (plan.left,plan.right):
                chain=(side.clavicle,*side.arm.chain)
                for a,b in zip(chain,chain[1:]):
                    self.assertAlmostEqual(math.dist(point(source[index[a]]),point(source[index[b]])),math.dist(point(fitted[index[a]]),point(fitted[index[b]])),places=10)
                wrist=side.arm.chain[2]
                self.assertLess(math.dist(point(fitted[index[wrist]]),[point(source[index[wrist]])[j]+side.arm.offsets[frame-1][j] for j in range(3)]),1e-10)
        audit=verify_symmetric_sequence(plan,originals,bases,actual)
        self.assertEqual(audit['frames'],21);self.assertEqual(audit['tracked_joints'],8)
        self.assertEqual(v,fixture())

    def test_wrong_source_or_base_bindings_unknown_fields_and_policy_reject(self):
        for case in ('source','base','missing_base','extra','policy','space','version','fps','base_identity','base_targets'):
            v=deepcopy(fixture());d=v[0]
            if case=='source':d['bindings']['source_sha256']='c'*64
            if case=='base':d['bindings']['base_fitted_sha256']='c'*64
            if case=='missing_base':del d['bindings']['base_fit_policy_sha256']
            if case=='extra':d['disable_guards']=True
            if case=='policy':d['policy']='NONE'
            if case=='space':d['coordinate_space']='SOURCE_LOCAL'
            if case=='version':d['schema_version']=True
            if case=='fps':d['fps']=True
            if case=='base_identity':v=(*v[:5],replace(v[5],bindings=tuple((k,'c'*64) for k,_ in v[5].bindings)),*v[6:])
            if case=='base_targets':v=(*v[:5],replace(v[5],targets=tuple(reversed(v[5].targets))),*v[6:])
            with self.subTest(case=case),self.assertRaises(ValidationError):self.plan(v)

    def test_complete_hierarchy_and_anatomical_branch_validation(self):
        for case in ('cross','cycle','missing_helper','two_roots','wrong_hand','root_clavicle','extra_descendant','order','skin','reference'):
            v=deepcopy(fixture());d,_,baseline,profile,parents,*_=v
            if case=='cross':parents['lowerL']='upperR'
            if case=='cycle':parents['helperL']='handL'
            if case=='missing_helper':del parents['helperL']
            if case=='two_roots':parents['clavL']=None
            if case=='wrong_hand':d['chains']['left']['hand']='handR'
            if case=='root_clavicle':d['chains']['left']['clavicle']='root'
            if case=='extra_descendant':parents['head']='clavL'
            if case=='order':baseline['mapped_pairs'].reverse()
            if case=='skin':profile['skin_deformation_policy']='NONE'
            if case=='reference':profile['mesh_strain_reference']='FIRST_POSE_AND_NEUTRAL_V1'
            with self.subTest(case=case),self.assertRaises(ValidationError):self.plan(v)

    def test_base_activity_cannot_be_overwritten_by_any_control(self):
        for suffix in ('offset_world','clavicle_rotation_world_degrees','hand_rotation_local_degrees'):
            v=deepcopy(fixture());v[0]['frames'][2]['left_'+suffix]=[.0001,0.,0.]
            with self.subTest(suffix=suffix),self.assertRaisesRegex(ValidationError,'BASE_ACTIVITY_OVERLAP'):self.plan(v)

    def test_nonfinite_bool_vectors_fixed_bounds_and_endpoints_reject(self):
        for value in ([True,0.,0.],[float('nan'),0.,0.],[float('inf'),0.,0.],[10**400,0.,0.],[.081,0.,0.],[0.,0.]):
            v=deepcopy(fixture());v[0]['frames'][13]['left_offset_world']=value
            with self.subTest(value=value),self.assertRaises(ValidationError):self.plan(v)
        for key,value in (('left_clavicle_rotation_world_degrees',[9.,9.,9.]),('right_hand_rotation_local_degrees',[15.01,0.,0.])):
            v=deepcopy(fixture());v[0]['frames'][13][key]=value
            with self.assertRaises(ValidationError):self.plan(v)
        v=deepcopy(fixture());v[0]['frames'][-1]['left_offset_world']=[.0001,0.,0.]
        with self.assertRaisesRegex(ValidationError,'endpoints'):self.plan(v)

    def test_translation_and_angular_velocity_acceleration_guards(self):
        for key,amount,word in (('left_offset_world',.02,'speed'),('left_offset_world',.004,'acceleration'),
                                ('left_clavicle_rotation_world_degrees',6.,'speed'),('left_clavicle_rotation_world_degrees',2.,'acceleration')):
            v=deepcopy(fixture())
            for row in v[0]['frames']:row[key]=[0.,0.,0.]
            v[0]['frames'][13][key]=[amount,0.,0.]
            with self.subTest(key=key,amount=amount),self.assertRaisesRegex(ValidationError,word):self.plan(v)

    def test_cropped_reordered_extra_or_empty_controls_reject(self):
        for case in ('cropped','reordered','bool_frame','extra_frame','noop','bad_renders'):
            v=deepcopy(fixture());d=v[0]
            if case=='cropped':d['frames'].pop()
            if case=='reordered':d['frames'].reverse()
            if case=='bool_frame':d['frames'][0]['frame']=True
            if case=='extra_frame':d['frames'][0]['joint_scale']=[1.,1.,1.]
            if case=='noop':
                for row in d['frames']:
                    for k in row:
                        if k!='frame':row[k]=[0.,0.,0.]
            if case=='bad_renders':d['render_frames']=[1,2,3,4,5]
            with self.subTest(case=case),self.assertRaises(ValidationError):self.plan(v)

    def test_observation_tamper_in_either_branch_root_or_retained_base_rejects(self):
        v=fixture();plan=self.plan(v);originals,bases=v[-2:]
        actual=[fit_symmetric_frame(plan,p,b,f) for f,(p,b) in enumerate(zip(originals,bases),1)]
        for frame,name in ((14,'clavL'),(14,'handR'),(14,'root'),(3,'handR')):
            bad=deepcopy(actual);bad[frame-1][plan.targets.index(name)][3]+=.001
            with self.subTest(frame=frame,name=name),self.assertRaises(ValidationError):verify_symmetric_sequence(plan,originals,bases,bad)
        bad=deepcopy(originals[13]);bad[0][0]=-1.
        with self.assertRaises(ValidationError):fit_symmetric_frame(plan,bad,bases[13],14)
        with self.assertRaises(ValidationError):fit_symmetric_frame(plan,originals[13],bases[13],True)

    def test_derived_relative_rotation_does_not_relax_final_world_bound(self):
        v=fixture();plan=self.plan(v);offsets=list(plan.right.arm.offsets);offsets[13]=(0.,-.07,0.)
        side=replace(plan.right,arm=replace(plan.right.arm,offsets=tuple(offsets),hand_rotations=()),
                     rotations=tuple((0.,0.,0.) for _ in offsets))
        with self.assertRaisesRegex(ValidationError,'15-degree source-world'):
            fit_symmetric_frame(replace(plan,right=side),v[-2][13],v[-1][13],14)

    def test_actual_correction_audit_rejects_a_clavicle_pulse(self):
        v=fixture();plan=self.plan(v);values=list(plan.left.rotations);values[13]=(2.,0.,values[13][2])
        plan=replace(plan,left=replace(plan.left,rotations=tuple(values)))
        originals,bases=v[-2:]
        actual=[fit_symmetric_frame(plan,p,b,f) for f,(p,b) in enumerate(zip(originals,bases),1)]
        with self.assertRaisesRegex(ValidationError,'discontinuous angular'):
            verify_symmetric_sequence(plan,originals,bases,actual)

    def test_world_frame_change_keeps_hand_axes_local(self):
        v=fixture();plan=self.plan(v)
        def vector(a):return (-a[1],a[0],a[2])
        def matrix(m):
            result=list(m)
            for j in range(3):result[j]=-m[4+j];result[4+j]=m[j]
            p=vector([m[j*4+3] for j in range(3)])
            for j in range(3):result[j*4+3]=p[j]+(3.,4.,1.)[j]
            return result
        expected=fit_symmetric_frame(plan,v[-2][13],v[-1][13],14)
        def side(s):return replace(s,arm=replace(s.arm,offsets=tuple(vector(x) for x in s.arm.offsets)),
                                   rotations=tuple(vector(x) for x in s.rotations))
        rotated=replace(plan,left=side(plan.left),right=side(plan.right))
        actual=fit_symmetric_frame(rotated,[matrix(m) for m in v[-2][13]],[matrix(m) for m in v[-1][13]],14)
        for wanted,measured in zip(map(matrix,expected),actual):
            for a,b in zip(wanted,measured):self.assertAlmostEqual(a,b,places=10)

    def test_sha_duplicate_json_redirection_and_cancellation_boundaries(self):
        v=fixture();payload=json.dumps(v[0]).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'layer.json';path.write_bytes(payload);digest=sha256(payload).hexdigest()
            self.assertEqual(read_symmetric_fit(path,digest,*v[1:6]),self.plan(v))
            with self.assertRaisesRegex(ValidationError,'SHA-256'):read_symmetric_fit(path,'0'*64,*v[1:6])
            duplicate=payload.replace(b'"schema_version": 1',b'"schema_version": 1, "schema_version": 1',1)
            path.write_bytes(duplicate)
            with self.assertRaisesRegex(ValidationError,'JSON'):read_symmetric_fit(path,sha256(duplicate).hexdigest(),*v[1:6])
            path.write_bytes(payload)
            def cancelled():raise RuntimeError('cancel-test')
            with self.assertRaisesRegex(RuntimeError,'cancel-test'):read_symmetric_fit(path,digest,*v[1:6],cancel_check=cancelled)
            path.write_bytes(b' '*(MAX_FIT_BYTES+1))
            with self.assertRaisesRegex(ValidationError,'bounded'):read_symmetric_fit(path,digest,*v[1:6])

    def test_symlink_policy_is_rejected_before_following_it(self):
        v=fixture();payload=json.dumps(v[0]).encode()
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'policy.json';target.write_bytes(payload);link=Path(temporary)/'redirect.json'
            try:os.symlink(target,link)
            except OSError:self.skipTest('Symbolic links are unavailable in this Windows environment')
            with self.assertRaisesRegex(ValidationError,'regular policy'):
                read_symmetric_fit(link,sha256(payload).hexdigest(),*v[1:6])


if __name__=='__main__':unittest.main()
