"""Pure mapping checks over invented receipts/matrices, no native admission."""
from hashlib import sha256
import json
import math
import unittest

from fixtures.authored_idle_mapping import encoded, evidence, rebind_frame, rebind_snapshot
from ucc.animations.authored_idle_mapping import build_original_idle_profile
from ucc.animations.native_profile import validate_native_profile
from ucc.core.errors import ValidationError


class AuthoredIdleMappingTests(unittest.TestCase):
    def test_mapped_source_unit_columns_cannot_hide_reflection_or_shear(self):
        request,arguments = evidence()
        for reflection in (True,False):
            snapshot = json.loads(arguments['snapshot_json'])
            index = next(i for i,b in enumerate(snapshot['bones']) if b['name']=='head')
            values = snapshot['frames'][-1]['poses'][index]
            if reflection:
                for row in range(3): values[row*4] *= -1
            else:
                values[0],values[4],values[8] = 1.,0.,0.
                values[1],values[5],values[9] = .5,math.sqrt(.75),0.
                values[2],values[6],values[10] = 0.,0.,1.
            self.assertTrue(all(abs(sum(values[r*4+c]**2 for r in range(3))-1) < 1e-12 for c in range(3)))
            with self.subTest(reflection=reflection),self.assertRaisesRegex(ValidationError,'reflected or sheared'):
                build_original_idle_profile(request,**rebind_snapshot(arguments,snapshot))

    def test_coherently_bound_frame_rest_and_overflow_numbers_reject(self):
        request,arguments = evidence()
        for kind in ('reflection','shear','overflow'):
            frame = json.loads(arguments['frame_json'])
            if kind=='overflow':
                payload = encoded(frame).replace(b'"overflow_marker":0.0',b'"overflow_marker":1e999')
            else:
                values = frame['anatomy']['bones'][0]['rest_local']
                if kind=='reflection': values[0] = -1.
                else: values[1],values[5] = .5,math.sqrt(.75)
                payload = encoded(frame)
            updated,changed = rebind_frame(request,arguments,payload)
            with self.subTest(kind=kind),self.assertRaises(ValidationError):
                build_original_idle_profile(updated,**changed)

    def test_same_rig_candidate_builds_explicit_map_without_hips_aliases(self):
        request,arguments = evidence()
        profile = build_original_idle_profile(request,**arguments)
        self.assertEqual(len(profile['pairs']),51)
        self.assertEqual(profile['pairs'][0]['source'],'@ARMATURE')
        self.assertTrue(all(p['source']==p['target'] for p in profile['pairs'][1:]))
        self.assertEqual(profile['hand_reference_planes']['schema_version'],2)
        self.assertEqual(profile['root_motion_policy'],'ARMATURE_ORIGIN_DISPLACEMENT_V1')
        self.assertEqual(profile['skin_deformation_policy'],'BOUND_CORRECTIVE_SMOOTH_V1')
        self.assertFalse(any(p['source'].startswith('LeftHand') for p in profile['pairs']))
        self.assertFalse(any('-0.' in p['source'] for p in profile['pairs']))
        validate_native_profile(profile,arguments['source_sha256'],arguments['snapshot_sha256'],request.target.master_sha256)
        self.assertFalse(request.to_dict()['usable_action_approved'])

    def test_rejects_unpinned_source_review_recipe_frame_snapshot_and_worker_bytes(self):
        request,original = evidence()
        for key in ('source_sha256','review_sha256','recipe_sha256','snapshot_sha256',
                    'worker_request_sha256','worker_result_sha256'):
            arguments = dict(original,**{key:'9'*64})
            with self.subTest(key=key),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**arguments)
        with self.assertRaises(ValidationError):
            build_original_idle_profile(request,**dict(original,frame_json=original['frame_json']+b' '))

    def test_verifier_identity_status_and_phase_cannot_be_reused_or_changed(self):
        request,original = evidence()
        for name in ('inspection_job_id','verification_job_id'):
            with self.subTest(name=name),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**dict(original,**{name:request.job_id}))
        for field,value in (('status','error'),('operation','inspect_fbx_animation'),('error','failed')):
            arguments = dict(original); raw = json.loads(arguments['worker_result_json']); raw[field]=value
            arguments['worker_result_json']=encoded(raw)
            arguments['worker_result_sha256']=sha256(arguments['worker_result_json']).hexdigest()
            with self.subTest(field=field),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**arguments)

    def test_coherently_rehashed_last_frame_omitted_helper_motion_is_rejected(self):
        request,arguments = evidence(); snapshot = json.loads(arguments['snapshot_json'])
        index = next(i for i,b in enumerate(snapshot['bones']) if b['name']=='finger2-0.L')
        snapshot['frames'][-1]['poses'][index][0]=0.
        snapshot['frames'][-1]['poses'][index][1]=-1.
        snapshot['frames'][-1]['poses'][index][4]=1.
        snapshot['frames'][-1]['poses'][index][5]=0.
        with self.assertRaisesRegex(ValidationError,'silently drop'):
            build_original_idle_profile(request,**rebind_snapshot(arguments,snapshot))

    def test_coherently_rehashed_local_translation_and_root_motion_reject(self):
        request,original = evidence()
        for root in (False,True):
            snapshot = json.loads(original['snapshot_json'])
            if root:
                snapshot['frames'][150]['armature_world'][3]=.01
            else:
                index=next(i for i,b in enumerate(snapshot['bones']) if b['name']=='finger1-3.R')
                snapshot['frames'][150]['poses'][index][3]+=.01
            with self.subTest(root=root),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**rebind_snapshot(original,snapshot))

    def test_clock_topology_rest_and_incomplete_source_frames_reject(self):
        request,original = evidence()
        for kind in ('clock','parent','rest','frames'):
            snapshot = json.loads(original['snapshot_json'])
            if kind=='clock': snapshot['fps']=24.
            elif kind=='parent': snapshot['bones'][-1]['parent']='spine05'
            elif kind=='rest':
                snapshot['bones'][-1]['matrix'][3]=.001
                snapshot['bones'][-1]['head'][0]=.001
                snapshot['bones'][-1]['tail'][0]=.001
            else: snapshot['frames'].pop()
            with self.subTest(kind=kind),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**rebind_snapshot(original,snapshot))

    def test_partial_report_quality_upgrades_and_missing_evidence_reject(self):
        request,original = evidence()
        for field,value in (('sample_count',299),('usable_action_approved',True),('skeleton_fingerprint','9'*64)):
            arguments=dict(original); raw=json.loads(arguments['worker_result_json']);raw['details'][field]=value
            arguments['worker_result_json']=encoded(raw)
            arguments['worker_result_sha256']=sha256(arguments['worker_result_json']).hexdigest()
            with self.subTest(field=field),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**arguments)
        with self.assertRaises(ValidationError):build_original_idle_profile(request)

    def test_coherently_bound_unknown_recipe_or_incomplete_execution_report_rejects(self):
        request,original = evidence()
        for recipe_change in (True,False):
            arguments=dict(original)
            result=json.loads(arguments['worker_result_json'])
            if recipe_change:
                recipe=json.loads(arguments['recipe_json']); recipe['unreviewed_extra']=True
                arguments['recipe_json']=encoded(recipe)
                arguments['recipe_sha256']=sha256(arguments['recipe_json']).hexdigest()
                worker=json.loads(arguments['worker_request_json'])
                worker['options']['recipe_sha256']=arguments['recipe_sha256']
                arguments['worker_request_json']=encoded(worker)
                arguments['worker_request_sha256']=sha256(arguments['worker_request_json']).hexdigest()
            else:
                report=json.loads(arguments['verification_json'])
                report['required_quality_execution']['wrapped_same_interval_velocities_measured']=False
                arguments['verification_json']=encoded(report)
                result['details']['outputs'][1]={'name':'authored_idle_verification.json',
                    'bytes':len(arguments['verification_json']),'sha256':sha256(arguments['verification_json']).hexdigest()}
            arguments['worker_result_json']=encoded(result)
            arguments['worker_result_sha256']=sha256(arguments['worker_result_json']).hexdigest()
            with self.subTest(recipe=recipe_change),self.assertRaises(ValidationError):
                build_original_idle_profile(request,**arguments)


if __name__=='__main__':unittest.main()
