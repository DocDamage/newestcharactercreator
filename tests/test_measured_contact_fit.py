"""Mocked transaction boundaries; invented contacts are not Blender evidence."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_native_fit_coordinator as fit_fixture
from fixtures.contact_fit_contract import fitted_contract,stage_report,record
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.jobs.contact_fit import fit_measured_contacts
from ucc.jobs.contact_fit_context import ContactFitContext
from ucc.jobs.native_playback import NativePlayback
from ucc.library.provenance import AssetPolicyError
from ucc.preview.surface_review import SurfaceReview


class MeasuredContactFitTests(unittest.TestCase):
    def setUp(self):
        self.f=fit_fixture.NativeFitCoordinatorTests();self.f.setUpClass();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;contacts=f.folder/'motion_contacts.json';contacts.write_text('{"unit_only":true}')
        self.staged={'candidate.blend':f.master,'review_motion.blend':f.folder/'review_motion.blend',
            'target_timeline.json':f.folder/'target_timeline.json','source_snapshot.json':f.folder/'source_snapshot.json',
            'native_mapping.json':f.folder/'native_mapping.json','motion_contacts.json':contacts}
        expected={n:f.digest(p) for n,p in self.staged.items()}
        surface=SurfaceReview('CHECKED','',((),)*5,((0,0),(0,0),(0,1),(0,0),(0,0)),('a'*64,)*5)
        cache=SimpleNamespace(surface_review=surface,world_matrix=(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1))
        self.playback=NativePlayback(f.project.project_id,f.project.revision,f.preview.master_sha256,
            f.preview.source_sha256,cache,'unit-cache',str(f.folder/'motion_skin.json'),'unit-surface')
        self.ctx=ContactFitContext(f.project,f.base,f.profile,f.original_bindings,self.staged,expected,self.playback)
        self.source_area_path=f.folder/'unit-source-areas.json';self.source_area_path.write_text('{"unit_only":true}')
        self.source_review=SimpleNamespace(report_sha256=f.digest(self.source_area_path),areas=SimpleNamespace(polygon_sha256='a'*64))
        self.fault=None;self.operations=[]

    def run_fit(self,**overrides):
        f=self.f
        def worker(request,**kw):
            self.operations.append(request.operation);folder=f.store.root/'.ucc-jobs'/request.job_id;folder.mkdir()
            for n,p in kw['staged_inputs'].items():(folder/n).write_bytes(p.read_bytes())
            _p,_opts,_base,_profile,rest,_data=fitted_contract(request.options,f.base)
            path=folder/'proposed_contact_fit.json';policy=dict(f.policy)
            if self.fault=='angular':
                from copy import deepcopy
                policy=deepcopy(policy);policy['policy']='BOUNDED_NATIVE_ARM_HAND_IK_V2'
                for row,v in zip(policy['frames'],(0.,.1,.5,.1,0.)):row['hand_rotation_local_degrees']=[v,0.,0.]
                for matrix in f.base['full_timeline_frames'][2]['target_global_poses'][3:5]:
                    for i,v in zip((0,1,4,5),(-1.,0.,0.,-1.)):matrix[i]=v
            if self.fault=='omit_crossing':
                policy['frames']=[{'frame':i+1,'offset_world':([.00025,0,0] if i==1 else [0,0,0])} for i in range(5)]
            path.write_text(json.dumps(policy))
            source_receipt={'status':'REAL_NATIVE_SURFACE_REVIEW_VERIFIED','bindings':{k:v for k,v in request.options.items() if k!='source_body_areas_sha256'},'frames_verified':5,
                'saved_review_verification':stage_report(request.options,rest)['original_review_verification'],
                'world_matrix':list(self.playback.cache.world_matrix),'originals_unchanged':True,'contact_quality_verified':False}
            raw={'status':'REAL_NATIVE_CONTACT_CANDIDATE_PROPOSED','algorithm':'BOUNDED_HAND_CONTACT_AREA_SEARCH_V3','bindings':dict(request.options),
                'source_surface_verification':source_receipt,'target_rest_frames':rest,'policy':record(path),
                'source_frames_verified':5,'contact_interval':[3,3],'candidate_interval':[2,4],
                'candidate_frames_checked':3,'candidate_pose_tests':10,'candidate_trials':2,'candidate_intersection_pairs':0,
                'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
            raw['body_area_verification']={'policy':'NO_NEW_CENTRAL_BODY_POLYGONS_V1','source_frames_verified':5,
                'polygon_topology_sha256':'a'*64,'candidate_frames_checked':3,'new_area_frames':0,'more_hand_pair_frames':0,'rejected_pose_observations':1}
            if self.fault=='new_area':raw['body_area_verification']['new_area_frames']=1
            if self.fault=='body_crop':raw['body_area_verification']['candidate_frames_checked']=2
            if self.fault=='body_baseline':raw['body_area_verification']['polygon_topology_sha256']='e'*64
            if self.fault=='late_baseline':self.source_area_path.write_bytes(b'changed')
            if self.fault=='source':f.source.write_bytes(b'changed')
            if self.fault=='staged':(folder/'candidate.blend').write_bytes(b'changed')
            if self.fault=='revision':f.store.save(replace(f.project,revision=f.project.revision+1),expected_revision=f.project.revision)
            if self.fault=='cancel':f.cancel.set()
            if self.fault=='scope':raw['contact_quality_verified']=True
            if self.fault=='algorithm':raw['algorithm']='UNBOUNDED_V0'
            if self.fault=='trials':raw['candidate_trials']=501
            if self.fault=='receipt':source_receipt['frames_verified']=4
            if self.fault=='interval':raw['candidate_interval']=[2,3]
            if self.fault=='crop':raw['candidate_frames_checked']=2
            if self.fault=='budget':raw['candidate_pose_tests']=1025
            if self.fault=='bool':raw['candidate_intersection_pairs']=False
            if self.fault=='rest':raw['target_rest_frames']['hand']['parent']='hand'
            return SimpleNamespace(details=raw),folder
        def bake(*args,**kw):
            self.operations.append('fit_native_preview')
            if self.fault=='bake':raise ValidationError('unit rejected saved fit')
            return SimpleNamespace(unit_only=True)
        def cache(*args,**kw):
            self.operations.append('prepare_fitted_playback')
            if self.fault=='cache':raise ValidationError('unit rejected fitted cache')
            return SimpleNamespace(unit_only=True)
        def body(*args,**kw):
            if 'fitted' not in kw:
                self.operations.append('review_source_body_areas')
                if self.fault=='source_review':raise ValidationError('unit source-area review failed')
                if self.fault=='source_cancel':f.cancel.set()
                return self.source_review
            self.operations.append('review_body_contact_areas')
            if self.fault=='body':raise ValidationError('unit incomplete body areas')
            if self.fault=='body_cancel':f.cancel.set()
            return SimpleNamespace(unit_only=True)
        def guard(review):
            self.operations.append('require_body_fit_guard')
            if self.fault=='body_guard':raise ValidationError('unit unsafe new contact areas')
            return SimpleNamespace(unit_only=True)
        args={'source_fbx':f.source,'permission':f.permission,'blender_exe':Path('unit.blender'),
              'worker_script':Path('unit.py'),'cancel':f.cancel};args.update(overrides)
        with (patch('ucc.jobs.contact_fit.contact_context',return_value=self.ctx),
              patch('ucc.jobs.contact_fit.BlenderJobRunner.run',side_effect=worker),
              patch('ucc.jobs.contact_fit.fit_native_preview',side_effect=bake),
              patch('ucc.jobs.contact_fit.prepare_fitted_playback',side_effect=cache),
              patch('ucc.jobs.contact_fit.review_body_contact_areas',side_effect=body),
              patch('ucc.jobs.contact_fit.source_area_inputs',return_value=(self.source_area_path,self.source_review.report_sha256)),
              patch('ucc.jobs.contact_fit.require_body_fit_guard',side_effect=guard)):
            return fit_measured_contacts(f.store,f.preview,self.playback,**args)

    def test_candidate_then_saved_fit_then_cache_before_any_pair_is_returned(self):
        result=self.run_fit();self.assertEqual(self.operations,['review_source_body_areas','propose_native_hand_contact_fit','fit_native_preview','prepare_fitted_playback',
            'review_body_contact_areas','require_body_fit_guard'])
        self.assertIsNotNone(result.body_review);self.assertIsNotNone(result.body_fit_guard)
        self.assertIs(result.source_body_review,self.source_review)
        self.assertTrue(result.candidate_job_id);self.assertTrue(Path(result.private_candidate_policy).is_file())
        self.assertEqual(self.f.store.load(),self.f.project);self.assertIs(result.original,self.playback)

    def test_license_denial_precedes_context_or_worker(self):
        with self.assertRaises(AssetPolicyError):self.run_fit(permission=replace(self.f.permission,reviewed=False))
        self.assertFalse(self.operations)

    def test_world_hand_angular_rejection_precedes_baking(self):
        self.fault='angular'
        with self.assertRaisesRegex(ValidationError,'angular'):self.run_fit()
        self.assertNotIn('fit_native_preview',self.operations)

    def test_all_faults_keep_original_and_never_return_partial_comparison(self):
        for fault in ('source','staged','revision','cancel','scope','algorithm','trials','receipt','interval','crop','budget','bool','rest','omit_crossing','bake','cache','body','body_guard','body_cancel','source_review','source_cancel','new_area','body_crop','body_baseline','late_baseline'):
            with self.subTest(fault=fault):
                case=MeasuredContactFitTests();case.setUp()
                try:
                    case.fault=fault
                    with self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError)):case.run_fit()
                finally:case.doCleanups()


if __name__=='__main__':unittest.main()
