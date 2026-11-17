"""Real loader, source hashes and SQLite/WAL guards; native proof is stubbed."""
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fixtures.target_action_logic import TargetFixture
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.jobs import godot_registered_runtime_admission as admission
from ucc.jobs.master_preview import _digest
from ucc.jobs.target_action_context import Budget
from ucc.library.provenance import AssetPolicyError


class RegisteredRuntimeCurrentInputsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=TargetFixture(Path(temp.name).resolve());self.directory,self.binding=self.f.payload()
        self.library=self.f.root/"library.json";self.library.write_text('{"rights":{"no_ai":true}}')
        self.selection=RegisteredInputSelection(self.f.project.project_id,self.f.project.revision,
            _digest(self.f.store.file),self.f.master_sha,self.f.clip_id,self.binding.sha256,
            self.binding.source.source_binding_sha256,self.binding.source.catalog_record_sha256)
        policy=replace(self.f.policy,can_use_non_unreal=True)
        self.permissions=tuple(EngineInputPermission(name,digest,policy,False) for name,digest in (
            ("master",self.f.master_sha),("expression_library",_digest(self.library)),
            ("motion:original-diagnostic",self.f.source_sha)))
        self.budget=Budget(None,60);self.host={"nonshipping_host":"original"}
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch("ucc.jobs.target_action_evidence.validate_retained_target_action",return_value=object()))
        self.stack.enter_context(patch.object(admission,"_registered_sources",side_effect=lambda *a:{"master":self.f.master,"expression_library":self.library}))
        self.stack.enter_context(patch.object(admission,"host_code_snapshot",side_effect=lambda *a:dict(self.host)))
        self.stack.enter_context(patch("ucc.jobs.target_action_storage.host_code_snapshot",return_value={"nonshipping_loader":"same"}))
        self.stack.enter_context(patch("ucc.jobs.runner.BlenderJobRunner.run",side_effect=AssertionError("Current-input reload started a worker")))

    def admit(self,**changes):
        args=dict(selection=self.selection,database_path=self.f.database,permissions=self.permissions,budget=self.budget)
        return admission.current_inputs(self.f.store,**(args|changes))

    def test_current_saved_loader_preserves_ids_scopes_progress_and_creates_no_jobs(self):
        events=[];before=set((self.f.store.root/".ucc-jobs").glob("*"))
        current=self.admit(progress=events.append);current.guard()
        self.assertEqual(current.project,self.f.project);self.assertEqual(current.binding,self.binding)
        self.assertEqual(current.project.animations,(self.f.clip_id,))
        self.assertEqual(current.source_hashes,{p.asset_id:p.source_sha256 for p in self.permissions})
        self.assertIn("LOAD_TARGET_ACTION_COMPLETE",events)
        self.assertTrue(all(value.startswith("LOAD_TARGET_ACTION_") for value in events))
        self.assertEqual(set((self.f.store.root/".ucc-jobs").glob("*")),before)

    def test_library_and_motion_noai_cannot_be_removed_by_explicit_selection(self):
        for role in ("expression_library","motion:original-diagnostic"):
            permissions=tuple(replace(p,policy=replace(p.policy,no_ai=False)) if p.asset_id==role else p for p in self.permissions)
            with self.subTest(role=role),self.assertRaises(ValidationError):self.admit(permissions=permissions)

    def test_permission_content_must_equal_single_captured_source_hashes(self):
        changed=tuple(replace(p,source_sha256="0"*64) if p.asset_id=="expression_library" else p for p in self.permissions)
        with self.assertRaises(ValidationError):self.admit(permissions=changed)

    def test_loaded_target_hash_conflict_is_never_overwritten_by_new_source_digest(self):
        real=admission.load_target_action
        def loaded(*args,**kwargs):
            prepared=real(*args,**kwargs)
            return replace(prepared,watched_inputs=prepared.watched_inputs+((self.library,"0"*64),))
        with patch.object(admission,"load_target_action",side_effect=loaded):
            with self.assertRaises(ProjectStorageError):self.admit()

    def test_policy_revocation_committed_only_in_wal_is_rechecked(self):
        connection=sqlite3.connect(self.f.database);self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        current=self.admit();before=_digest(self.f.database)
        row=connection.execute("SELECT license_json FROM asset_sources WHERE asset_id=?",(self.f.reference.asset_id,)).fetchone()
        policy=json.loads(row[0]);policy["local_preview_allowed"]=False
        connection.execute("UPDATE asset_sources SET license_json=? WHERE asset_id=?",(json.dumps(policy),self.f.reference.asset_id));connection.commit()
        self.assertEqual(_digest(self.f.database),before)
        with self.assertRaises((ProjectConflict,ProjectStorageError,ValidationError,AssetPolicyError)):current.guard()

    def test_host_source_and_proof_replacement_rejects_current_guard(self):
        current=self.admit();self.host["nonshipping_host"]="changed"
        with self.assertRaises((ProjectStorageError,ProjectConflict)):current.guard()
        self.host["nonshipping_host"]="original";current=self.admit()
        path=self.directory/"body_first/result.json";replacement=self.f.root/"same-byte.json"
        replacement.write_bytes(path.read_bytes());replacement.replace(path)
        with self.assertRaises((ProjectStorageError,ProjectConflict)):current.guard()

    def test_original_source_registration_namespace_change_rejects_guard(self):
        current=self.admit();(self.f.store.root/"animations/foreign.json").write_bytes(b"{}")
        with self.assertRaises((ProjectStorageError,ProjectConflict)):current.guard()
