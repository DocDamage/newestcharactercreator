"""Private cache intake faults with synthetic data; source-FK parsing is mocked."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4
import unittest
from unittest.mock import patch

import test_native_playback as playback_fixture
from fixtures.surface_cache_contract import write_surface_cache
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError,ProjectConflict
from ucc.jobs.contact_fit_context import contact_context
from ucc.jobs.native_playback import NativePlayback
from ucc.jobs.protocol import JobResult


class ContactFitContextTests(unittest.TestCase):
    def setUp(self):
        self.f=playback_fixture.PlaybackCoordinatorTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;jobs=f.store.root/'.ucc-jobs';self.folder=jobs/str(uuid4());self.folder.mkdir()
        self.verify_folder=jobs/str(uuid4());self.verify_folder.mkdir()
        self.data,self.report,_b,self.timeline,self.profile,self.surface,self.verified=write_surface_cache(self.folder)
        (f.folder/'target_timeline.json').write_text(json.dumps(self.timeline))
        f.preview.worker_report['timeline']=file_record(f.folder/'target_timeline.json')
        self.options={**f.bindings,'review_sha256':f.digest(f.folder/'review_motion.blend'),
                      'timeline_sha256':f.digest(f.folder/'target_timeline.json')}
        self.report['bindings']=dict(self.options);self.report['saved_review_verification']['bindings']=dict(self.options)
        self.data['bindings']=dict(self.options);self.surface['bindings']=dict(self.options)
        self.verified['saved_review_verification']['bindings']=dict(self.options)
        self.write()
        self.playback=NativePlayback(f.project.project_id,f.project.revision,f.bindings['master_sha256'],f.bindings['source_sha256'],
            None,self.folder.name,str(self.folder/'motion_skin.json'),self.verify_folder.name)

    def write(self,operation='cache_native_fbx_body'):
        p=self.folder/'motion_contacts.json';p.write_text(json.dumps(self.surface));record=file_record(p)
        self.report['surface_review']=record;self.data['surface_review']=record
        p=self.folder/'motion_skin.json';p.write_text(json.dumps(self.data));self.report['manifest']=file_record(p)
        self.verified['bindings']={**self.options,'surface_review_sha256':record['sha256']}
        (self.folder/'result.json').write_text(json.dumps(JobResult(self.folder.name,operation,'ok',self.report).as_dict()))
        (self.verify_folder/'result.json').write_text(json.dumps(JobResult(self.verify_folder.name,'verify_native_surface_review','ok',self.verified).as_dict()))

    def load(self):
        f=self.f
        with (patch('ucc.jobs.contact_fit_context.read_native_profile',return_value=(self.profile,f.bindings['mapping_sha256'])),
              patch('ucc.jobs.contact_fit_context.validate_snapshot'),
              patch('ucc.jobs.contact_fit_context.read_native_timeline',return_value=(self.timeline,f.folder/'target_timeline.json'))):
            return contact_context(f.store,f.preview,self.playback,source_fbx=f.source)

    def test_cache_and_surface_are_redecoded_with_current_original_bindings(self):
        ctx=self.load();self.assertEqual(ctx.playback.cache.frame_count,3)
        self.assertEqual(ctx.playback.cache.surface_review.flagged_frames,(1,))
        self.assertEqual(len(ctx.staged),6);self.assertEqual(ctx.bindings,self.options)
        self.assertEqual(ctx.expected['motion_contacts.json'],self.report['surface_review']['sha256'])

    def test_source_revision_map_scope_missing_receipt_geometry_and_partial_surface_reject(self):
        for fault in ('source','revision','bindings','operation','receipt','missing','geometry','surface','path'):
            with self.subTest(fault=fault):
                case=ContactFitContextTests();case.setUp()
                try:
                    if fault=='source':case.f.source.write_bytes(b'changed')
                    if fault=='revision':case.playback=replace(case.playback,revision=case.playback.revision+1)
                    if fault=='bindings':case.report['bindings']['mapping_sha256']='d'*64;case.write()
                    if fault=='operation':case.write(operation='inspect_environment')
                    if fault=='receipt':case.verified['frames_verified']=2;case.write()
                    if fault=='missing':case.playback=replace(case.playback,surface_verification_job_id='')
                    if fault=='geometry':(case.folder/'motion_skin.bin').write_bytes(b'replaced')
                    if fault=='surface':case.surface['frames'].pop();case.write()
                    if fault=='path':case.playback=replace(case.playback,private_manifest=str(case.f.root/'outside/motion_skin.json'))
                    with self.assertRaises((ValidationError,ProjectConflict)):case.load()
                finally:case.doCleanups()


if __name__=='__main__':unittest.main()
