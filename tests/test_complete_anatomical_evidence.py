"""Synthetic receipt/envelope tests; reused W parsers are tested separately."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_central_surface_intake import surface_contract
from ucc.animations.contact_fit import HASHES
from ucc.core.errors import ValidationError
from ucc.jobs.complete_anatomical_evidence import RECORDS,validate_complete_measurement,validate_complete_receipt,read_complete_anatomy
from ucc.preview.central_surface import POLICY


class CompleteAnatomicalEvidenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        self.bindings={k:'a'*64 for k in HASHES};self.base={'source_frame_count':3}
        self.raw,self.cache,self.volume,self.polygons=surface_contract()
        self.flags={'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        self.full={'schema_version':1,'policy':POLICY,'bindings':self.bindings,'source_frame_count':3,'paired':False,
            'polygon_topology_sha256':'d'*64,'original':self.raw,'fitted':None,'originals_unchanged':True,**self.flags}
        self.area={'polygons':self.polygons,'polygon_topology_sha256':'d'*64}
        self.write()

    def write(self,paired=False):
        self.report={'status':'REAL_COMPLETE_ANATOMICAL_SAFETY_MEASURED','bindings':self.bindings,'frames':3,'originals_unchanged':True,**self.flags}
        data={'report':self.area,'enclosure_report':{'original':self.volume,'fitted':self.volume if paired else None},'full_trunk_report':self.full}
        for key,(name,_,_) in RECORDS.items():
            path=self.folder/name;path.write_text(json.dumps(data[key]),encoding='utf-8')
            self.report[key]={'name':name,'bytes':path.stat().st_size,'sha256':sha256(path.read_bytes()).hexdigest()}
        self.receipt={'status':'REAL_COMPLETE_ANATOMICAL_SAFETY_VERIFIED',
            'bindings':{**self.bindings,**{h:self.report[k]['sha256'] for k,(_,h,_) in RECORDS.items()}},
            'frames_verified':3,'paired':paired,'originals_unchanged':True,**self.flags}

    def read(self,**kwargs):
        with patch('ucc.jobs.complete_anatomical_evidence.parse_body_contact_areas',return_value=SimpleNamespace(unit_only=True)),\
             patch('ucc.jobs.complete_anatomical_evidence.read_central_enclosure',return_value=SimpleNamespace(unit_only=True)):
            return read_complete_anatomy(self.folder,self.report,self.receipt,self.bindings,self.base,{},self.cache,**kwargs)

    def test_all_three_files_and_complete_geometry_are_required_before_semantics_return(self):
        result=self.read();self.assertEqual(result.full_trunk.original.surface.pairs,((1,0),)*3)
        self.assertIsNone(result.full_trunk.fitted);self.assertIsNone(result.full_trunk.new_area_frames)

    def test_paired_intake_derives_stable_area_and_per_hand_count_changes(self):
        self.bindings={**self.bindings,**{k:'a'*64 for k in ('fit_sha256','fitted_sha256','fit_report_sha256')}}
        self.full.update(bindings=self.bindings,paired=True,fitted=deepcopy(self.raw))
        row=self.full['fitted']['frames'][1];hit=row['observation']['left']
        hand=hit['selected_hand_triangles'][1];hit['hand_triangles']=[hand]
        _,indices=self.cache.frame(1);vertices=struct.unpack_from('<III',indices,hand*12)
        hit['hand_polygons']=[next(i for i,p in enumerate(self.polygons) if set(vertices)<=set(p))]
        hit=self.full['fitted']['frames'][2]['observation']['left']
        body=self.full['fitted']['frames'][2]['observation']['body_triangle_ids'][:2]
        hit.update(pair_count=2,central_triangles=body)
        self.write(paired=True)
        result=self.read(fitted_timeline={'unit_only':True},fitted_cache=self.cache)
        self.assertEqual(result.full_trunk.new_area_frames,(1,))
        self.assertEqual(result.full_trunk.more_hand_pair_frames,(2,))

    def test_measurement_record_sizes_flags_and_exact_bindings_are_closed(self):
        for fault in ('status','extra','approval','bytes','bool_bytes','filename','record_hash','binding','count'):
            report=deepcopy(self.report)
            if fault=='status':report['status']='REAL_ANATOMICAL_SAFETY_MEASURED'
            if fault=='extra':report['allow_partial']=True
            if fault=='approval':report['contact_quality_verified']=True
            if fault=='bytes':report['full_trunk_report']['bytes']=64*1024*1024+1
            if fault=='bool_bytes':report['report']['bytes']=True
            if fault=='filename':report['full_trunk_report']['name']='../elsewhere.json'
            if fault=='record_hash':report['enclosure_report']['sha256']='bad'
            if fault=='binding':report['bindings']['source_sha256']='b'*64
            if fault=='count':report['frames']=True
            with self.subTest(fault=fault),self.assertRaises(ValidationError):
                validate_complete_measurement(report,self.bindings,self.base,False)

    def test_receipt_must_bind_every_report_with_full_frame_coverage_and_no_approval(self):
        validate_complete_receipt(self.receipt,self.report,self.bindings,self.base,False)
        for fault in ('body_review_sha256','enclosure_review_sha256','full_trunk_review_sha256','status','count','bool','paired','approval'):
            receipt=deepcopy(self.receipt)
            if fault.endswith('sha256'):receipt['bindings'].pop(fault)
            if fault=='status':receipt['status']='REAL_ANATOMICAL_SAFETY_VERIFIED'
            if fault=='count':receipt['frames_verified']=2
            if fault=='bool':receipt['frames_verified']=True
            if fault=='paired':receipt['paired']=True
            if fault=='approval':receipt['engine_import_verified']=True
            with self.subTest(fault=fault),self.assertRaises(ValidationError):
                validate_complete_receipt(receipt,self.report,self.bindings,self.base,False)

    def test_changed_report_bytes_reject_even_with_an_unchanged_valid_receipt(self):
        for key,(name,_,_) in RECORDS.items():
            self.write();path=self.folder/name;path.write_bytes(path.read_bytes()+b' ')
            with self.subTest(report=key),self.assertRaises(ValidationError):self.read()

    def test_rehashed_policy_coverage_topology_or_hidden_fitted_payload_reject(self):
        original=deepcopy(self.full)
        for fault in ('policy','version','frame','topology','approve','fitted','selection','extra'):
            self.full=deepcopy(original)
            if fault=='policy':self.full['policy']='HAND_CENTRAL_BODY_TRIANGLES_V1'
            if fault=='version':self.full['schema_version']=True
            if fault=='frame':self.full['source_frame_count']=2
            if fault=='topology':self.full['polygon_topology_sha256']='e'*64
            if fault=='approve':self.full['contact_quality_verified']=True
            if fault=='fitted':self.full['fitted']={}
            if fault=='selection':self.full['original']['frames'][0]['observation']['body_triangle_ids'].pop()
            if fault=='extra':self.full['override']=True
            self.write()
            with self.subTest(fault=fault),self.assertRaises(ValidationError):self.read()

    def test_cancellation_and_missing_fitted_timeline_do_not_return_partial_evidence(self):
        def cancelled():raise RuntimeError('unit intake cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.read(cancel_check=cancelled)
        with self.assertRaises(ValidationError):self.read(fitted_cache=self.cache)


if __name__=='__main__':unittest.main()
