"""Invented search constraints and mocked geometry; not animation proof."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blender_bridge.contact_area_probe import CandidateAreaGuard,AreaCandidateProbe,area_critical_layout,area_trial_rank
from blender_bridge.contact_candidate_policy import CandidateLayout,refine_vectors
from blender_bridge.native_contact_candidate import search_candidate
from blender_bridge.native_contact_probe import CandidateBudgetExceeded
from blender_bridge.native_area_candidate import FIELDS,checked_area_candidate_job
from ucc.jobs.protocol import JobRequest
from ucc.core.errors import ValidationError


class AreaSearchTests(unittest.TestCase):
    def test_frame_area_guard_rejects_new_faces_despite_fewer_pairs(self):
        empty={'hand_triangles':[],'central_triangles':[],'pair_count':0}
        original={'left':{'hand_triangles':[0],'central_triangles':[2],'pair_count':2},'right':empty}
        current=deepcopy(original);current['left'].update(hand_triangles=[1],pair_count=1)
        source=SimpleNamespace(inspector=SimpleNamespace(polygon_sha='a'*64,rows=[original]),areas=[{'left':{0,2},'right':set()}])
        guard=CandidateAreaGuard({},source)
        inspector=SimpleNamespace(status='CHECKED',area_reason='',polygon_sha='a'*64,rows=[current],inspect=lambda *a:None)
        mesh=SimpleNamespace(loop_triangles=[SimpleNamespace(polygon_index=i) for i in range(3)])
        with patch('blender_bridge.contact_area_probe.AreaInspector',return_value=inspector):
            self.assertEqual(guard(None,None,None,mesh,1,'b'*64,'c'*64),1)
            current['left']['hand_triangles']=[0];self.assertEqual(guard(None,None,None,mesh,1,'b'*64,'c'*64),0)
            current['right']=deepcopy(original['left']);self.assertGreater(guard(None,None,None,mesh,1,'b'*64,'c'*64),0)
            inspector.polygon_sha='d'*64
            with self.assertRaisesRegex(ValueError,'STABLE_BODY_AREAS_UNAVAILABLE'):guard(None,None,None,mesh,1,'b'*64,'c'*64)
        self.assertEqual(guard.rejected,[1,1]);guard.reset();self.assertEqual(guard.frames,[])

    def test_body_critical_frames_are_measured_inside_the_changed_interval(self):
        layout=CandidateLayout('right',('u','l','h'),2,3,1,5,(2,),(1,2,3,4,5),.03,5,30.)
        rows=[{'left':{'pair_count':n},'right':{'pair_count':0}} for n in (1000,0,4,8,2000)]
        result=area_critical_layout(layout,SimpleNamespace(inspector=SimpleNamespace(rows=rows)))
        self.assertEqual(result.critical,(2,4,3));self.assertEqual(layout.critical,(2,))
        self.assertEqual(result.maximum,.03);self.assertEqual(result.start,1)

    def test_refinement_can_shrink_without_expanding_displacement_or_trial_limits(self):
        layout=CandidateLayout('right',('u','l','h'),2,3,1,5,(2,),(1,2,3,4,5),.03,5,30.)
        rows=[{'vector':(.02,-.005,-.015),'pairs':2,'checked':8,'body_frames_checked':7}]
        fine=refine_vectors(layout,rows,rank_key=area_trial_rank,step_size=.0025)
        self.assertIn((.02,-.0025,-.0175),fine)
        self.assertTrue(all(sum(x*x for x in v)<=.03**2+1e-12 for v in fine))
        easy={'vector':(0.,0.,.02),'pairs':1,'checked':1,'body_frames_checked':0}
        self.assertLess(area_trial_rank(rows[0]),area_trial_rank(easy))
        for step in (0.,-.1,.006,True,float('nan')):
            with self.assertRaises(ValueError):refine_vectors(layout,rows,step_size=step)

    def test_sampled_success_never_substitutes_for_complete_interval_or_pose_budget(self):
        layout=SimpleNamespace(start=1,end=5,critical=(2,))
        def trial(_layout,vector,*args):return {'chosen':vector},vector
        class Probe:
            calls=[]
            def evaluate(self,plan,frames):
                frames=list(frames);self.calls.append((plan,frames))
                return {'pairs':1 if len(frames)>1 and plan==(1,0,0) else 0,'checked':len(frames)}
        probe=Probe()
        with (patch('blender_bridge.native_contact_candidate.coarse_vectors',return_value=[(1,0,0)]),
              patch('blender_bridge.native_contact_candidate.refine_vectors',return_value=[(2,0,0)]),
              patch('blender_bridge.native_contact_candidate.trial_policy',side_effect=trial)):
            chosen,rows=search_candidate(layout,probe,{},None,None,None)
            self.assertEqual(chosen['chosen'],(2,0,0));self.assertEqual(probe.calls[-1][1],[2,3,4])
            with patch.object(probe,'evaluate',side_effect=CandidateBudgetExceeded('CANDIDATE_POSE_BUDGET_EXCEEDED')):
                with self.assertRaises(CandidateBudgetExceeded):search_candidate(layout,probe,{},None,None,None)

    def test_exact_pose_cache_is_only_for_sampling_and_complete_acceptance_evaluates_again(self):
        probe=AreaCandidateProbe.__new__(AreaCandidateProbe);probe._queries={};probe._cache_enabled=True;probe.cache_hits=0;probe.tested=0
        class Guard:
            frames=[]
            def reset(self):self.frames=[]
        probe.area_guard=Guard()
        plan={'chain':('u','l','h'),'offsets':[(.01,0.,0.),(.02,0.,0.)]}
        def actual(_plan,frame):probe.tested+=1;probe.area_guard.frames.append(frame);return 0
        with patch('blender_bridge.native_contact_probe.CandidateProbe.frame',side_effect=actual) as frame:
            probe.evaluate(plan,[1,2]);probe.evaluate(plan,[1,2])
            self.assertEqual(frame.call_count,2);self.assertEqual(probe.cache_hits,2)
            result=probe.evaluate_complete(plan,[1,2]);self.assertEqual(result['body_frames_checked'],2)
            self.assertEqual(frame.call_count,4);self.assertEqual(probe.tested,4)
            with patch('blender_bridge.native_contact_probe.CandidateProbe.frame',side_effect=CandidateBudgetExceeded('budget')):
                with self.assertRaises(CandidateBudgetExceeded):probe.evaluate_complete(plan,[1,2])
            self.assertTrue(probe._cache_enabled)

    def test_failed_full_interval_frame_is_learned_before_later_candidate_acceptance(self):
        layout=SimpleNamespace(start=1,end=5,critical=(2,))
        class Probe:
            samples=[]
            def evaluate(self,plan,frames):
                frames=list(frames);self.samples.append(frames);return {'pairs':0,'checked':len(frames)}
            def evaluate_complete(self,plan,frames):
                return {'pairs':1 if plan==1 else 0,'checked':3,'failed_frame':4} if plan==1 else {'pairs':0,'checked':3}
        probe=Probe()
        with (patch('blender_bridge.native_contact_candidate.coarse_vectors',return_value=[(1,0,0)]),
              patch('blender_bridge.native_contact_candidate.refine_vectors',return_value=[(2,0,0)]),
              patch('blender_bridge.native_contact_candidate.trial_policy',side_effect=lambda _l,v,*a:({'selected':v[0]},v[0]))):
            result,_=search_candidate(layout,probe,{},None,None,None,learn_failed_frames=True)
        self.assertEqual(result['selected'],2);self.assertEqual(probe.samples[-1],[2,4]);self.assertEqual(layout.critical,(2,))

    def test_eight_hash_request_cannot_omit_body_baseline_or_add_overrides(self):
        req=JobRequest.new('propose_native_area_contact_fit',input_project='candidate.blend',options={k:'a'*64 for k in FIELDS}).as_dict()
        self.assertEqual(checked_area_candidate_job(req),req['options'])
        for fault in ('missing','bool','extra','path'):
            bad=deepcopy(req)
            if fault=='missing':bad['options'].pop('source_body_areas_sha256')
            if fault=='bool':bad['options']['source_body_areas_sha256']=True
            if fault=='extra':bad['options']['skip_body_areas']=True
            if fault=='path':bad['input_project']='review_motion.blend'
            with self.subTest(fault=fault),self.assertRaises(ValueError):checked_area_candidate_job(bad)
            with self.assertRaises(ValidationError):JobRequest.from_dict(bad)

    def test_optional_job_schema_closes_the_eight_hash_candidate_contract(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        req=JobRequest.new('propose_native_area_contact_fit',input_project='candidate.blend',options={k:'a'*64 for k in FIELDS}).as_dict()
        validator.validate(req);req['options'].pop('source_body_areas_sha256');self.assertTrue(list(validator.iter_errors(req)))


if __name__=='__main__':unittest.main()
