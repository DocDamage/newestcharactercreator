"""Invented contact counts test search policy only, never physical clearance."""
from copy import deepcopy
from dataclasses import replace
import math
import unittest

from fixtures.contact_fit_contract import baseline_contract
from ucc.animations.contact_fit import read_fit_plan
from blender_bridge.contact_candidate_policy import (
    CandidateUnavailable,candidate_layout,trial_policy,coarse_vectors,refine_vectors,
)


class ContactCandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        _policy,self.bindings,self.baseline,self.profile,self.parents,_=baseline_contract()
        self.baseline['source_frame_count']=300;self.baseline['fps']=30.
        self.contacts={'status':'CHECKED','frame_count':300,'frames':[
            {'frame':f,'left':{'pair_count':0},'right':{'pair_count':(81 if f==8 else 10) if 6<=f<=31 else 0}}
            for f in range(1,301)]}

    def layout(self):return candidate_layout(self.baseline,self.profile,self.parents,self.contacts)

    def test_actual_named_ancestry_interval_extrema_and_all_frames_are_preserved(self):
        layout=self.layout();self.assertEqual((layout.side,layout.first,layout.last),('right',6,31))
        self.assertEqual((layout.start,layout.end),(1,46));self.assertEqual(layout.critical[0],8)
        self.assertEqual(layout.chain,('upper','lower','hand'));self.assertEqual(len(layout.render_frames),5)
        data,worker=trial_policy(layout,(.015,-.005,-.02),self.bindings,self.baseline,self.profile,self.parents)
        app=read_fit_plan(data,self.bindings,self.baseline,self.profile,self.parents)
        self.assertEqual(len(app.offsets),300);self.assertEqual(app.offsets,tuple(worker['offsets']))
        self.assertEqual(app.offsets[0],(0,0,0));self.assertEqual(app.offsets[-1],(0,0,0))
        self.assertEqual(app.offsets[5],(.015,-.005,-.02));self.assertEqual(app.offsets[45],(0,0,0))

    def test_coarse_and_refined_trials_are_deterministic_unique_finite_and_fixed_bounded(self):
        layout=self.layout();vectors=coarse_vectors(layout);self.assertEqual(len(vectors),18)
        self.assertEqual(len(set(vectors)),18)
        observations=[{'vector':v,'pairs':i} for i,v in enumerate(vectors)]
        fine=refine_vectors(layout,observations);self.assertEqual(fine,refine_vectors(layout,list(observations)))
        self.assertLessEqual(len(fine),216);self.assertTrue(fine)
        for v in vectors+fine:
            self.assertTrue(0<math.hypot(*v)<=layout.maximum+1e-12)
            data,_=trial_policy(layout,v,self.bindings,self.baseline,self.profile,self.parents)
            read_fit_plan(data,self.bindings,self.baseline,self.profile,self.parents)

    def test_unavailable_partial_empty_two_hand_endpoint_and_bool_counts_reject_explicitly(self):
        for fault,code in (('unavailable','COMPLETE_SURFACE_REVIEW_REQUIRED'),('partial','COMPLETE_SURFACE_REVIEW_REQUIRED'),
            ('empty','NO_CHECKED_CROSSINGS'),('both','MULTIPLE_CONTACTING_HANDS_UNSUPPORTED'),
            ('endpoint','CONTACT_AT_FIXED_ENDPOINT'),('bool','COMPLETE_SURFACE_REVIEW_REQUIRED')):
            old=deepcopy(self.contacts)
            if fault=='unavailable':self.contacts['status']='UNAVAILABLE'
            if fault=='partial':self.contacts['frames'].pop()
            if fault=='empty':
                for row in self.contacts['frames']:row['right']['pair_count']=0
            if fault=='both':self.contacts['frames'][7]['left']['pair_count']=1
            if fault=='endpoint':self.contacts['frames'][0]['right']['pair_count']=1
            if fault=='bool':self.contacts['frames'][7]['right']['pair_count']=True
            with self.subTest(fault=fault),self.assertRaises(CandidateUnavailable) as error:self.layout()
            self.assertEqual(error.exception.code,code);self.contacts=old

    def test_missing_cyclic_multiple_root_and_nonstring_parent_trees_reject(self):
        for fault in ('missing','cycle','root','nonstring'):
            old=deepcopy(self.parents)
            if fault=='missing':self.parents.pop('hand')
            if fault=='cycle':self.parents['lower']='hand'
            if fault=='root':self.parents['lower']=None
            if fault=='nonstring':self.parents['lower']=[]
            with self.subTest(fault=fault),self.assertRaises(CandidateUnavailable):self.layout()
            self.parents=old

    def test_nonfinite_oversized_zero_vectors_wrong_hashes_and_short_fast_ramps_do_not_bypass_fit_bounds(self):
        layout=self.layout()
        for v in ((float('nan'),0,0),(10**400,0,0),(.04,0,0),(0,0,0),(True,0,0)):
            with self.subTest(v=v),self.assertRaises(ValueError):trial_policy(layout,v,self.bindings,self.baseline,self.profile,self.parents)
        bad=dict(self.bindings);bad['master_sha256']=True
        with self.assertRaises(ValueError):trial_policy(layout,(.01,0,0),bad,self.baseline,self.profile,self.parents)
        short=replace(layout,first=2,start=1)
        with self.assertRaisesRegex(ValueError,'velocity/acceleration'):
            trial_policy(short,(.03,0,0),self.bindings,self.baseline,self.profile,self.parents)

    def test_candidate_job_requires_exact_hashes_fixed_paths_and_no_override(self):
        from ucc.jobs.protocol import JobRequest
        from ucc.core.errors import ValidationError
        from blender_bridge.native_contact_candidate import checked_candidate_job
        options={**self.bindings,'surface_review_sha256':'a'*64}
        job=JobRequest.new('propose_native_contact_fit',input_project='candidate.blend',options=options).as_dict()
        self.assertEqual(checked_candidate_job(job),options)
        for fault in ('missing','override','bool','path','weak'):
            bad=deepcopy(job)
            if fault=='missing':bad['options'].pop('surface_review_sha256')
            if fault=='override':bad['options']['allow_bad_strain']=True
            if fault=='bool':bad['options']['surface_review_sha256']=True
            if fault=='path':bad['input_project']='review_motion.blend'
            if fault=='weak':bad['options']['source_sha256']='a'*63
            with self.subTest(fault=fault),self.assertRaises(ValidationError):JobRequest.from_dict(bad)
            with self.assertRaises(ValueError):checked_candidate_job(bad)

    def test_candidate_job_schema_requires_the_closed_seven_hash_contract(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        import json
        from pathlib import Path
        from ucc.jobs.protocol import JobRequest
        schema=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text()))
        job=JobRequest.new('propose_native_contact_fit',input_project='candidate.blend',
                          options={**self.bindings,'surface_review_sha256':'a'*64}).as_dict()
        schema.validate(job)
        job['options']['skip_source_reopen']=True;self.assertTrue(list(schema.iter_errors(job)))

    def test_long_contact_interval_cannot_consume_more_than_the_fixed_pose_budget(self):
        self.baseline['source_frame_count']=2000;self.contacts['frame_count']=2000
        self.contacts['frames']=[{'frame':f,'left':{'pair_count':0},'right':{'pair_count':1 if 2<=f<=1999 else 0}} for f in range(1,2001)]
        with self.assertRaisesRegex(CandidateUnavailable,'CONTACT_INTERVAL_EXCEEDS_CANDIDATE_BUDGET'):self.layout()


if __name__=='__main__':unittest.main()
