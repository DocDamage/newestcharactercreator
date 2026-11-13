"""Rehashed malformed reports must fail independently of their byte identities."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.skin_inclusion_contract import write_skin_contract
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError
from ucc.preview.skin_inclusion import read_skin_inclusion
from ucc.preview.skin_geometry import cached_skin_metrics
from ucc.jobs.protocol import JobRequest
from blender_bridge.skin_inclusion_review import OPERATIONS,checked_skin_job


class SkinInclusionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.folder=Path(temp.name);self.prepare()

    def prepare(self,paired=False):
        self.data,self.report,self.receipt,self.bindings,self.baseline,self.profile,self.fitted,self.cache=write_skin_contract(self.folder,paired)

    def load(self,**kwargs):return read_skin_inclusion(self.folder,self.report,self.receipt,self.bindings,self.baseline,self.profile,self.cache,
        fitted_timeline=self.fitted,fitted_cache=self.cache if self.fitted else None,**kwargs)

    def rewrite(self):
        p=self.folder/'body_contacts.json';p.write_text(json.dumps(self.data),encoding='utf-8');self.report['report']=file_record(p)
        self.receipt['bindings']['body_review_sha256']=self.report['report']['sha256']

    def test_original_and_paired_observations_preserve_unknown_separately(self):
        result=self.load();self.assertIsNone(result.fitted)
        self.assertEqual(result.original.nonzero,((frozenset({0}),frozenset()),)*3)
        self.assertEqual(result.original.ambiguous,((frozenset(),frozenset({2})),)*3)
        self.prepare(True);self.assertEqual(self.load().original,self.load().fitted)

    def test_rehashed_scope_hash_topology_geometry_selection_and_budget_lies_reject(self):
        original=deepcopy(self.data)
        for case in ('version','policy','approval','count','frame','skin','topology','world','parent','region','volume','diagonal','offset',
                     'queries','bool','duplicate','outside','shared','unselected','ambiguous_overlap','partial','missing','nan','vertex_count'):
            self.data=deepcopy(original);d=self.data['original'];row=d['frames'][0];obs=row['observation']
            if case=='version':self.data['schema_version']=True
            if case=='policy':self.data['policy']='HAND_CENTRAL_BODY_TRIANGLES_V1'
            if case=='approval':self.data['contact_quality_verified']=True
            if case=='count':d['frames'].pop()
            if case=='frame':row['frame']=True
            if case=='skin':row['skin_sha256']='0'*64
            if case=='topology':row['triangle_sha256']='0'*64
            if case=='world':d['world_matrix'][0]=True
            if case=='parent':d['parents']['head']='head'
            if case=='region':d['region_bones']['left_hand']=['WR']
            if case=='volume':obs['signed_volume_world']=2.
            if case=='diagonal':obs['diagonal_world']=2.
            if case=='offset':obs['offset_world']=.1
            if case=='queries':obs['ray_queries']=5
            if case=='bool':obs['left']['selected_triangles']=[True]
            if case=='duplicate':obs['left']['selected_triangles']=[0,0]
            if case=='outside':obs['left']['selected_triangles']=[12]
            if case=='shared':obs['right']=deepcopy(obs['left'])
            if case=='unselected':obs['left']['nonzero_triangles']=[1]
            if case=='ambiguous_overlap':obs['left']['ambiguous_triangles']=[0]
            if case=='partial':row['observation']=None
            if case=='missing':obs.pop('ray_queries')
            if case=='nan':obs['signed_volume_world']=float('nan')
            if case=='vertex_count':d['region_vertex_counts']['left_hand']=2
            self.rewrite()
            with self.subTest(case=case),self.assertRaises(ValidationError):self.load()

    def test_fresh_receipt_status_and_report_bytes_are_mandatory(self):
        self.receipt['status']='REAL_NATIVE_BODY_CONTACTS_VERIFIED'
        with self.assertRaises(ValidationError):self.load()
        self.prepare();self.receipt['bindings']['body_review_sha256']='0'*64
        with self.assertRaises(ValidationError):self.load()
        self.prepare();(self.folder/'body_contacts.json').write_text('{}',encoding='utf-8')
        with self.assertRaises(ValidationError):self.load()

    def test_unavailable_has_no_zero_or_partial_verdict(self):
        d=self.data['original'];d.update(status='UNAVAILABLE',reason='SKIN_OPEN_OR_UNORIENTED')
        for row in d['frames']:row['observation']=None
        self.rewrite();result=self.load();self.assertIsNone(result.original.nonzero);self.assertIsNone(result.original.ambiguous)
        d['frames'][0]['observation']={};self.rewrite()
        with self.assertRaises(ValidationError):self.load()

    def test_independent_cache_metrics_and_cancellation(self):
        diagonal,volume=cached_skin_metrics(self.cache,0);self.assertAlmostEqual(volume,1.);self.assertAlmostEqual(diagonal,3**.5)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.load(cancel_check=cancel)
        with self.assertRaisesRegex(RuntimeError,'cancelled'):cached_skin_metrics(self.cache,0,cancel_check=cancel)
        self.cache=replace(self.cache,world_matrix=tuple(-x if i==0 else x for i,x in enumerate(self.cache.world_matrix)))
        with self.assertRaises(ValidationError):cached_skin_metrics(self.cache,0)

    def test_all_four_job_contracts_require_exact_fixed_sha_inputs(self):
        for operation,fields in OPERATIONS.items():
            options={key:'a'*64 for key in fields}
            request=JobRequest.new(operation,input_project='candidate.blend',options=options)
            self.assertEqual(checked_skin_job(request.as_dict()),options)
            with self.subTest(operation=operation),self.assertRaises(ValidationError):
                JobRequest.new(operation,input_project='candidate.blend',options={**options,'quality_approved':True}).validate()

    def test_closed_schemas_match_all_operations_and_complete_observations(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        root=Path(__file__).resolve().parents[1]/'docs/schemas'
        worker=Draft202012Validator(json.loads((root/'worker-job.v1.schema.json').read_text(encoding='utf-8')))
        for operation,fields in OPERATIONS.items():
            request=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            worker.validate(request);request['options']['skip_topology']=True;self.assertTrue(list(worker.iter_errors(request)))
        schema=Draft202012Validator(json.loads((root/'skin-inclusion.v1.schema.json').read_text(encoding='utf-8')))
        for paired in (False,True):
            self.prepare(paired);schema.validate(self.data)
            bad=deepcopy(self.data);bad['original']['frames'][0]['observation']['quality_approved']=True
            self.assertTrue(list(schema.iter_errors(bad)))
            bad=deepcopy(self.data);bad['original'].update(status='UNAVAILABLE',reason='SKIN_RAY_BUDGET')
            for row in bad['original']['frames']:row['observation']=None
            schema.validate(bad);bad['original']['frames'][0]['observation']=self.data['original']['frames'][0]['observation']
            self.assertTrue(list(schema.iter_errors(bad)))
