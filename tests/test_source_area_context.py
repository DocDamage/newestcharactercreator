"""Fresh-source area binding with synthetic private job records only."""
from dataclasses import replace
from copy import deepcopy
import unittest

import test_body_review_coordinator as fixture
from ucc.core.errors import ValidationError
from ucc.jobs.source_area_context import source_area_inputs,validate_candidate_areas


class SourceAreaContextTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.BodyReviewCoordinatorTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.review=self.f.run_review(stable_areas=True)

    def test_fresh_original_cache_and_bound_private_baseline_are_required(self):
        path,digest=source_area_inputs(self.f.f.store,self.f.ctx,self.review)
        self.assertEqual(str(path),self.review.private_report);self.assertEqual(digest,self.review.report_sha256)
        for fault in ('revision','binding','unavailable','metadata','report','paired','coverage','cache_job','cache_bytes','outside'):
            case=SourceAreaContextTests();case.setUp()
            try:
                r=case.review
                if fault=='revision':r=replace(r,revision=r.revision+1)
                if fault=='binding':r=replace(r,bindings=())
                if fault=='unavailable':r=replace(r,areas=replace(r.areas,status='UNAVAILABLE'))
                if fault=='metadata':r=replace(r,metadata_sha256='e'*64)
                if fault=='report':r=replace(r,report_sha256='e'*64)
                if fault=='paired':r=replace(r,fitted_playback=object())
                if fault=='coverage':r=replace(r,areas=replace(r.areas,original=()))
                if fault=='cache_job':r=replace(r,original_playback=replace(r.original_playback,job_id='unit-other'))
                if fault=='cache_bytes':r=replace(r,original_playback=replace(r.original_playback,cache=replace(r.original_playback.cache,packed=b'changed')))
                if fault=='outside':
                    from pathlib import Path
                    p=case.f.f.store.root/'outside.json';p.write_bytes(Path(r.private_report).read_bytes());r=replace(r,private_report=str(p))
                with self.subTest(fault=fault),self.assertRaises(ValidationError):source_area_inputs(case.f.f.store,case.f.ctx,r)
            finally:case.doCleanups()

    def test_candidate_coverage_receipt_is_closed_and_cannot_turn_missing_work_into_zero(self):
        good={'policy':'NO_NEW_CENTRAL_BODY_POLYGONS_V1','source_frames_verified':3,'polygon_topology_sha256':self.review.areas.polygon_sha256,
            'candidate_frames_checked':2,'new_area_frames':0,'more_hand_pair_frames':0,'rejected_pose_observations':1}
        validate_candidate_areas(good,self.review,3,2,10)
        for key,value in (('policy','old'),('polygon_topology_sha256','e'*64),('source_frames_verified',2),
            ('candidate_frames_checked',1),('new_area_frames',True),('new_area_frames',1),('more_hand_pair_frames',1),
            ('rejected_pose_observations',11),('rejected_pose_observations',-1),('skip_body',True)):
            bad=deepcopy(good);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):validate_candidate_areas(bad,self.review,3,2,10)


if __name__=='__main__':unittest.main()
