"""Invented boundary cases and mocked skin constraints; not pack evidence."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blender_bridge.contact_area_probe import AreaCandidateProbe
from blender_bridge.contact_candidate_policy import CandidateLayout,trial_policy
from blender_bridge.hand_candidate_policy import measured_window,hand_trial,orientation_vectors,nearby_vectors
from blender_bridge.hand_candidate_search import search_hand_candidate
from blender_bridge.native_contact_probe import CandidateBudgetExceeded
from blender_bridge.native_area_candidate import checked_area_candidate_job,FIELDS
from ucc.jobs.protocol import JobRequest
from ucc.core.errors import ValidationError
from fixtures.contact_fit_contract import fixture


class HandCandidateTests(unittest.TestCase):
    def test_hand_proposal_is_a_closed_eight_hash_operation_in_both_contracts(self):
        req=JobRequest.new('propose_native_hand_contact_fit',input_project='candidate.blend',options={k:'a'*64 for k in FIELDS}).as_dict()
        self.assertEqual(checked_area_candidate_job(req),req['options'])
        for field in FIELDS:
            bad=deepcopy(req);del bad['options'][field]
            with self.subTest(field=field),self.assertRaises(ValidationError):JobRequest.from_dict(bad)
            with self.assertRaises(ValueError):checked_area_candidate_job(bad)
        bad=deepcopy(req);bad['options']['skip_body_check']=True
        with self.assertRaises(ValidationError):JobRequest.from_dict(bad)
        try:from jsonschema import Draft202012Validator
        except ImportError:return
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator=Draft202012Validator(schema);validator.validate(req)
        self.assertTrue(list(validator.iter_errors(bad)))

    def test_measured_hand_window_and_complete_bounded_policy(self):
        _,bindings,base,profile,parents,_=deepcopy(fixture());base.update(source_frame_count=61,fps=30.)
        layout=CandidateLayout('right',('upper','lower','hand'),20,30,5,45,(22,20),(1,20,22,30,61),.03,61,30.)
        window=measured_window(layout,[22,23,26])
        self.assertEqual((window.begin,window.first,window.last,window.end),(7,22,26,41))
        data,plan=hand_trial(layout,window,(.002,0.,0.),(0.,0.,-15.),bindings,base,profile,parents)
        self.assertEqual(data['policy'],'BOUNDED_NATIVE_ARM_HAND_IK_V2')
        self.assertEqual(len(plan['hand_rotations']),61)
        self.assertEqual(plan['hand_rotations'][21],(0.,0.,-15.))
        for i in (*range(7),*range(40,61)):self.assertEqual(plan['hand_rotations'][i],(0.,0.,0.))
        for bad in ([],[5],[45],[True],[22.5]):
            with self.subTest(bad=bad),self.assertRaises(ValueError):measured_window(layout,bad)
        self.assertEqual(len(orientation_vectors()),18)
        self.assertTrue(all(sum(x*x for x in v)<=15**2 for v in orientation_vectors()))
        values=nearby_vectors(layout,(.02,0.,-.02),.00125)
        self.assertIn((.02,-.00125,-.02),values)
        self.assertTrue(all(sum(x*x for x in v)<=.03**2 for v in values))

    def test_arm_seed_cannot_pollute_body_query_cache_and_restores_on_failure(self):
        probe=AreaCandidateProbe.__new__(AreaCandidateProbe)
        guard=object();queries={('existing',):'checked'}
        probe.mesh_guard=guard;probe._cache_enabled=True;probe._queries=queries
        def seed(*args):
            self.assertIsNone(probe.mesh_guard);self.assertFalse(probe._cache_enabled)
            self.assertEqual(probe._queries,{})
            probe._queries['arm_only']=0
            raise CandidateBudgetExceeded('budget')
        with patch('blender_bridge.native_contact_probe.CandidateProbe.evaluate',side_effect=seed):
            with self.assertRaises(CandidateBudgetExceeded):probe.evaluate_arm_seed({},[1])
        self.assertIs(probe.mesh_guard,guard);self.assertIs(probe._queries,queries);self.assertTrue(probe._cache_enabled)
        self.assertNotIn('arm_only',queries)

    def run_search(self,*,body_clear=False,fail_complete=False,budget=False):
        layout=SimpleNamespace(start=1,end=6,first=2,last=5,count=9,fps=30.,maximum=.03,critical=(2,),render_frames=(1,2,3,5,9))
        seed={'frames':[{'offset_world':[.02,0.,-.02]}]}
        source=SimpleNamespace(inspector=SimpleNamespace(rows=[{'left':{'pair_count':i},'right':{'pair_count':0}} for i in range(9)]))
        class Probe:
            complete=0
            def evaluate_arm_seed(self,*args):raise AssertionError('Mocked seed must be used')
            def evaluate(self,plan,frames):
                if budget:raise CandidateBudgetExceeded('budget')
                frames=list(frames);bad=not body_clear and plan=='seed' and frames==[3]
                return {'pairs':int(bad),'checked':len(frames),'body_frames_checked':len(frames)}
            def evaluate_complete(self,plan,frames):
                self.complete+=1
                if fail_complete:return {'pairs':1,'checked':3,'failed_frame':4,'body_frames_checked':3}
                return {'pairs':0,'checked':len(list(frames)),'body_frames_checked':len(list(frames))}
        probe=Probe();observations=[]
        with (patch('blender_bridge.hand_candidate_search.search_candidate',return_value=(seed,[])),
              patch('blender_bridge.hand_candidate_search.trial_policy',return_value=(seed,'seed')),
              patch('blender_bridge.hand_candidate_search.hand_trial',return_value=({'selected':'hand'},'hand')),
              patch('blender_bridge.hand_candidate_search.orientation_vectors',return_value=((0.,0.,-15.),)),
              patch('blender_bridge.hand_candidate_search.nearby_vectors',return_value=())):
            result=search_hand_candidate(layout,probe,{},None,None,None,source,observations=observations)
        return result,probe

    def test_no_body_trade_still_requires_fresh_complete_acceptance(self):
        (policy,rows),probe=self.run_search(body_clear=True)
        self.assertIn('frames',policy);self.assertEqual(probe.complete,1)
        self.assertEqual(rows[-1]['phase'],'seed_complete')

    def test_body_failures_lead_to_declared_hand_policy_and_fresh_full_check(self):
        (policy,rows),probe=self.run_search()
        self.assertEqual(policy['selected'],'hand');self.assertEqual(probe.complete,1)
        self.assertEqual(rows[-1]['phase'],'hand_complete');self.assertEqual(len(policy['render_frames']),5)

    def test_sample_success_never_accepts_failed_complete_interval_or_budget(self):
        with self.assertRaisesRegex(ValueError,'NO_BOUNDED_HAND'):self.run_search(fail_complete=True)
        with self.assertRaises(CandidateBudgetExceeded):self.run_search(budget=True)

    def test_shared_trial_limit_precedes_any_additional_body_query(self):
        layout=SimpleNamespace(start=1,end=6)
        seed={'frames':[{'offset_world':[.02,0.,-.02]}]}
        def seeds(*args,observations,**kwargs):
            observations.extend({'vector':(.02,0.,-.02),'pairs':1,'checked':1} for _ in range(499))
            return seed,observations
        probe=SimpleNamespace(evaluate_arm_seed=lambda *a:None)
        with (patch('blender_bridge.hand_candidate_search.search_candidate',side_effect=seeds),
              patch('blender_bridge.hand_candidate_search.trial_policy',return_value=(seed,'seed'))):
            with self.assertRaisesRegex(ValueError,'TRIAL_BUDGET'):search_hand_candidate(layout,probe,{},None,None,None,None)
