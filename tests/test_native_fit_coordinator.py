"""Mock-worker transaction faults; fake files here never count as Blender proof."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.contact_fit_contract import baseline_contract,fitted_contract,stage_report,record,write_render_report
from fixtures.private_render_png import png
from ucc.core.errors import ValidationError,ProjectStorageError,ProjectConflict
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.core.master_versions import stage_unverified_master
from ucc.jobs.native_body import NativeBodyPreview
from ucc.jobs.native_fit import fit_native_preview
from ucc.jobs.native_fit_evidence import read_fitted_timeline as actual_reader
from ucc.library.provenance import LicensePolicy,AssetPolicyError


class NativeFitCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.images=[png(phase=i*9) for i in range(5)]

    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.store=ProjectStore(self.root/'hero');self.store.save(CharacterProject.new('Target fitting unit fixture'))
        source_master=self.root/'unit.blend';source_master.write_bytes(b'BLENDER_UNIT_NOT_REAL'*1000)
        saved=stage_unverified_master(self.store,source_master,authorized_source_root=self.root)
        self.master=saved.master_path;self.project=saved.project
        self.folder=self.store.root/'.ucc-jobs/unit-original';self.folder.mkdir(parents=True)
        self.policy,self.original_bindings,self.base,self.profile,self.parents,_=baseline_contract()
        for name in ('source_snapshot.json','native_mapping.json'):(self.folder/name).write_text('{}')
        (self.folder/'target_timeline.json').write_text(json.dumps(self.base))
        (self.folder/'review_motion.blend').write_bytes(b'UNIT_ONLY_NOT_A_SAVED_ANIMATION')
        self.source=self.root/'unit.fbx';self.source.write_bytes(b'NOT_FBX_UNIT_BOUNDARY_ONLY')
        self.digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.bindings={'source_sha256':self.digest(self.source),'snapshot_sha256':self.digest(self.folder/'source_snapshot.json'),
                       'mapping_sha256':self.digest(self.folder/'native_mapping.json'),'master_sha256':self.digest(self.master)}
        raw={'bindings':dict(self.bindings),'timeline':record(self.folder/'target_timeline.json'),
             'visual_review_blend':record(self.folder/'review_motion.blend')}
        self.preview=NativeBodyPreview(self.project.project_id,self.project.revision,self.bindings['master_sha256'],self.bindings['source_sha256'],
             self.base,str(self.folder/'review_motion.blend'),'',str(self.folder/'target_timeline.json'),
             ('unit-first','unit-second'),str(self.folder/'native_mapping.json'),raw)
        self.original_bindings={**self.bindings,'review_sha256':raw['visual_review_blend']['sha256'],'timeline_sha256':raw['timeline']['sha256']}
        self.policy['bindings']=dict(self.original_bindings);self.policy_path=self.root/'unit-contact-fit.json';self.policy_path.write_text(json.dumps(self.policy))
        self.permission=LicensePolicy('unit original','CC0','unit-original://target-fit',reviewed=True,local_preview_allowed=True,no_ai=True)
        self.cancel=Event();self.fault=None;self.operations=[];self.data=None

    def fit(self,**overrides):
        def worker(request,**kwargs):
            self.operations.append(request.operation);self.assertIs(kwargs['cancel'],self.cancel)
            folder=self.store.root/'.ucc-jobs'/request.job_id;folder.mkdir()
            for name,path in kwargs['staged_inputs'].items():(folder/name).write_bytes(path.read_bytes())
            _,_,_,_,rest,data=fitted_contract(request.options,self.base)
            if request.operation=='fit_native_fbx_body':
                path=folder/'fitted_motion.blend';path.write_bytes(b'UNIT_ONLY_NOT_AN_ACTUAL_FITTED_SCENE')
                raw=stage_report(request.options,rest);raw['fitted_scene']=record(path)
                if self.fault=='staged':(folder/'candidate.blend').write_bytes(b'TAMPERED_UNIT_COPY')
                if self.fault=='policy':self.policy_path.write_text('{}')
                if self.fault=='stage_receipt':raw['original_review_verification']['frames_verified']=4
            elif request.operation=='measure_native_fit':
                self.data=data;path=folder/'fitted_timeline.json';path.write_text(json.dumps(data));self.measure_path=path
                raw={'status':'REAL_NATIVE_FIT_MEASURED','bindings':dict(request.options),'frames':5,'timeline':record(path),
                     'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
                if self.fault=='source':self.source.write_bytes(b'UNIT_SOURCE_EDIT')
                if self.fault=='cancel':self.cancel.set()
                if self.fault=='revision':self.store.save(replace(self.store.load(),revision=self.project.revision+1))
            else:
                raw=write_render_report(folder,request.options,self.data,self.images)
                if self.fault=='approval':raw['contact_quality_verified']=True
                if self.fault=='fresh':raw['frames_verified']=4
                if self.fault=='image':(folder/'review_frames/frame_0001_front.png').unlink()
                if self.fault=='canonical':self.measure_path.write_text('{}')
            return SimpleNamespace(details=raw),folder
        def reader(*args,**kwargs):
            data,path,plan,surface,angular=actual_reader(*args,**kwargs)
            # Explicitly mocked contact detector; this is a coordinator unit test.
            verdict=surface if self.fault=='unavailable' else SimpleNamespace(status='CHECKED',flagged_frames=(2,) if self.fault=='partial' else ())
            return data,path,plan,verdict,angular
        args={'source_fbx':self.source,'fit_policy':self.policy_path,'permission':self.permission,
              'blender_exe':Path('unit-blender'),'worker_script':Path('unit-worker'),'cancel':self.cancel}
        args.update(overrides)
        with patch('ucc.jobs.native_fit.validate_snapshot'),patch('ucc.jobs.native_fit.read_native_profile',return_value=(self.profile,self.bindings['mapping_sha256'])),\
             patch('ucc.jobs.native_fit.read_native_timeline',return_value=(self.base,self.folder/'target_timeline.json')),\
             patch('ucc.jobs.native_fit.read_fitted_timeline',side_effect=reader),patch('ucc.jobs.native_fit.BlenderJobRunner.run',side_effect=worker):
            return fit_native_preview(self.store,self.preview,**args)

    def test_three_distinct_staged_jobs_and_png_checks_precede_candidate_publication(self):
        before=self.digest(self.master);result=self.fit()
        self.assertEqual(self.operations,['fit_native_fbx_body','measure_native_fit','verify_native_fit'])
        self.assertEqual(len(set(result.worker_job_ids)),3);self.assertFalse(result.contact_quality_verified)
        self.assertEqual(self.digest(self.master),before);self.assertEqual(self.store.load(),self.project)
        self.assertTrue(Path(result.private_render_review).is_file())

    def test_license_cancel_and_stale_project_fail_before_any_worker(self):
        with self.assertRaises(AssetPolicyError):self.fit(permission=replace(self.permission,reviewed=False))
        self.cancel.set()
        with self.assertRaises(ProjectStorageError):self.fit()
        self.cancel.clear();self.preview=replace(self.preview,revision=self.preview.revision+1)
        with self.assertRaises(ProjectConflict):self.fit()
        self.assertFalse(self.operations)

    def test_input_changes_cancel_revision_and_failed_receipts_never_publish(self):
        for fault in ('staged','policy','stage_receipt','source','cancel','revision','unavailable','partial','approval','fresh','image','canonical'):
            # Each transaction gets an independent temporary project.
            other=NativeFitCoordinatorTests('test_three_distinct_staged_jobs_and_png_checks_precede_candidate_publication')
            other.setUp();self.addCleanup(other.doCleanups);other.fault=fault
            before=other.digest(other.master)
            with self.subTest(fault=fault),self.assertRaises((ValidationError,ProjectStorageError,ProjectConflict)):other.fit()
            self.assertEqual(other.digest(other.master),before)
            if fault in ('staged','policy','stage_receipt'):self.assertEqual(len(other.operations),1)
            if fault in ('unavailable','partial'):self.assertEqual(len(other.operations),2)


if __name__=='__main__':unittest.main()
