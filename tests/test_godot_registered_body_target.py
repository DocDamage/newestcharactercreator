"""Coordinator filesystem faults. Every engine/native gate explicitly stubbed."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from fixtures.godot_registered_body_logic import BodyCoordinationFixture
from ucc.core.errors import ProjectConflict,ProjectStorageError
from ucc.jobs import godot_registered_body_target as target
from ucc.jobs.runner import ProcessOutcome,WorkerFailure


class RegisteredBodyCoordinatorTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.f=BodyCoordinationFixture(Path(temporary.name).resolve());self.calls=[]
        stack=ExitStack();self.addCleanup(stack.close)
        self.admission=stack.enter_context(patch.object(target,'admit_body_inputs',return_value=self.f.inputs))
        self.runner=stack.enter_context(patch.object(target,'run_process',side_effect=self.run_child))
        self.verify=stack.enter_context(patch.object(target,'verify_body_outputs',side_effect=self.verify_outputs))

    def run_child(self,command,logdir,**kwargs):
        self.calls.append(command);engine=Path(command[command.index('--path')+1])
        if len(self.calls)==1:(engine/'character.glb.import').write_text('animation/fps=30.0\n"optimizer/enabled": false\n"compression/enabled": false')
        if len(self.calls) in (2,4):
            name='configured_import.json' if len(self.calls)==2 else 'import_configuration.json'
            phase='PRE_REIMPORT' if len(self.calls)==2 else 'POST_REIMPORT'
            (engine/name).write_text(json.dumps(dict(schema_version=1,phase=phase,animation_fps=30.,optimizer_enabled=False,
                compression_enabled=False,import_settings_sha256=sha256((engine/'character.glb.import').read_bytes()).hexdigest())))
        if len(self.calls)==4:
            for name in ('measurement.json','actual_corrected_world.f32','actual_normals_vec4.f32','imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32'):
                (engine/name).write_bytes(('NONSHIPPING_NO_ENGINE_PROOF:'+name).encode())
        return ProcessOutcome(0,'','',.001)

    def verify_outputs(self,engine,*args,**kwargs):
        return dict(status='NONSHIPPING_EVIDENCE_DOUBLE',measurement_sha256=sha256((engine/'measurement.json').read_bytes()).hexdigest(),
            output_files={name:dict(sha256=sha256((engine/name).read_bytes()).hexdigest(),bytes=(engine/name).stat().st_size)
                for name in ('actual_corrected_world.f32','actual_normals_vec4.f32','imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32')})

    def test_uv_mutation_after_verification_cannot_be_adopted_as_final_baseline(self):
        real=self.verify_outputs
        def verify(engine,*args,**kwargs):
            observed=real(engine,*args,**kwargs)
            (engine/'imported_uv.f32').write_bytes(b'NONSHIPPING_CHANGED_AFTER_VERIFICATION')
            return observed
        self.verify.side_effect=verify
        with self.assertRaises(ProjectStorageError):self.invoke()
        self.assertEqual(self.receipts(),[])

    def invoke(self,**changes):return target.verify_registered_native_body_runtime(self.f.store,**(self.f.args()|changes))

    def receipts(self):return list((self.f.store.root/'.ucc-jobs').glob('registered-body300-*/diagnostic_receipt.json'))

    def test_four_controlled_phases_and_closed_private_receipt_without_engine_launch(self):
        before=self.f.store.file.read_bytes();result=self.invoke()
        self.assertEqual(len(self.calls),4);self.assertFalse(result.engine_import_verified)
        for index in (0,2,3):
            self.assertIn('mobile',self.calls[index]);self.assertIn('vulkan',self.calls[index]);self.assertNotIn('--headless',self.calls[index])
        self.assertIn('--headless',self.calls[1]);self.assertIn('res://configure.gd',self.calls[1])
        raw=(result.directory/'diagnostic_receipt.json').read_bytes()
        self.assertEqual(sha256(raw).hexdigest(),result.receipt_sha256)
        self.assertEqual(json.loads(raw)['execution_sha256'],self.f.execution.sha256)
        self.assertEqual(self.f.store.file.read_bytes(),before)

    def test_cancel_before_first_child_leaves_no_success_receipt(self):
        event=Event()
        def progress(phase):
            if phase=='GODOT_INITIAL_IMPORT':event.set()
        with self.assertRaises(ProjectStorageError):self.invoke(cancel=event,progress=progress)
        self.assertEqual(self.calls,[]);self.assertEqual(self.receipts(),[])

    def test_command_uses_exact_normalized_selected_path_not_raw_pathlike_string(self):
        class InconsistentPath:
            def __init__(self,path):self.path=path
            def __fspath__(self):return str(self.path)
            def __str__(self):return 'UNSELECTED_PROGRAM_MUST_NEVER_LAUNCH.exe'
        selected=self.f.root/'NOT_A_GODOT_CONSOLE.exe'
        self.invoke(godot_exe=InconsistentPath(selected),godot_main_exe=InconsistentPath(self.f.root/'NOT_A_GODOT_MAIN.exe'))
        self.assertTrue(all(command[0]==str(selected) for command in self.calls))
        self.assertEqual(self.admission.call_args.kwargs['godot_exe'],selected)

    def test_failed_child_does_not_continue_or_verify(self):
        self.runner.side_effect=lambda *a,**kw:ProcessOutcome(13,'','synthetic failure',.001)
        with self.assertRaises(WorkerFailure):self.invoke()
        self.assertEqual(self.runner.call_count,1);self.verify.assert_not_called();self.assertEqual(self.receipts(),[])

    def test_existing_execution_work_identity_is_never_overwritten(self):
        work=self.f.store.root/'.ucc-jobs'/('registered-body300-'+self.f.execution.execution_id)
        work.mkdir();sentinel=work/'FOREIGN';sentinel.write_bytes(b'PRESERVE')
        with self.assertRaises(ProjectStorageError):self.invoke()
        self.assertEqual(sentinel.read_bytes(),b'PRESERVE');self.assertEqual(self.calls,[])

    def test_staged_program_mutation_stops_before_second_child(self):
        real=self.run_child
        def child(command,*args,**kwargs):
            result=real(command,*args,**kwargs)
            engine=Path(command[command.index('--path')+1]);(engine/'validate.gd').write_bytes(b'NONSHIPPING_CHANGED')
            return result
        self.runner.side_effect=child
        with self.assertRaises(ProjectStorageError):self.invoke()
        self.assertEqual(len(self.calls),1);self.assertEqual(self.receipts(),[])

    def test_foreign_work_directory_replacement_is_preserved_and_rejected(self):
        def progress(phase):
            if phase=='STAGE_REGISTERED_BODY300':
                [work]=list((self.f.store.root/'.ucc-jobs').glob('registered-body300-*'))
                engine=work/'engine';engine.rename(work/'owned-engine-kept');engine.mkdir()
                self.foreign=engine
        with self.assertRaises(ProjectStorageError):self.invoke(progress=progress)
        self.assertEqual(list(self.foreign.iterdir()),[]);self.assertEqual(self.calls,[])

    def test_current_source_revocation_after_final_child_rejects(self):
        real=self.run_child;revoked=[False]
        def guard():
            if revoked[0]:raise ProjectConflict('NONSHIPPING_WAL_POLICY_REVOCATION_DOUBLE')
        self.admission.return_value=replace(self.f.inputs,guard=guard)
        def child(*args,**kwargs):
            value=real(*args,**kwargs)
            if len(self.calls)==4:revoked[0]=True
            return value
        self.runner.side_effect=child
        with self.assertRaises(ProjectConflict):self.invoke()
        self.assertEqual(self.receipts(),[])

    def test_same_byte_receipt_replacement_after_commit_rejects_and_preserves_history(self):
        real=target.rename_new
        def rename(source,destination):
            real(source,destination);replacement=self.f.root/'same-byte-receipt.json'
            replacement.write_bytes(destination.read_bytes());replacement.replace(destination)
        with patch.object(target,'rename_new',side_effect=rename):
            with self.assertRaises(ProjectStorageError) as failure:self.invoke()
        self.assertEqual(len(self.receipts()),1)
        self.assertTrue(any('commit completed' in note for note in failure.exception.__notes__))
