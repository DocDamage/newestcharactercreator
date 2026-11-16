"""Independent binary corruption and real filesystem transaction unit guards."""
from contextlib import ExitStack
from pathlib import Path
import struct,tempfile,time
from threading import Event
import unittest
from unittest.mock import patch
from fixtures.godot_native_target_logic import NativeTargetFixture
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.jobs.godot_native_target import verify_sampled_native_runtime
from ucc.jobs.godot_native_target_evidence import compare_outputs
from ucc.jobs.runner import ProcessOutcome,WorkerFailure


class NativeTargetTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.f=NativeTargetFixture(Path(temporary.name).resolve());self.calls=[]

    def doubles(self,callback=None):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('ucc.jobs.godot_native_target.project_sources',return_value={'master':self.f.master}))
        stack.enter_context(patch('ucc.jobs.godot_native_target.validate_runtime_files'))
        stack.enter_context(patch('ucc.jobs.godot_native_target.validate_sample_report',side_effect=lambda raw,**kwargs:raw))
        stack.enter_context(patch('ucc.jobs.godot_native_target.REFERENCE_BYTES',17))
        stack.enter_context(patch('ucc.jobs.godot_native_target.verify_native_target_evidence',return_value={'UNIT_ONLY_NOT_ENGINE_EVIDENCE':True}))
        def process(command,workdir,**kwargs):
            self.calls.append(workdir.name);engine=Path(command[command.index('--path')+1]);workdir.mkdir()
            (workdir/'stdout.log').write_text('UNIT_PROCESS_DOUBLE_NOT_ENGINE_OUTPUT')
            if workdir.name=='configure-import':(engine/'character.glb.import').write_text('animation/fps=30.0\n"optimizer/enabled": false\n"compression/enabled": false\n')
            if callback:
                value=callback(workdir.name,engine)
                if value is not None:return value
            return ProcessOutcome(0,'UNIT_ONLY','',.001)
        stack.enter_context(patch('ucc.jobs.godot_native_target.run_process',side_effect=process))

    def run_target(self,**kwargs):return verify_sampled_native_runtime(self.f.store,**self.f.target_kwargs(),**kwargs)

    def preserved(self):
        self.assertEqual(self.f.store.file.read_bytes(),self.f.original_metadata)
        self.assertEqual(self.f.master.read_bytes(),self.f.original_master)
        self.assertTrue((self.f.bundle/'request.json').is_file())
        self.assertFalse(list((self.f.store.root/'.ucc-candidates/godot-native-verification').glob('*')))

    def test_success_keeps_false_readiness_and_uses_all_four_target_phases(self):
        self.doubles();result=self.run_target()
        self.assertFalse(result.engine_import_verified)
        self.assertTrue((result.directory/'independent_verification.json').is_file())
        self.assertEqual(self.calls,['initial-import','configure-import','configured-import','actual-verification'])
        self.assertEqual(self.f.store.file.read_bytes(),self.f.original_metadata)

    def test_default_adapter_uses_trusted_resource_locator(self):
        self.doubles();kwargs=self.f.target_kwargs();kwargs.pop('adapter_directory')
        with patch('ucc.jobs.godot_native_target.bundled_native_adapter_path',return_value=self.f.adapter) as resolve:
            result=verify_sampled_native_runtime(self.f.store,**kwargs)
        resolve.assert_called_once_with();self.assertFalse(result.engine_import_verified)

    def test_midflight_original_mutation_rejects_before_next_process(self):
        def mutate(phase,engine):
            if phase=='initial-import':self.f.motion.write_bytes(b'UNIT_SOURCE_CHANGED')
        self.doubles(mutate)
        with self.assertRaises(ProjectStorageError):self.run_target()
        self.assertEqual(len(self.calls),1);self.preserved()

    def test_process_failure_or_total_deadline_keeps_prior_source_bundle(self):
        self.doubles(lambda phase,engine:ProcessOutcome(13,'','UNIT_FAILURE',.001))
        with self.assertRaises(WorkerFailure):self.run_target()
        self.preserved()

    def test_deadline_is_total_not_per_process(self):
        def delay(phase,engine):time.sleep(.08)
        self.doubles(delay)
        with self.assertRaises(WorkerFailure):self.run_target(timeout_s=.06)
        self.assertLessEqual(len(self.calls),1);self.preserved()

    def test_precancel_launches_no_target_process(self):
        self.doubles();cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.run_target(cancel=cancel)
        self.assertEqual(self.calls,[]);self.preserved()

    def test_final_journal_failure_rolls_target_back_into_private_job(self):
        self.doubles();real_replace=__import__('os').replace
        def replace_status(source,destination):
            if b'PRIVATE_NATIVE_TARGET_VERIFIED' in Path(source).read_bytes():raise OSError('UNIT_FINAL_JOURNAL_FAILURE')
            return real_replace(source,destination)
        with patch('ucc.jobs.godot_native_target.os.replace',side_effect=replace_status):
            with self.assertRaisesRegex(OSError,'UNIT_FINAL_JOURNAL_FAILURE'):self.run_target()
        self.preserved()
        self.assertTrue(list((self.f.store.root/'.ucc-jobs').glob('native-target-*/engine/independent_verification.json')))

    def test_independent_readback_rejects_position_normal_and_homogeneous_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for name,values in [('actual_corrected_world.f32',(0.,0.,0.,1.)),('expected_vec4.f32',(0.,0.,0.,1.)),
                ('actual_normals_vec4.f32',(0.,0.,1.,0.)),('expected_normals_vec4.f32',(0.,0.,1.,0.))]:
                (root/name).write_bytes(struct.pack('<4f',*values))
            self.assertEqual(compare_outputs(root,samples=1,vertices=1,check=lambda:None)['maximum_position_error_m'],0.)
            for name,values in [('actual_corrected_world.f32',(.001,0.,0.,1.)),('actual_corrected_world.f32',(0.,0.,0.,0.)),
                ('actual_normals_vec4.f32',(.0019,0.,(1-.0019**2)**.5,0.))]:
                original=(root/name).read_bytes();(root/name).write_bytes(struct.pack('<4f',*values))
                with self.assertRaises(ValidationError):compare_outputs(root,samples=1,vertices=1,check=lambda:None)
                (root/name).write_bytes(original)


if __name__=='__main__':unittest.main()
