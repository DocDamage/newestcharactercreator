"""Invented polygon/triangle contracts, not animation or physical skin evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

import test_body_contacts as body_fixture
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError
from ucc.preview.contact_areas import POLICY,polygon_membership,contact_polygons,read_body_contact_areas
from ucc.jobs.protocol import JobRequest
from blender_bridge.body_contact_areas import OPERATIONS,checked_area_job


class ContactAreaTests(unittest.TestCase):
    def setUp(self):
        self.f=body_fixture.BodyContactParserTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.prepare(True);f=self.f;seen={}
        for frame in range(3):
            for face in struct.iter_unpack('<III',f.cache.frame(frame)[1]):seen.setdefault(tuple(sorted(face)),list(face))
        polygons=list(seen.values());self.polygons=polygons
        self.wrapper={'schema_version':1,'policy':POLICY,'status':'CHECKED','reason':'','bindings':f.bindings,
            'body_contacts':deepcopy(f.data),'polygons':polygons,
            'polygon_topology_sha256':sha256(json.dumps(polygons,separators=(',',':')).encode()).hexdigest(),
            'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        self.write()

    def write(self):
        f=self.f;p=f.folder/'body_contacts.json';p.write_text(json.dumps(self.wrapper));f.report['report']=file_record(p)
        f.receipt['bindings']['body_review_sha256']=f.report['report']['sha256']

    def load(self,**kwargs):
        f=self.f
        return read_body_contact_areas(f.folder,f.report,f.receipt,f.bindings,f.base,f.profile,f.cache,
            fitted_timeline=f.fitted,fitted_cache=f.cache,cancel_check=kwargs.get('cancel_check',lambda:None))

    def test_closed_paired_areas_resolve_actual_cache_indices_and_new_faces(self):
        areas=self.load();self.assertEqual(areas.status,'CHECKED');self.assertEqual(areas.new_area_frames,(2,))
        self.assertEqual(areas.more_hand_pair_frames,(2,));self.assertTrue(areas.fitted[2]-areas.original[2])
        self.assertEqual(areas.contacts.fitted.flagged_frames,(1,2))

    def test_quad_diagonal_and_global_triangle_number_changes_do_not_invent_new_areas(self):
        membership=polygon_membership([[0,1,2,3],[4,5,6,7]],8)
        def cache(tris):return SimpleNamespace(frame=lambda _: (b'',b''.join(struct.pack('<III',*t) for t in tris)))
        source=cache([(0,1,2),(0,2,3),(4,5,6),(4,6,7)])
        fitted=cache([(0,1,3),(1,2,3),(4,5,7),(5,6,7)])
        a=contact_polygons(source,SimpleNamespace(triangles=((0,),)),membership)
        b=contact_polygons(fitted,SimpleNamespace(triangles=((1,),)),membership)
        self.assertEqual(a,b);self.assertEqual(a,(frozenset({0}),))
        c=contact_polygons(fitted,SimpleNamespace(triangles=((2,),)),membership)
        self.assertEqual(c[0]-a[0],{1})

    def test_rehashed_polygon_scope_identity_budget_and_partial_verdict_faults_reject(self):
        initial=deepcopy(self.wrapper)
        for fault in ('policy','approval','version','sha','duplicate','outside','bool','missing','unavailable','status_list','nested_body'):
            self.wrapper=deepcopy(initial)
            if fault=='policy':self.wrapper['policy']='TRIANGLE_NUMBERS_ARE_STABLE'
            if fault=='approval':self.wrapper['contact_quality_verified']=True
            if fault=='version':self.wrapper['schema_version']=True
            if fault=='sha':self.wrapper['polygon_topology_sha256']='e'*64
            if fault=='duplicate':self.wrapper['polygons'].append(self.wrapper['polygons'][0])
            if fault=='outside':self.wrapper['polygons'][0][0]=120
            if fault=='bool':self.wrapper['polygons'][0][0]=True
            if fault=='missing':self.wrapper['polygons']=[]
            if fault=='unavailable':self.wrapper.update(status='UNAVAILABLE',reason='POLYGON_TOPOLOGY_CHANGED')
            if fault=='status_list':self.wrapper['status']=[]
            if fault=='nested_body':self.wrapper['body_contacts']['original']['frames'].pop()
            self.write()
            with self.subTest(fault=fault),self.assertRaises(ValidationError):self.load()
        with self.assertRaises(ValidationError):polygon_membership([[0,1,2]]*100001,120)

    def test_unavailable_preserves_contact_observations_without_a_partial_area_verdict(self):
        self.wrapper.update(status='UNAVAILABLE',reason='POLYGON_TOPOLOGY_CHANGED',polygons=[],polygon_topology_sha256=None)
        self.write();areas=self.load();self.assertEqual(areas.contacts.fitted.flagged_frames,(1,2))
        self.assertIsNone(areas.new_area_frames);self.assertIsNone(areas.original)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.load(cancel_check=cancel)

    def test_missing_or_ambiguous_highlighted_face_and_pair_increases_hidden_by_totals(self):
        cache=SimpleNamespace(frame=lambda _:(b'',struct.pack('<III',0,1,2)))
        surface=SimpleNamespace(triangles=((0,),))
        for membership in (polygon_membership([[0,1,3]],4),polygon_membership([[0,1,2],[0,1,2,3]],4)):
            with self.assertRaises(ValidationError):contact_polygons(cache,surface,membership)
        d=self.wrapper['body_contacts'];d['original']['frames'][1]['left']['pair_count']=2
        d['original']['frames'][1]['left']['hand_triangles']=[1,3]
        d['fitted']['frames'][1]['left']['pair_count']=0
        d['fitted']['frames'][1]['left'].update(pair_sha256=sha256().hexdigest(),hand_triangles=[],central_triangles=[])
        d['fitted']['frames'][1]['right']=deepcopy(d['original']['frames'][1]['left'])
        d['fitted']['frames'][1]['right']['pair_count']=1
        d['fitted']['frames'][1]['right']['hand_triangles']=[1]
        # More per-hand pairs must be diagnosed even when aggregate counts drop.
        self.write();areas=self.load();self.assertIn(1,areas.more_hand_pair_frames)
        self.assertNotIn(1,areas.contacts.more_pair_frames)

    def test_all_four_requests_close_hashes_and_override_flags(self):
        for operation,fields in OPERATIONS.items():
            req=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            self.assertEqual(checked_area_job(req),req['options'])
            req['options']['skip_area_check']=True
            with self.assertRaises(ValidationError):JobRequest.from_dict(req)
            with self.assertRaises(ValueError):checked_area_job(req)

    def test_optional_schemas_close_polygon_intake_and_worker_requests(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        path=Path(__file__).resolve().parents[1]/'docs/schemas'
        validator=Draft202012Validator(json.loads((path/'body-contact-areas.v1.schema.json').read_text()))
        validator.validate(self.wrapper)
        worker=Draft202012Validator(json.loads((path/'worker-job.v1.schema.json').read_text()))
        for operation,fields in OPERATIONS.items():
            req=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            worker.validate(req);req['options']['skip_area_check']=True;self.assertTrue(list(worker.iter_errors(req)))


if __name__=='__main__':unittest.main()
