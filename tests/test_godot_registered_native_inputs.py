"""Synthetic filesystem/catalog faults; native proof and recipe gates are stubbed.

Real SQLite source review, normal saved loader/inventory and host file guards run.
These fixture bytes are never native source or engine acceptance.
"""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fixtures.target_action_logic import TargetFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.godot_runtime_contract import CODE_FILES, CAPABILITY
from ucc.jobs.master_preview import _digest
from ucc.jobs.godot_registered_native_inputs import admit_registered_native_production
from ucc.library.provenance import AssetPolicyError

MODULE = "ucc.jobs.godot_registered_native_inputs."


class RegisteredNativeInputsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.f=TargetFixture(Path(temp.name).resolve())
        self.directory,self.binding=self.f.payload()
        self.runtime=self.f.root/"private-code"; self.runtime.mkdir()
        for name in CODE_FILES:(self.runtime/name).write_text("# SYNTHETIC_NOT_EXECUTABLE_RUNTIME:"+name)
        self.provenance=self.f.root/"provenance.json";self.provenance.write_text('{"test_only":true}')
        self.library=self.f.root/"library.json";self.library.write_text('{"rights":{"no_ai":true}}')
        self.runner=SimpleNamespace(jobs_root=self.f.store.root/".ucc-jobs",
            worker_script=self.f.script,blender_exe=self.f.executable)
        self.cancel=Event(); self.host={"test_only_host":"unchanged"}
        policy=replace(self.f.policy,can_use_non_unreal=True)
        self.permissions=tuple(EngineInputPermission(name,digest,policy,False) for name,digest in (
            ("master",self.f.master_sha),("expression_library",_digest(self.library)),
            ("motion:original-diagnostic",self.f.source_sha)))
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        # The genuine loader still seals files/catalog and current context; only
        # native geometry/cache reader is an explicit nonshipping test double.
        self.stack.enter_context(patch("ucc.jobs.target_action_evidence.validate_retained_target_action",return_value=object()))
        self.stack.enter_context(patch(MODULE+"_registered_sources",side_effect=lambda *a:{"master":self.f.master,"expression_library":self.library}))
        self.builder=self.stack.enter_context(patch(MODULE+"build_registered_native_recipe",side_effect=lambda project,*a,**kw:{"project_snapshot":project.to_dict()}))
        self.stack.enter_context(patch(MODULE+"worker_dependency_files",return_value=set()))
        self.stack.enter_context(patch(MODULE+"host_code_snapshot",side_effect=lambda *a:dict(self.host)))
        self.stack.enter_context(patch("ucc.jobs.target_action_storage.host_code_snapshot",return_value={"test_loader_host":"unchanged"}))

    def admit(self,**changes):
        kwargs=dict(binding_sha256=self.binding.sha256,**self.f.load_args(),runtime_directory=self.runtime,
            runtime_code_provenance=self.provenance,motion_asset_id="motion:original-diagnostic",
            permissions=self.permissions,capability=CAPABILITY,cancel=self.cancel,
            check=lambda:None,remaining=lambda:120.)
        return admit_registered_native_production(self.f.store,self.runner,**(kwargs|changes))

    def test_normal_saved_loader_and_fixed_roles_preserve_current_ids_and_no_jobs(self):
        before=set(self.runner.jobs_root.glob("*")) if self.runner.jobs_root.exists() else set()
        selected=self.admit()
        self.assertEqual(selected["binding"],self.binding)
        self.assertEqual(selected["project"].animations,self.f.project.animations)
        self.assertEqual(selected["evidence"]["native_review"],self.directory/"body_first/review_motion.blend")
        self.assertEqual(selected["evidence"]["source_snapshot"],self.directory/"source_snapshot.json")
        self.assertEqual(set(selected["implementation"]),CODE_FILES)
        self.assertEqual(selected["bindings"]["motion:original-diagnostic"],self.f.source_sha)
        self.assertEqual(selected["prepared_target"].binding_sha256,self.binding.sha256)
        selected["unchanged"]()
        after=set(self.runner.jobs_root.glob("*")) if self.runner.jobs_root.exists() else set()
        self.assertEqual(before,after)
        self.assertEqual(self.f.store.load(),self.f.project)

    def test_nested_loader_progress_never_claims_unqualified_parent_completion(self):
        events=[]
        self.admit(progress=events.append)
        self.assertIn("LOAD_TARGET_ACTION_RETAINED_VALIDATION",events)
        self.assertIn("LOAD_TARGET_ACTION_COMPLETE",events)
        self.assertTrue(all(event.startswith("LOAD_TARGET_ACTION_") for event in events))
        self.assertNotIn("COMPLETE",events)

    def test_code_provenance_library_proof_and_namespace_drift_reject(self):
        selected=self.admit()
        paths=(self.runtime/"smooth.glsl",self.provenance,self.library,
               self.directory/"body_first/result.json",self.f.source)
        for path in paths:
            stamp=path.stat();old=path.read_bytes();path.write_bytes(old+b" ")
            with self.subTest(path=path),self.assertRaises((ProjectConflict,ProjectStorageError,ValidationError,AssetPolicyError)):
                selected["unchanged"]()
            path.write_bytes(old)
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        extra=self.runtime/"unlisted.gd";extra.write_text("# NOT_EXECUTED")
        with self.assertRaises((ValidationError,ProjectStorageError)):selected["unchanged"]()
        extra.unlink()
        selected["unchanged"]()

    def test_same_byte_replacement_changes_identity_and_host_drift_reject(self):
        selected=self.admit();path=self.runtime/"smooth.glsl"
        replacement=path.with_suffix(".replacement");replacement.write_bytes(path.read_bytes());replacement.replace(path)
        with self.assertRaises(ProjectStorageError):selected["unchanged"]()
        selected=self.admit();self.host["test_only_host"]="changed"
        with self.assertRaises(ProjectStorageError):selected["unchanged"]()

    def test_selected_catalog_policy_commit_held_in_wal_rejects(self):
        connection=sqlite3.connect(self.f.database);self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=WAL")
        selected=self.admit();before=_digest(self.f.database)
        row=connection.execute("SELECT license_json FROM asset_sources WHERE asset_id=?",(self.f.reference.asset_id,)).fetchone()
        policy=json.loads(row[0]);policy["local_preview_allowed"]=False
        connection.execute("UPDATE asset_sources SET license_json=? WHERE asset_id=?",(json.dumps(policy),self.f.reference.asset_id));connection.commit()
        self.assertEqual(_digest(self.f.database),before)
        with self.assertRaises((ValidationError,ProjectConflict,ProjectStorageError,AssetPolicyError)):
            selected["unchanged"]()

    def test_cancel_or_wrong_selected_binding_rejects_before_source_jobs(self):
        self.cancel.set()
        with self.assertRaises((ProjectStorageError,ValidationError)):self.admit()
        self.cancel.clear()
        with self.assertRaises((ProjectStorageError,ValidationError)):self.admit(binding_sha256="0"*64)
        self.assertFalse(self.builder.called)

    def test_overflowed_provenance_float_is_structured_error_before_recipe_or_child(self):
        self.provenance.write_text('{"overflow":1e999}')
        with self.assertRaises(ValidationError):self.admit()
        self.assertFalse(self.builder.called)

    def test_malformed_provenance_and_extra_code_reject_admission(self):
        self.provenance.write_text('{"duplicate":1,"duplicate":2}')
        with self.assertRaises(ValidationError):self.admit()
        self.provenance.write_text('{"identity_only":true}')
        (self.runtime/"geometry.bin").write_bytes(b"SYNTHETIC_NOT_GEOMETRY")
        with self.assertRaises((ValidationError,ProjectStorageError)):self.admit()

    def test_worker_namespace_and_frozen_source_guards_reject_late_insertions(self):
        selected=self.admit();extra=self.f.script.parent/"unexpected.py";extra.write_text("# NONSHIPPING")
        with self.assertRaises(ProjectStorageError):selected["unchanged"]()
        extra.unlink()
        # Added source-side records are outside .ucc-jobs and must stay protected.
        selected=self.admit();extra=self.f.store.root/"animations"/"foreign.json";extra.write_text("{}")
        with self.assertRaises((ProjectStorageError,ProjectConflict)):selected["unchanged"]()

    def test_explicit_motion_permission_cannot_remove_stored_source_noai(self):
        changed=tuple(replace(p,policy=replace(p.policy,no_ai=False))
            if p.asset_id=="motion:original-diagnostic" else p for p in self.permissions)
        with self.assertRaises(ValidationError):self.admit(permissions=changed)


class RegisteredPreparedSourceClosureTests(unittest.TestCase):
    def test_referenced_hand_checks_exact_original_intent_without_stripping_ids(self):
        from test_expression_contracts import source_project, prepared
        from ucc.core.models import PartInstance
        from ucc.core.hand_parts import hand_asset_id, build_hand_library_recipe
        from ucc.jobs.godot_registered_native_inputs import _registered_sources
        base=source_project(); recipe=build_hand_library_recipe(base,"a"*64)
        project=replace(prepared(base),parts=(PartInstance("fixture-hand",hand_asset_id("c"*64,"shorter"),"hand.L"),),
            animations=("selected#clip-0000","unselected#clip-0000"))
        library=SimpleNamespace(manifest_path=Path("fixture-library.json"))
        hand=SimpleNamespace(manifest={"recipe":recipe},sha256="c"*64,manifest_path=Path("fixture-hand.json"))
        with (patch(MODULE+"_master_file",return_value=(Path("fixture-master.blend"),"e"*64)),
              patch(MODULE+"_digest",return_value="e"*64),
              patch(MODULE+"load_expression_library",return_value=library),
              patch(MODULE+"load_hand_library",return_value=hand),
              patch(MODULE+"load_hand_receipt") as receipt,
              patch(MODULE+"admit_expression_source") as admit):
            result=_registered_sources(object(),project,None)
            self.assertEqual(project.animations,("selected#clip-0000","unselected#clip-0000"))
            self.assertEqual(result["part:"+project.parts[0].part_asset_id],hand.manifest_path)
            self.assertEqual(receipt.call_args.args[2:4],("e"*64,"shorter"))
            self.assertEqual(admit.call_args.args[2],"a"*64)
            changed=replace(project,parameters=(("height",.1),("muscle",.9),("weight",.8)))
            with self.assertRaises(ProjectConflict):_registered_sources(object(),changed,None)

    def test_referenced_no_hand_admits_current_prepared_chain_directly(self):
        from test_expression_contracts import source_project, prepared
        from ucc.jobs.godot_registered_native_inputs import _registered_sources
        project=replace(prepared(source_project()),animations=("selected#clip-0000",))
        library=SimpleNamespace(manifest_path=Path("fixture-library.json"))
        with (patch(MODULE+"_master_file",return_value=(Path("fixture-master.blend"),"e"*64)),
              patch(MODULE+"_digest",return_value="e"*64),
              patch(MODULE+"load_expression_library",return_value=library),
              patch(MODULE+"admit_expression_source") as admit):
            result=_registered_sources(object(),project,None)
            self.assertEqual(set(result),{"master","expression_library"})
            self.assertEqual(admit.call_args.args[2],"e"*64)
