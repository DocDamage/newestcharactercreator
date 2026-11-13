"""Closed body-review parser contracts with invented metadata, not real contact."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.body_contact_contract import write_body_contract
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError
from ucc.preview.body_contacts import read_body_contacts,POLICY
from ucc.preview.motion_cache import read_motion_cache
from ucc.jobs.protocol import JobRequest
from blender_bridge.body_contact_review import checked_body_job,OPERATIONS


class BodyContactParserTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.prepare()

    def prepare(self,paired=False):
        (self.data,self.report,self.receipt,self.bindings,self.base,self.profile,self.fitted,self.cache_report,
         arm_verified)=write_body_contract(self.folder,paired)
        self.cache=read_motion_cache(self.folder,self.cache_report,self.cache_report['bindings'],self.base,
            profile=self.profile,surface_verification=arm_verified)

    def rewrite(self):
        p=self.folder/'body_contacts.json';p.write_text(json.dumps(self.data));self.report['report']=file_record(p)
        self.receipt['bindings']['body_review_sha256']=self.report['report']['sha256']

    def load(self,**kwargs):return read_body_contacts(self.folder,self.report,self.receipt,self.bindings,self.base,self.profile,self.cache,
        fitted_timeline=self.fitted,fitted_cache=self.cache if self.fitted is not None else None,**kwargs)

    def test_original_and_paired_reports_are_distinct_immutable_scoped_views(self):
        original=self.load();self.assertEqual(original.original.policy,POLICY);self.assertEqual(original.original.flagged_frames,(1,))
        self.assertIsNone(original.fitted);self.prepare(paired=True);paired=self.load()
        self.assertEqual(paired.fitted.flagged_frames,(1,2));self.assertEqual(paired.more_pair_frames,(2,))
        self.assertEqual(paired.original.triangle_hashes,self.cache.surface_review.triangle_hashes)

    def test_rehashed_wrong_scope_coverage_flags_world_hierarchy_regions_and_topology_reject(self):
        original=deepcopy(self.data)
        for case in ('version','scope','approval','fps','count','world','parent','cycle','deform','region','head','size','skin','topology','bool_count','shared_tri','partial','status_list'):
            self.data=deepcopy(original);d=self.data['original']
            if case=='version':self.data['schema_version']=True
            if case=='scope':self.data['paired']=True
            if case=='approval':self.data['contact_quality_verified']=True
            if case=='fps':self.data['fps']=60
            if case=='count':d['frames'].pop()
            if case=='world':d['world_matrix'][3]=.1
            if case=='parent':d['parents'].pop('head')
            if case=='cycle':d['parents']['spine']='head'
            if case=='deform':d['deform_bones'].append('not_actual')
            if case=='region':d['region_bones']['central_body']=['AL','head','spine']
            if case=='head':d['head']='WL'
            if case=='size':d['region_vertex_counts']['central_body']=121
            if case=='skin':d['frames'][0]['skin_sha256']='e'*64
            if case=='topology':d['frames'][0]['triangle_sha256']='e'*64
            if case=='bool_count':d['frames'][1]['left']['pair_count']=True
            if case=='shared_tri':d['frames'][1]['left']['central_triangles']=[1]
            if case=='partial':d['status']='UNAVAILABLE';d['reason']='SURFACE_PAIR_BUDGET_EXCEEDED'
            if case=='status_list':d['status']=[]
            self.rewrite()
            with self.subTest(case=case),self.assertRaises(ValidationError):self.load()

    def test_fresh_receipt_and_independent_cache_timing_cannot_be_replaced_by_assertions(self):
        original=deepcopy(self.receipt)
        for key,value in (('frames_verified',2),('paired',1),('originals_unchanged',False),('contact_quality_verified',True),('bindings',{})):
            self.receipt=deepcopy(original);self.receipt[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):self.load()
        self.receipt=original;self.cache=replace(self.cache,fps=60.)
        with self.assertRaises(ValidationError):self.load()

    def test_unavailable_report_has_no_partial_pair_verdict_and_cancel_propagates(self):
        d=self.data['original'];d['status']='UNAVAILABLE';d['reason']='SURFACE_WORKLOAD_EXCEEDED'
        for row in d['frames']:row['left']=row['right']=None
        self.rewrite();result=self.load();self.assertEqual(result.original.status,'UNAVAILABLE')
        self.assertFalse(result.original.flagged_frames)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.load(cancel_check=cancel)

    def test_all_four_worker_requests_close_hashes_paths_and_override_flags(self):
        for operation,fields in OPERATIONS.items():
            request=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            self.assertEqual(checked_body_job(request),request['options'])
            for case in ('missing','extra','bool','path'):
                bad=deepcopy(request)
                if case=='missing':bad['options'].pop('review_sha256')
                if case=='extra':bad['options']['skip_reopen']=True
                if case=='bool':bad['options']['review_sha256']=True
                if case=='path':bad['input_project']='review_motion.blend'
                with self.subTest(operation=operation,case=case),self.assertRaises(ValidationError):JobRequest.from_dict(bad)
                with self.assertRaises(ValueError):checked_body_job(bad)

    def test_job_schema_matches_original_and_paired_body_operations(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        schema=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text()))
        for operation,fields in OPERATIONS.items():
            request=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            schema.validate(request);request['options']['skip_reopen']=True;self.assertTrue(list(schema.iter_errors(request)))

    def test_observation_schema_closes_original_and_paired_variants_and_unavailable_results(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        schema=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/body-contacts.v1.schema.json').read_text()))
        for paired in (False,True):
            self.prepare(paired);schema.validate(self.data)
            bad=deepcopy(self.data);bad['contact_quality_verified']=True;self.assertTrue(list(schema.iter_errors(bad)))
            bad=deepcopy(self.data);bad['original']['status']='UNAVAILABLE';bad['original']['reason']='SURFACE_WORKLOAD_EXCEEDED'
            self.assertTrue(list(schema.iter_errors(bad)))
            for row in bad['original']['frames']:row['left']=row['right']=None
            schema.validate(bad)


if __name__=='__main__':unittest.main()
