"""NONSHIPPING pipeline doubles test publication, guards and real observer seams."""
from pathlib import Path
from types import SimpleNamespace
from threading import Event
from unittest.mock import patch
from contextlib import closing
import tempfile
import unittest
import json

from fixtures.target_action_logic import TargetFixture, clock_snapshot
from fixtures.target_action_contract import metadata_pair
from ucc.core.errors import ProjectStorageError, ProjectConflict, ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.native_body import NativeBodyPreview
from ucc.jobs.neutral_master import NeutralMasterInspection
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.jobs.target_action import prepare_target_action, list_target_action_bindings, load_target_action
import test_fbx_intake as intake_tests


class TargetActionPreparationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.f=TargetFixture(Path(temp.name).resolve()); _, b=metadata_pair(); self.ids=b.producer
        self.mapping=self.f.root/'mapping.json'; self.mapping.write_text('NONSHIPPING_EXPLICIT_MAPPING')
        from ucc.jobs.master_preview import _digest
        self.mapping_sha=_digest(self.mapping); self.cache=object(); self.cancel=Event()
        self.snapshot=clock_snapshot(); self.snapshot['source_sha256']=self.f.source_sha
        self.snapshot_bytes=json.dumps(self.snapshot).encode()
        self.assertEqual(_digest_bytes(self.snapshot_bytes),self.f.review.source.snapshot_sha256)

    def worker(self, job_id, operation, details=None):
        folder=self.f.store.root/'.ucc-jobs'/job_id; folder.mkdir(parents=True)
        request={'job_id':job_id,'operation':operation,'NONSHIPPING_LOGIC_ONLY':True}
        result={'job_id':job_id,'operation':operation,'status':'ok','details':details or {}}
        (folder/'request.json').write_text(json.dumps(request)); (folder/'result.json').write_text(json.dumps(result))
        return folder

    def neutral(self, store, **kwargs):
        for job in self.ids.neutral_worker_job_ids:
            self.worker(job,'inspect_mpfb_neutral_master',{'expression_key_count':0})
        return NeutralMasterInspection(self.f.project.project_id,self.f.project.revision,
            kwargs.get('expected_project_sha256',''),self.f.master_sha,
            {'state_sha256':'7'*64,'rest_sha256':'8'*64},self.ids.neutral_worker_job_ids)

    def native(self, store, **kwargs):
        for job in self.ids.source_intake_worker_job_ids:
            folder=self.worker(job,'inspect_fbx_animation')
            (folder/'source_snapshot.json').write_bytes(self.snapshot_bytes)
            request=JobRequest(job,'inspect_fbx_animation',None,{'source_sha256':self.f.source_sha})
            details={'snapshot':{'name':'source_snapshot.json','bytes':len(self.snapshot_bytes),'sha256':_digest_bytes(self.snapshot_bytes)}}
            kwargs['source_intake_observer'](request,JobResult(job,'inspect_fbx_animation','ok',details),folder)
        for job in self.ids.body_worker_job_ids:
            folder=self.worker(job,'verify_native_fbx_body')
            (folder/'target_timeline.json').write_text('NONSHIPPING_TIMELINE')
            (folder/'review_motion.blend').write_bytes(b'BLENDER_NONSHIPPING_LOGIC_MARKER')
            (folder/'source_snapshot.json').write_bytes(self.snapshot_bytes)
        self.worker(self.ids.body_reopen_job_id,'reopen_native_fbx_body')
        first=self.f.store.root/'.ucc-jobs'/self.ids.body_worker_job_ids[0]
        from ucc.core.target_action_format import RETAINED_FILES
        for name in RETAINED_FILES:
            if name.startswith('body_first/review_frames/'):
                path=first/name.removeprefix('body_first/'); path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'NONSHIPPING_NO_RENDER_PIXELS')
        return NativeBodyPreview(self.f.project.project_id,self.f.project.revision,self.f.master_sha,
            self.f.source_sha,{},str(first/'review_motion.blend'),'NONSHIPPING',str(first/'target_timeline.json'),
            self.ids.body_worker_job_ids,str(self.mapping),{},self.ids.body_reopen_job_id,{},
            self.ids.source_intake_worker_job_ids)

    def playback(self, store, preview, **kwargs):
        folder=self.worker(self.ids.cache_job_id,'cache_native_fbx_body')
        self.worker(self.ids.surface_verification_job_id,'verify_native_surface_review')
        for name in ('motion_skin.json','motion_skin.bin','motion_contacts.json'):
            (folder/name).write_bytes(b'NONSHIPPING_NOT_CACHE_ADMISSION')
        return SimpleNamespace(job_id=self.ids.cache_job_id,surface_verification_job_id=self.ids.surface_verification_job_id)

    def prepare(self, **extra):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name,value in (('inspect_saved_neutral_master',self.neutral),('preview_native_body',self.native),
                               ('prepare_native_playback',self.playback)):
                stack.enter_context(patch('ucc.jobs.target_action_preparation.'+name,side_effect=value))
            stack.enter_context(patch('ucc.jobs.target_action_preparation.read_native_profile',return_value=(
                {'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1','root_motion_policy':'SOURCE_HIP_MIDPOINT_V1'},self.mapping_sha)))
            self.native_reader=stack.enter_context(patch(
                'ucc.jobs.target_action_evidence.validate_retained_target_action',return_value=self.cache))
            return prepare_target_action(self.f.store,database_path=self.f.database,clip_id=self.f.clip_id,
                expected_source_sha256=self.f.source_sha,expected_policy=self.f.policy,mapping_profile=self.mapping,
                expected_mapping_sha256=self.mapping_sha,expected_source_binding_sha256=self.f.review.source.source_binding_sha256,
                expected_catalog_record_sha256=self.f.review.source.catalog_record_sha256,
                blender_exe=self.f.executable,worker_script=self.f.script,purpose='NONSHIPPING_LOGIC_ONLY',
                local_preview_confirmed=True,cancel=self.cancel,**self.f.context(),**extra)

    def test_complete_sealed_unit_has_45_proofs_and_binding_and_preserves_registered_project(self):
        original=self.f.store.file.read_bytes(); result=self.prepare()
        self.assertIs(result.cache,self.cache)
        self.assertEqual(len([p for p in result.directory.rglob('*') if p.is_file()]),46)
        self.assertEqual(self.f.store.file.read_bytes(),original)
        self.assertEqual(len(list_target_action_bindings(self.f.store)),1)
        # Explicit mocked numerical boundary: stage validation and common Load
        # each receive the complete retained graph, never a partial producer set.
        self.assertEqual(self.native_reader.call_count,2)
        for call in self.native_reader.call_args_list:
            directory,binding=call.args
            self.assertEqual(len(binding.files),45)
            self.assertEqual(binding.producer.source_intake_worker_job_ids,self.ids.source_intake_worker_job_ids)
            self.assertEqual(binding.producer.body_worker_job_ids,self.ids.body_worker_job_ids)

    def test_cancel_after_source_workers_never_publishes_or_runs_cache(self):
        real=self.native
        def cancelled(*a,**kw):
            value=real(*a,**kw); self.cancel.set(); return value
        self.native=cancelled
        with self.assertRaisesRegex(ProjectStorageError,'cancelled'):self.prepare()
        self.assertEqual(list_target_action_bindings(self.f.store),())

    def test_raced_foreign_destination_is_not_replaced_or_removed(self):
        def progress(phase):
            if phase=='PERSISTING':
                from ucc.core.target_action import TargetActionBinding
                path=next((self.f.store.root/'.ucc-jobs').glob('target-action-*/payload/binding.json'))
                b=TargetActionBinding.from_bytes(path.read_bytes())
                self.foreign=self.f.store.root/'animations/actions'/b.sha256
                self.foreign.mkdir(); (self.foreign/'FOREIGN.txt').write_text('FOREIGN')
        with self.assertRaises(ProjectConflict):self.prepare(progress=progress)
        self.assertEqual((self.foreign/'FOREIGN.txt').read_text(),'FOREIGN')

    def test_late_complete_callback_failure_retains_completed_immutable_binding(self):
        def progress(phase):
            if phase=='COMPLETE':raise RuntimeError('late observer fault')
        with self.assertRaisesRegex(RuntimeError,'late observer fault') as caught:self.prepare(progress=progress)
        self.assertEqual(len(list_target_action_bindings(self.f.store)),1)
        self.assertTrue(any('Completed private target binding retained' in n for n in caught.exception.__notes__))

    def test_committed_record_remains_historical_when_proof_drift_blocks_loading(self):
        def progress(phase):
            if phase=='RECORD_COMMITTED':
                self.committed=next((self.f.store.root/'animations/actions').iterdir())
                (self.committed/'playback/motion_skin.bin').write_bytes(b'CHANGED_AFTER_COMMIT')
        with self.assertRaises(ProjectStorageError) as caught:self.prepare(progress=progress)
        self.assertTrue(self.committed.is_dir())
        self.assertTrue(any(n=='Completed private target binding retained at '+str(self.committed)
                            for n in caught.exception.__notes__))
        with patch('ucc.jobs.target_action_evidence.validate_retained_target_action') as reader:
            with self.assertRaises(ProjectStorageError):
                load_target_action(self.f.store,binding_sha256=self.committed.name,**self.f.load_args())
            reader.assert_not_called()

    def test_host_code_change_before_first_worker_is_rejected(self):
        host=self.f.root/'mock-host/ucc/jobs'; host.mkdir(parents=True)
        selected=host/'target_action_preparation.py'; selected.write_text('# NONSHIPPING host marker\n')
        def progress(phase):
            if phase=='NEUTRAL_MASTER':selected.write_text('# NONSHIPPING changed host marker\n')
        from ucc.jobs.neutral_master import inspect_saved_neutral_master
        self.neutral=inspect_saved_neutral_master
        with patch('ucc.jobs.target_action_resources.__file__',str(host/'target_action_resources.py')):
            with patch('ucc.jobs.neutral_master.BlenderJobRunner.run') as runner:
                with self.assertRaisesRegex(ProjectStorageError,'host code'):self.prepare(progress=progress)
                runner.assert_not_called()

    def test_policy_change_after_first_neutral_child_rejects_before_second_launch(self):
        from ucc.jobs.neutral_master import inspect_saved_neutral_master
        from test_neutral_master import observation
        import sqlite3
        self.neutral=inspect_saved_neutral_master; calls=[]
        def worker(request,**kwargs):
            calls.append(request.job_id)
            folder=self.f.store.root/'.ucc-jobs'/request.job_id;folder.mkdir()
            (folder/'candidate.blend').write_bytes(self.f.master.read_bytes())
            with closing(sqlite3.connect(self.f.database)) as db:
                raw=json.loads(db.execute('SELECT license_json FROM asset_sources').fetchone()[0])
                raw['local_preview_allowed']=False
                db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(raw),))
                db.commit()
            return JobResult(request.job_id,request.operation,'ok',observation(self.f.master_sha)),folder
        with patch('ucc.jobs.neutral_master.BlenderJobRunner.run',side_effect=worker):
            with self.assertRaisesRegex(ValidationError,'Registered catalog source/clip/policy differs'):self.prepare()
        self.assertEqual(len(calls),1)
        self.assertEqual(list_target_action_bindings(self.f.store),())

    def test_new_worker_module_after_first_child_rejects_before_second_launch(self):
        from ucc.jobs.neutral_master import inspect_saved_neutral_master
        from test_neutral_master import observation
        self.neutral=inspect_saved_neutral_master;calls=[]
        def worker(request,**kwargs):
            calls.append(request.job_id)
            folder=self.f.store.root/'.ucc-jobs'/request.job_id;folder.mkdir()
            (folder/'candidate.blend').write_bytes(self.f.master.read_bytes())
            (self.f.script.parent/'json.py').write_text('# NONSHIPPING injected module marker\n')
            return JobResult(request.job_id,request.operation,'ok',observation(self.f.master_sha)),folder
        with patch('ucc.jobs.neutral_master.BlenderJobRunner.run',side_effect=worker):
            with self.assertRaisesRegex(ProjectStorageError,'worker code namespace changed'):self.prepare()
        self.assertEqual(len(calls),1)
        self.assertEqual(list_target_action_bindings(self.f.store),())

    def test_missing_installed_fbx_helper_fails_before_workers(self):
        for relative,message in (('addons_core/io_scene_fbx/import_fbx.py','incomplete'),
                ('modules/bpy_extras/anim_utils.py','auxiliary helper'),('modules/rna_prop_ui.py','RNA helper')):
            helper=self.f.executable.parent/'5.3/scripts'/relative
            original=helper.read_bytes(); helper.unlink()
            with self.subTest(helper=relative),self.assertRaisesRegex(ProjectStorageError,message):self.prepare()
            helper.write_bytes(original)
            self.assertEqual(list_target_action_bindings(self.f.store),())

    def test_mutated_helper_or_new_empty_directory_during_neutral_work_rejects(self):
        real=self.neutral
        def changed(*a,**kw):
            value=real(*a,**kw)
            (self.f.executable.parent/'5.3/scripts/addons_core/io_scene_fbx/new-empty-cache').mkdir()
            helper=self.f.executable.parent/'5.3/scripts/modules/bpy_extras/anim_utils.py'
            helper.write_text('# NONSHIPPING changed helper\n')
            return value
        self.neutral=changed
        with self.assertRaisesRegex(ProjectStorageError,'helper closure changed'):self.prepare()
        self.assertEqual(list_target_action_bindings(self.f.store),())


def _digest_bytes(data):
    from hashlib import sha256
    return sha256(data).hexdigest()


class IntakeObserverTests(unittest.TestCase):
    def fixture(self):
        fixture=intake_tests.FbxCoordinatorTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        return fixture

    def test_optional_observer_captures_two_actual_runner_triples_without_new_json_fields(self):
        f=self.fixture(); seen=[]
        with patch('ucc.jobs.fbx_intake.BlenderJobRunner.run',side_effect=f.run_worker):
            original=f.invoke(); observed=f.invoke(observer=lambda *triple:seen.append(triple))
        self.assertEqual(set(original),set(observed)); self.assertEqual(len(seen),2)
        self.assertEqual(len({job.job_id for job,_,_ in seen}),2)
        for request,result,folder in seen:
            self.assertEqual((request.job_id,request.operation),(result.job_id,result.operation))
            self.assertEqual(folder.name,request.job_id)

    def test_bad_source_result_never_reaches_observer(self):
        f=self.fixture(); f.fault='staged'; seen=[]
        with patch('ucc.jobs.fbx_intake.BlenderJobRunner.run',side_effect=f.run_worker):
            with self.assertRaises(Exception):f.invoke(observer=lambda *triple:seen.append(triple))
        self.assertEqual(seen,[])

    def test_each_existing_orchestrator_calls_guard_before_every_owned_child(self):
        from test_neutral_master import NeutralCoordinatorTests
        from test_native_coordinator import NativeCoordinatorTests
        from test_native_playback import PlaybackCoordinatorTests
        for kind in ('neutral','intake','body','playback'):
            with self.subTest(orchestrator=kind):
                fixture={'neutral':NeutralCoordinatorTests,'intake':intake_tests.FbxCoordinatorTests,
                    'body':NativeCoordinatorTests,'playback':PlaybackCoordinatorTests}[kind]()
                fixture.setUp();self.addCleanup(fixture.doCleanups)
                seen=[]
                if kind=='intake':
                    with patch('ucc.jobs.fbx_intake.BlenderJobRunner.run',side_effect=fixture.run_worker):
                        fixture.invoke(source_guard=lambda:seen.append(len(seen)))
                    self.assertEqual(seen,[0,1])
                elif kind=='neutral':
                    fixture.invoke(source_guard=lambda:seen.append(fixture.runs))
                    self.assertEqual(seen,[0,1])
                elif kind=='body':
                    fixture.corrective=True
                    fixture.run_preview(source_guard=lambda:seen.append(fixture.runs))
                    self.assertEqual(seen,[0,1,2])
                else:
                    fixture.surface=True
                    from ucc.jobs.native_playback import prepare_native_playback
                    with patch('test_native_playback.prepare_native_playback',side_effect=lambda *a,**kw:
                            prepare_native_playback(*a,**kw,source_guard=lambda:seen.append(fixture.runs))):
                        fixture.prepare()
                    self.assertEqual(seen,[0,1])
