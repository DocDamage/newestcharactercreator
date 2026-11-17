"""Saved loader boundary/seal/WAL faults; native/authority doubles explicit."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from fixtures.godot_saved_preview_logic import SavedPreviewFixture
from fixtures.godot_registered_retention_logic import OBSERVED
from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.export.godot_saved_preview import SelectedProofFile
from ucc.jobs import godot_saved_preview as saved
from ucc.library.provenance import AssetPolicyError


class SavedPreviewLoaderTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.f=SavedPreviewFixture(Path(temp.name).resolve())
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(saved,'current_inputs',side_effect=self.f.current))
        self.body=self.stack.enter_context(patch.object(saved,'admit_body_proof',side_effect=self.f.body))
        self.stack.enter_context(patch.object(saved,'admit_draw_proof',side_effect=self.f.draw))
        self.stack.enter_context(patch('ucc.jobs.godot_registered_runtime_admission._native_timeline',return_value=([],{})))
        self.stack.enter_context(patch('ucc.jobs.godot_registered_runtime_admission.validate_reopen_report'))
        self.stack.enter_context(patch('ucc.jobs.godot_registered_runtime_admission.validate_runtime_files',return_value=dict(OBSERVED)))
        self.stack.enter_context(patch('subprocess.Popen',side_effect=AssertionError('Read-only preview launched an app')))
        self.stack.enter_context(patch('ucc.jobs.godot_registered_body_inputs.body_adapter_paths',side_effect=AssertionError('Frozen viewer looked up C adapters')))
        self.stack.enter_context(patch('ucc.jobs.godot_registered_body_draw._adapter_paths',side_effect=AssertionError('Frozen viewer looked up D adapters')))
    def load(self,**changes):return saved.load_saved_godot_preview(self.f.store,**(self.f.args()|changes))
    def test_external_relocated_retention_and_c_d_proofs_return_captured_pngs_with_no_execution(self):
        value=self.load();self.assertEqual([x.frame for x in value.frames],[1,150,300]);self.assertEqual(value.frames[0].png_bytes,self.f.png_raw)
        self.assertFalse(value.engine_import_verified);self.assertFalse(value.visual_quality_approved)
        self.assertIn(self.f.database,value.watch_paths);self.assertIn(self.f.database.parent,value.watch_paths)
        self.assertEqual(dict(value.watched_identities)[self.f.database.with_name(self.f.database.name+'-wal')],(0,0,0,0))
        self.assertEqual(self.f.store.load(),self.f.project)
    def test_frozen_view_does_not_resolve_historical_executable_or_adapter(self):
        with patch.object(sys,'frozen',True,create=True):value=self.load();value.guard()
        self.assertEqual(len(value.frames),3)
    def test_guard_has_fresh_budget_after_original_load_budget_expires(self):
        value=self.load();self.f.seen_reads.budget.deadline=-1
        value.guard(timeout_s=60);self.assertGreaterEqual(self.f.context_calls,2)
    def test_wal_policy_revocation_rechecks_current_authority_and_never_checkpoints_global(self):
        writer=sqlite3.connect(self.f.database);self.addCleanup(writer.close);writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
        value=self.load();before=self.f.database.read_bytes()
        writer.execute('UPDATE synthetic_policy SET allowed=0');writer.commit();self.assertEqual(self.f.database.read_bytes(),before)
        with self.assertRaises(AssetPolicyError):value.guard()
    def test_mismatched_current_binding_rejects_before_body_reader(self):
        with self.assertRaises(ValidationError):self.load(selection=replace(self.f.selection,binding_sha256='1'*64))
        self.body.assert_not_called()
    def test_changed_noai_permission_not_inferred_from_historical_view(self):
        first=self.f.permissions[0];changed=replace(first,policy=replace(first.policy,no_ai=False,ai_input_allowed=True))
        with self.assertRaises((ValidationError,AssetPolicyError)):self.load(permissions=(changed,*self.f.permissions[1:]))
        self.body.assert_not_called()
    def test_unchecked_truthy_view_confirmation_rejects_without_authority(self):
        for value in (False,1,'true'):
            with self.subTest(value=value),self.assertRaises(ValidationError):self.load(local_view_confirmed=value)
        self.assertEqual(self.f.context_calls,0)
    def test_pre_cancel_and_fresh_guard_cancel_fail_closed(self):
        event=Event();event.set()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled by caller'):self.load(cancel=event)
        value=self.load()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled by caller'):value.guard(cancel=event)
    def test_late_source_change_during_captured_png_load_prevents_return(self):
        original=self.f.draw
        def mutate(*args):
            value=original(*args);self.f.revoked=True;return value
        with patch.object(saved,'admit_draw_proof',side_effect=mutate),self.assertRaises(ProjectConflict):self.load()
    def test_modified_png_path_rejects_guard_captured_bytes_unchanged(self):
        value=self.load();self.f.image.write_bytes(b'changed')
        self.assertEqual(value.frames[0].png_bytes,self.f.png_raw)
        with self.assertRaises(ProjectStorageError):value.guard()
    def test_same_byte_retained_file_replacement_rejects_guard(self):
        value=self.load();path=self.f.retained/'runtime_code_provenance.json';other=self.f.root/'replacement.json';other.write_bytes(path.read_bytes());other.replace(path)
        with self.assertRaises(ProjectStorageError):value.guard()
    def test_catalog_same_bytes_replacement_rejects_guard(self):
        value=self.load();other=self.f.root/'replacement.sqlite';other.write_bytes(self.f.database.read_bytes());other.replace(self.f.database)
        with self.assertRaisesRegex(ProjectStorageError,'catalog identity'):value.guard()
    def test_three_choices_require_absolute_paths_and_sha(self):
        with self.assertRaises(ValidationError):SelectedProofFile(Path('relative.json'),'a'*64)
        with self.assertRaises(ValidationError):SelectedProofFile(self.f.image,'not-a-sha')

    def test_committed_WAL_revocation_during_final_proof_hash_cannot_be_adopted(self):
        writer=sqlite3.connect(self.f.database);self.addCleanup(writer.close);writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
        from ucc.jobs.godot_saved_preview_files import ProofReads
        original=ProofReads.check;calls=0;main_before=self.f.database.read_bytes()
        def revoke_after_final_hash(reads,*args,**kwargs):
            nonlocal calls
            original(reads,*args,**kwargs);calls+=1
            if calls==2:
                writer.execute('UPDATE synthetic_policy SET allowed=0');writer.commit()
        with patch.object(ProofReads,'check',revoke_after_final_hash),self.assertRaises(AssetPolicyError):self.load()
        self.assertEqual(self.f.database.read_bytes(),main_before)
    def test_WAL_commit_after_final_logical_rights_check_rejected_by_byte_fence(self):
        writer=sqlite3.connect(self.f.database);self.addCleanup(writer.close);writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
        original=saved.final_catalog_guard;main_before=self.f.database.read_bytes()
        def final_fence(database,budget,logical):
            def revoke_after_logical():
                logical();writer.execute('UPDATE synthetic_policy SET allowed=0');writer.commit()
            return original(database,budget,revoke_after_logical)
        with patch.object(saved,'final_catalog_guard',side_effect=final_fence),self.assertRaisesRegex(ProjectStorageError,'semantic bytes changed'):self.load()
        self.assertEqual(self.f.database.read_bytes(),main_before)

    def test_allowed_empty_WAL_removal_drops_missing_direct_watch_but_retains_stamp(self):
        wal=self.f.database.with_name(self.f.database.name+'-wal');wal.write_bytes(b'')
        original=saved.final_catalog_guard
        def with_readonly_cleanup(database,budget,logical):
            def close_last_reader():
                logical();wal.unlink()
            return original(database,budget,close_last_reader)
        with patch.object(saved,'final_catalog_guard',side_effect=with_readonly_cleanup):value=self.load()
        self.assertNotIn(wal,value.watch_paths)
        self.assertEqual(dict(value.watched_identities)[wal],(0,0,0,0))
        self.assertIn(self.f.database.parent,value.watch_paths)
        self.assertTrue(all(path.exists() for path in value.watch_paths))
