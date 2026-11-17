"""Execution admission identity faults; retained/native authority explicitly doubled."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID
from threading import Event
from fixtures.godot_registered_retention_logic import RetentionFixture,digest
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection,RuntimeCodeSelection
from ucc.jobs import godot_registered_body_inputs as inputs
from ucc.jobs.target_action_context import Budget


class InterruptedCurrentGuardTests(unittest.TestCase):
    """Metadata-only retry faults; no source, engine or native authority doubled as proof."""

    @staticmethod
    def interrupted():
        db=sqlite3.connect(':memory:')
        try:
            db.set_progress_handler(lambda:1,1)
            try:db.execute('SELECT 1').fetchone()
            except sqlite3.OperationalError as error:
                assert error.sqlite_errorcode==sqlite3.SQLITE_INTERRUPT
                raise ProjectStorageError('Nonshipping interrupted metadata fault') from error
        finally:db.close()

    def test_one_interrupt_restarts_the_complete_guard(self):
        calls=[]
        def check():
            calls.append(len(calls))
            if len(calls)==1:self.interrupted()
        inputs._current_guard(check,Budget(None,10))
        self.assertEqual(len(calls),2)

    def test_retry_propagates_fresh_policy_rejection(self):
        calls=[]
        def check():
            calls.append(len(calls))
            if len(calls)==1:self.interrupted()
            raise ValidationError('Nonshipping current policy was revoked')
        with self.assertRaisesRegex(ValidationError,'policy was revoked'):
            inputs._current_guard(check,Budget(None,10))
        self.assertEqual(len(calls),2)

    def test_two_interruptions_stop_at_two_attempts(self):
        calls=[]
        def check():
            calls.append(len(calls));self.interrupted()
        with self.assertRaises(ProjectStorageError) as failure:
            inputs._current_guard(check,Budget(None,10))
        self.assertEqual(len(calls),2)
        self.assertEqual(failure.exception.__cause__.sqlite_errorcode,sqlite3.SQLITE_INTERRUPT)

    def test_cancellation_stops_before_retry_and_after_success(self):
        for interrupted in (True,False):
            with self.subTest(interrupted=interrupted):
                event=Event();calls=[]
                def check():
                    calls.append(1);event.set()
                    if interrupted:self.interrupted()
                with self.assertRaisesRegex(ProjectStorageError,'cancelled by caller'):
                    inputs._current_guard(check,Budget(event,10))
                self.assertEqual(len(calls),1)

    def test_other_errors_and_nested_interrupt_causes_never_retry(self):
        failures=[ValidationError('Nonshipping schema rejection')]
        for code in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED,sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_ERROR):
            cause=sqlite3.OperationalError('Nonshipping database fault');cause.sqlite_errorcode=code
            error=ProjectStorageError('Nonshipping source guard fault');error.__cause__=cause
            failures.append(error)
        cause=sqlite3.OperationalError('Nonshipping nested interrupt');cause.sqlite_errorcode=sqlite3.SQLITE_INTERRUPT
        middle=ProjectStorageError('Nonshipping middle');middle.__cause__=cause
        outer=ProjectStorageError('Nonshipping outer');outer.__cause__=middle;failures.append(outer)
        for error in failures:
            with self.subTest(error=str(error)):
                calls=[]
                def check():calls.append(1);raise error
                with self.assertRaises(type(error)):inputs._current_guard(check,Budget(None,10))
                self.assertEqual(len(calls),1)


class RegisteredBodyAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=RetentionFixture(Path(temp.name).resolve())
        self.recipe=json.loads((self.f.work/'native_recipe.json').read_bytes())
        self.receipt=json.loads(self.f.preparation.production_receipt.read_bytes())
        for name,source in (('runtime_request.json',self.f.work/'runtime_request.json'),
                            ('source_receipt.json',self.f.preparation.production_receipt)):
            (self.f.fresh/name).write_bytes(source.read_bytes())
        for name in ('native_positions.bin','native_normals.bin'):(self.f.fresh/name).write_bytes(b'NONSHIPPING!')
        stage=json.loads((self.f.stage/'native_stage.json').read_bytes())
        for name in ('native_positions.bin','native_normals.bin'):
            stage['files'][name]=dict(sha256=digest(self.f.fresh/name),bytes=12)
        (self.f.stage/'native_stage.json').write_bytes(canonical_bytes(stage))
        self.receipt['native_stage_sha256']=digest(self.f.stage/'native_stage.json')
        self.exe=self.f.root/'NOT_A_REAL_CONSOLE.exe';self.main=self.f.root/'NOT_A_REAL_MAIN.exe'
        self.exe.write_bytes(b'NONSHIPPING_NOT_EXECUTABLE_CONSOLE');self.main.write_bytes(b'NONSHIPPING_NOT_EXECUTABLE_MAIN')
        self.execution=RegisteredRuntimeExecutionSelection(str(UUID(int=9000)),'a'*64,
            tuple(RuntimeCodeSelection(name,value,self.recipe['runtime_code_lengths'][name]) for name,value in self.recipe['implementation'].items()),
            self.recipe['runtime_code_provenance_sha256'],digest(self.exe),digest(self.main),'Synthetic execution admission only',True)
        stack=ExitStack();self.addCleanup(stack.close)
        self.loader=stack.enter_context(patch.object(inputs,'load_registered_native_inputs',return_value=SimpleNamespace(directory=self.f.fresh)))
        manifest=SimpleNamespace(source_receipt_sha256=self.f.receipt_sha,stage_job_id=self.f.stage.name,reopen_job_id=self.f.fresh.name)
        stack.enter_context(patch.object(inputs,'read_bytes',return_value=(b'NONSHIPPING_MANIFEST_DOUBLE','a'*64)))
        stack.enter_context(patch.object(inputs.RegisteredRuntimeManifest,'from_bytes',return_value=manifest))
        stack.enter_context(patch.object(inputs,'seal',return_value=('NONSHIPPING_SEAL',{})))
        stack.enter_context(patch.object(inputs,'check_seal_identities'))
        stack.enter_context(patch.object(inputs,'current_inputs',return_value=self.f.context))
        stack.enter_context(patch.object(inputs,'validate_graph',return_value=(self.recipe,self.receipt,None,{})))
        stack.enter_context(patch.object(inputs,'watch_preparation',return_value=lambda:None))
        stack.enter_context(patch.object(inputs,'REFERENCE_BYTES',12))

    def admit(self,**changes):
        args=dict(selection=self.f.selection,retention_id=str(UUID(int=8000)),expected_manifest_sha256='a'*64,
            database_path=self.f.root/'unused',permissions=self.f.permissions,preparation=self.f.preparation,
            expected_production_receipt_sha256=self.f.receipt_sha,execution=self.execution,
            godot_exe=self.exe,godot_main_exe=self.main,budget=Budget(None,60))
        return inputs.admit_body_inputs(self.f.store,**(args|changes))

    def test_selected_program_identity_and_matching_actual_locator_are_consumed(self):
        admitted=self.admit();admitted.guard()
        self.assertEqual(set(admitted.references),{'native_positions.bin','native_normals.bin'})
        self.assertEqual(admitted.records['runtime_kernel.gd']['sha256'],self.recipe['implementation']['runtime_kernel.gd'])

    def test_untyped_preparation_rejects_before_any_retained_loader(self):
        for value in (None,{'directory':str(self.f.fresh)}):
            with self.subTest(value=value),self.assertRaises(ValidationError):self.admit(preparation=value)
        self.loader.assert_not_called()

    def test_provenance_code_candidate_receipt_and_historical_worker_drift_reject(self):
        for changes in (dict(execution=replace(self.execution,provenance_sha256='0'*64)),
                dict(execution=replace(self.execution,retention_manifest_sha256='0'*64)),
                dict(execution=replace(self.execution,execution_id=self.f.stage.name)),
                dict(execution=replace(self.execution,code=(replace(self.execution.code[0],bytes=1),)+self.execution.code[1:])),
                dict(expected_production_receipt_sha256='0'*64)):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.admit(**changes)

    def test_same_byte_selected_engine_replacement_rejects_guard(self):
        admitted=self.admit();replacement=self.f.root/'same-byte.exe'
        replacement.write_bytes(self.exe.read_bytes());replacement.replace(self.exe)
        with self.assertRaises(ProjectStorageError):admitted.guard()

    def test_engine_change_after_selected_digest_is_never_adopted_as_new_baseline(self):
        real=inputs.hash_file;changed=[False]
        def hashed(path,*args):
            result=real(path,*args)
            if path==self.exe and not changed[0]:
                changed[0]=True;self.exe.write_bytes(b'NONSHIPPING_CHANGED_EXECUTABLE')
            return result
        with patch.object(inputs,'hash_file',side_effect=hashed):
            with self.assertRaises(ProjectStorageError):self.admit()
