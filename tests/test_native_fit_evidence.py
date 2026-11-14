"""Synthetic fitted-report forgery tests, never physical animation evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.contact_fit_contract import fitted_contract,record,stage_report
from ucc.jobs.native_fit_evidence import read_fitted_timeline,validate_fit_stage
from ucc.jobs.native_fit_renders import validate_fit_verification
from ucc.core.errors import ValidationError


class NativeFitEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        self.policy,self.options,self.base,self.profile,self.rest,self.data=fitted_contract()
        self.rest=deepcopy(self.rest)
        self.policy_path=self.folder/'contact_fit.json';self.policy_path.write_text(json.dumps(self.policy))
        self.options['fit_sha256']=sha256(self.policy_path.read_bytes()).hexdigest()
        self.data['bindings']=dict(self.options);self.data['surface_review']['bindings']=dict(self.options)
        self.report={'status':'REAL_NATIVE_FIT_MEASURED','bindings':dict(self.options),'frames':5,
                     'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}

    def read(self,payload=None):
        path=self.folder/'fitted_timeline.json';path.write_bytes(json.dumps(self.data).encode() if payload is None else payload)
        self.report['timeline']=record(path)
        return read_fitted_timeline(self.folder,self.report,self.options,self.base,self.profile,self.policy_path,self.rest)

    def test_complete_math_and_geometry_metadata_pass_without_inventing_a_contact_verdict(self):
        data,path,plan,surface,audit=self.read()
        self.assertEqual(data['frame_count'],5);self.assertEqual(surface.status,'UNAVAILABLE')
        self.assertEqual(audit['frames'],5);self.assertEqual(len(plan.offsets),5)

    def test_rehashed_measurement_cannot_change_the_bound_fit_policy_version(self):
        self.data['policy']='BOUNDED_NATIVE_ARM_HAND_IK_V2'
        with self.assertRaisesRegex(ValidationError,'policy differs'):self.read()

    def test_hand_measurement_requires_complete_independently_matching_angular_evidence(self):
        self._check_independent_hand_angular_evidence('BOUNDED_NATIVE_ARM_HAND_IK_V2')

    def test_body_shape_measurement_requires_independently_matching_hand_angular_evidence(self):
        self._check_independent_hand_angular_evidence('BOUNDED_NATIVE_BODY_SHAPE_IK_V3')

    def _check_independent_hand_angular_evidence(self,policy):
        from ucc.animations.contact_fit import read_fit_plan,fit_frame,verify_fitted_sequence
        self.policy['policy']=policy
        for row,v in zip(self.policy['frames'],(0.,.1,.2,.1,0.)):row['hand_rotation_local_degrees']=[v,0.,0.]
        self.policy_path.write_text(json.dumps(self.policy));self.options['fit_sha256']=sha256(self.policy_path.read_bytes()).hexdigest()
        self.data['policy']=self.policy['policy'];self.data['bindings']=dict(self.options)
        self.data['surface_review']['bindings']=dict(self.options);self.report['bindings']=dict(self.options)
        plan=read_fit_plan(self.policy,self.policy['bindings'],self.base,self.profile,{n:r['parent'] for n,r in self.rest.items()})
        original=[r['target_global_poses'] for r in self.base['full_timeline_frames']]
        actual=[fit_frame(plan,p,i) for i,p in enumerate(original,1)]
        for row,poses in zip(self.data['frames'],actual):row['target_global_poses']=poses
        angular=verify_fitted_sequence(plan,original,actual)
        self.data['angular_correction_metrics']={'max_speed_degrees_s':angular['max_correction_angular_speed_degrees_s'],
            'max_acceleration_degrees_s2':angular['max_correction_angular_acceleration_degrees_s2']}
        self.read()
        self.data['angular_correction_metrics']['max_acceleration_degrees_s2']=0.
        with self.assertRaisesRegex(ValidationError,'independent full-sequence'):self.read()

    def test_rehashed_wrong_pose_hand_orientation_or_unrelated_body_motion_rejects(self):
        for bone,component in ((1,0),(2,3),(3,3),(4,7),(5,11)):
            original=deepcopy(self.data);self.data['frames'][2]['target_global_poses'][bone][component]+=.001
            with self.subTest(bone=bone),self.assertRaises(ValidationError):self.read()
            self.data=original

    def test_coverage_bindings_flags_rest_and_topology_forgeries_reject(self):
        for case in ('count','crop','fps','version','approve','extra','hash','rest_roll','rest_parent','cycle','triangle','vertex','surface','joint'):
            original=deepcopy(self.data)
            if case=='count':self.data['frame_count']=True
            if case=='crop':self.data['frames'].pop()
            if case=='fps':self.data['fps']=24.
            if case=='version':self.data['schema_version']=True
            if case=='approve':self.data['contact_quality_verified']=True
            if case=='extra':self.data['skip_original']=True
            if case=='hash':self.data['bindings']['fitted_sha256']='e'*64
            if case=='rest_roll':self.data['target_rest_frames']['helper']['matrix'][0]=.99
            if case=='rest_parent':self.data['target_rest_frames']['hand']['parent']='other'
            if case=='cycle':self.data['target_rest_frames']['helper']['parent']='hand'
            if case=='triangle':self.data['frames'][1]['triangle_sha256']='f'*64
            if case=='vertex':self.data['frames'][1]['vertex_count']=121
            if case=='surface':self.data['surface_review']['status']='CHECKED';self.data['surface_review']['reason']=''
            if case=='joint':self.data['joint_motion_metrics'][0]['max_twist_degrees']=90.01
            with self.subTest(case=case),self.assertRaises(ValidationError):self.read()
            self.data=original

    def test_unchanged_strain_correction_displacement_and_frame_guards_reject(self):
        for case in ('compress','stretch','correction','movement','step','first','bool_frame','huge_matrix','bool_matrix'):
            original=deepcopy(self.data);row=self.data['frames'][1]
            if case=='compress':row['bind_strain']['min_edge_length_ratio']=.049
            if case=='stretch':row['master_strain']['max_edge_stretch_ratio']=4.001
            if case=='correction':row['skin_correction']['max_correction_local']=.1
            if case=='movement':row['max_displacement_local']=100.
            if case=='step':row['adjacent_max_displacement_local']=100.
            if case=='first':self.data['frames'][0]['moved_vertices']=1
            if case=='bool_frame':self.data['frames'][0]['frame']=True
            if case=='huge_matrix':self.data['target_rest_frames']['root']['matrix'][0]=10**400
            if case=='bool_matrix':self.data['mesh_world'][0]=True
            with self.subTest(case=case),self.assertRaises(ValidationError):self.read()
            self.data=original

    def test_policy_bytes_duplicate_nonfinite_and_summary_approval_reject(self):
        original=self.policy_path.read_bytes();self.policy_path.write_bytes(b'{}')
        with self.assertRaises(ValidationError):self.read()
        self.policy_path.write_bytes(original)
        for payload in (b'{"policy":1,"policy":2}',b'{"value":NaN}',b'\xff'):
            with self.assertRaises(ValidationError):self.read(payload)
        self.report['animation_visual_quality_verified']=True
        with self.assertRaises(ValidationError):self.read()

    def test_stage_and_fresh_receipts_need_exact_identities_counts_and_no_approval(self):
        options={k:v for k,v in self.options.items() if k!='fitted_sha256'}
        raw=stage_report(options,self.rest);validate_fit_stage(raw,options,self.base)
        for case in ('frames','approve','rest','override','velocity'):
            bad=deepcopy(raw)
            if case=='frames':bad['frames']=4
            if case=='approve':bad['contact_quality_verified']=True
            if case=='rest':bad['target_rest_frames']['helper']['parent']='hand'
            if case=='override':bad['skip_verification']=True
            if case=='velocity':bad['max_unkeyed_translation']=.0001
            with self.subTest(case=case),self.assertRaises(ValidationError):validate_fit_stage(bad,options,self.base)
        verify_options={**self.options,'fit_report_sha256':'f'*64}
        good={'status':'REAL_NATIVE_FIT_VERIFIED','bindings':verify_options,'frames_verified':5,'private_review_renders':{},
              'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        validate_fit_verification(good,verify_options,self.data)
        for key,value in (('frames_verified',4),('contact_quality_verified',True),('originals_unchanged',False)):
            bad=deepcopy(good);bad[key]=value
            with self.assertRaises(ValidationError):validate_fit_verification(bad,verify_options,self.data)


if __name__=='__main__':unittest.main()
