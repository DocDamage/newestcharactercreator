"""Mock-worker fitted playback transaction faults; not Blender evidence."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import test_native_fit_coordinator as fit_fixtures
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.jobs.fitted_playback import prepare_fitted_playback
from ucc.library.provenance import AssetPolicyError


class FittedPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fit_fixtures.NativeFitCoordinatorTests('test_three_distinct_staged_jobs_and_png_checks_precede_candidate_publication')
        self.fixture.setUpClass();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture;self.preview=self.f.fit();self.fault=None;self.operations=[]

    def run_playback(self,**overrides):
        def worker(request,**kw):
            self.operations.append(request.operation);out=self.f.store.root/'.ucc-jobs'/request.job_id;out.mkdir()
            for n,p in kw['staged_inputs'].items():(out/n).write_bytes(p.read_bytes())
            if self.fault=='source':self.f.source.write_bytes(b'changed')
            if self.fault=='staged':(out/'contact_fit.json').write_bytes(b'changed')
            if self.fault=='policy':self.f.policy_path.write_bytes(b'changed')
            if self.fault=='revision':self.f.store.save(replace(self.f.project,revision=self.f.project.revision+1),expected_revision=self.f.project.revision)
            if self.fault=='cancel':self.f.cancel.set()
            return SimpleNamespace(details={'unit_mock_only':True}),out
        surface=SimpleNamespace(status='CHECKED',flagged_frames=())
        if self.fault=='surface':surface.flagged_frames=(1,)
        def read_cache(*args,**kw):
            if self.fault=='cache':raise ValidationError('unit invalid cache')
            return SimpleNamespace(frame_count=5)
        args={'source_fbx':self.f.source,'permission':self.f.permission,'blender_exe':Path('unit.blender'),
              'worker_script':Path('unit.py'),'cancel':self.f.cancel};args.update(overrides)
        with (patch('ucc.jobs.fitted_playback.read_native_profile',return_value=(self.f.profile,'unit')),
             patch('ucc.jobs.fitted_playback.validate_snapshot'),patch('ucc.jobs.fitted_playback.read_native_timeline',return_value=(self.f.base,None)),
             patch('ucc.jobs.fitted_playback.validate_fitted_data',return_value=(None,surface,None)),
             patch('ucc.jobs.fitted_playback.read_fitted_cache',side_effect=read_cache),
             patch('ucc.jobs.fitted_playback.BlenderJobRunner.run',side_effect=worker)):
            return prepare_fitted_playback(self.f.store,self.preview,**args)

    def test_distinct_fresh_job_and_unchanged_saved_project(self):
        result=self.run_playback();self.assertEqual(self.operations,['cache_native_fit'])
        self.assertEqual(self.f.store.load(),self.f.project);self.assertIs(result.fitted_preview,self.preview)
        self.assertEqual(result.fitted_scene_sha256,self.preview.fitted_scene_sha256)

    def test_unreviewed_license_stale_project_and_cancel_precede_worker(self):
        with self.assertRaises(AssetPolicyError):self.run_playback(permission=replace(self.f.permission,reviewed=False))
        self.f.cancel.set()
        with self.assertRaises(ProjectStorageError):self.run_playback()
        self.f.cancel.clear();self.f.store.save(replace(self.f.project,revision=self.f.project.revision+1),expected_revision=self.f.project.revision)
        with self.assertRaises(ProjectConflict):self.run_playback()
        self.assertFalse(self.operations)

    def test_input_staged_revision_cancel_unresolved_surface_and_invalid_cache_never_publish(self):
        for fault in ('source','staged','policy','revision','cancel','surface','cache'):
            with self.subTest(fault=fault):
                case=FittedPlaybackTests();case.setUp()
                try:
                    case.fault=fault
                    with self.assertRaises((ProjectConflict,ProjectStorageError,ValidationError)):case.run_playback()
                finally:case.doCleanups()


if __name__=='__main__':unittest.main()
