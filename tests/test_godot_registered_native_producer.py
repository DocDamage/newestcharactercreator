"""Synthetic orchestration faults; actual report/hash checks, no engine proof."""
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from fixtures.godot_registered_producer_logic import SyntheticRegisteredRunner, LazyMetadataFlood
from test_godot_registered_native_recipe import recipe_args
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_registered_native_recipe import build_registered_native_recipe
from ucc.export.godot_runtime_contract import CODE_FILES, CAPABILITY
from ucc.jobs.godot_registered_native_producer import prepare_registered_native_source, _finish_owned_receipt, _outputs
from ucc.jobs.godot_candidate_inputs import identity

MODULE = "ucc.jobs.godot_registered_native_producer."


class RegisteredNativeProducerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.store = ProjectStore(self.root / "project")
        from ucc.core.models import CharacterProject
        self.store.save(CharacterProject.new("SYNTHETIC producer fixture"))
        self.before = self.store.file.read_bytes()
        args = recipe_args(); self.project = args["project"]; self.binding = args["target_action_binding"]
        self.permissions = args["permissions"]
        self.provenance = self.root / "provenance.json"; self.provenance.write_bytes(b'{"synthetic_only":true}')
        args["runtime_code_provenance_sha256"] = sha256(self.provenance.read_bytes()).hexdigest()
        recipe = build_registered_native_recipe(**args)
        self.source_dir = self.root / "retained-synthetic-binding"; self.source_dir.mkdir()
        self.paths = {}
        for name in ("master", "source", "native_review", "native_timeline", "source_snapshot", "native_mapping"):
            path = self.source_dir / name; path.write_bytes(("NOT_NATIVE:" + name).encode()); self.paths[name] = path
        runtime = self.root / "private-code"; runtime.mkdir()
        implementation = {}
        for name in CODE_FILES:
            path = runtime / name; path.write_bytes(("NOT_EXECUTED_CODE:" + name).encode()); implementation[name] = path
        self.guard = Mock()
        self.selected = dict(unchanged=self.guard, project=self.project, binding=self.binding,
            prepared_target=SimpleNamespace(directory=self.source_dir), bindings=args["source_bindings"],
            evidence_bindings=args["evidence_bindings"], project_sha=args["project_file_sha256"],
            sources={"master":self.paths["master"]}, source=self.paths["source"],
            evidence={name:self.paths[name] for name in args["evidence_bindings"]},
            implementation=implementation, recipe=recipe)
        self.runner = SyntheticRegisteredRunner(self.root)
        self.cancel = Event(); self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.runner_factory = self.stack.enter_context(patch(MODULE + "BlenderJobRunner", return_value=self.runner))
        self.admit = self.stack.enter_context(patch(MODULE + "admit_registered_native_production", return_value=self.selected))
        self.worker_reader = self.stack.enter_context(patch(MODULE + "_worker", return_value={"synthetic": True}))
        self.stack.enter_context(patch(MODULE + "read_snapshot", return_value=(object(), self.paths["source_snapshot"])))
        self.stack.enter_context(patch(MODULE + "read_native_profile", return_value=(object(), args["evidence_bindings"]["native_mapping"])))
        self.stack.enter_context(patch(MODULE + "read_native_timeline", return_value=(object(), object())))
        self.reopen_validator = self.stack.enter_context(patch(MODULE + "validate_reopen_report"))
        self.byte_validator = self.stack.enter_context(patch(MODULE + "validate_runtime_files", return_value={"SYNTHETIC_VALIDATOR_ONLY": True}))
        self.legacy_retention = self.stack.enter_context(patch("ucc.jobs.godot_runtime_bundle.retain_private_native_runtime_inputs"))

    def prepare(self, **extra):
        return prepare_registered_native_source(self.store, binding_sha256=self.binding.sha256,
            database_path=self.root / "NOT_OPENED.sqlite3", expected_project_id=self.project.project_id,
            expected_revision=self.project.revision, expected_master_blend=self.project.master_blend,
            expected_project_sha256=self.selected["project_sha"], expected_clip_id=self.binding.source.clip_id,
            expected_source_binding_sha256=self.binding.source.source_binding_sha256,
            expected_catalog_record_sha256=self.binding.source.catalog_record_sha256,
            runtime_directory=self.root / "private-code", runtime_code_provenance=self.provenance,
            motion_asset_id="motion:original-diagnostic", permissions=self.permissions,
            requested_capability=CAPABILITY, blender_exe=self.root / "NOT_EXECUTED.exe",
            worker_script=self.root / "NOT_EXECUTED.py", cancel=self.cancel, **extra)

    def receipts(self):
        return list((self.store.root / ".ucc-jobs").glob("registered-native-source-*/native_production_receipt.json"))

    def assert_no_success_receipt(self):
        for path in self.receipts():
            raw = json.loads(path.read_bytes())
            self.assertEqual(raw["status"], "PREPARATION_COMPLETION_FAILED")
            for key in ("runtime_code_provenance_verified", "runtime_execution_verified", "engine_import_verified",
                        "visual_quality_approved", "distribution_license_review_complete", "public_export_published",
                        "source_redistribution_authorized"):
                self.assertIs(raw[key], False)

    def test_two_workers_reuse_selected_proofs_preserve_ids_and_do_not_retain_v1(self):
        result = self.prepare()
        self.assertEqual([job.operation for job in self.runner.jobs],
            ["stage_registered_native_godot_runtime", "verify_registered_native_godot_runtime"])
        self.assertEqual([call.args[1] for call in self.worker_reader.call_args_list],
                         ["source_intake_first", "body_first"])
        self.assertEqual(result.target_action_binding_sha256, self.binding.sha256)
        recipe = json.loads((result.workdir / "native_recipe.json").read_bytes())
        self.assertEqual(recipe["project_snapshot"]["animations"], list(self.project.animations))
        self.assertEqual(recipe["project_snapshot"]["revision"], self.project.revision)
        self.assertEqual(self.store.file.read_bytes(), self.before)
        self.assertEqual(len(list(result.workdir.iterdir())), 5)
        receipt = json.loads(result.production_receipt.read_bytes())
        self.assertEqual(receipt["stage_job_id"], self.runner.jobs[0].job_id)
        self.assertEqual(receipt["reopen_job_id"], self.runner.jobs[1].job_id)
        for key in ("runtime_code_provenance_verified", "runtime_execution_verified", "engine_import_verified",
                    "visual_quality_approved", "distribution_license_review_complete", "public_export_published",
                    "source_redistribution_authorized"):
            self.assertIs(receipt[key], False)
        self.assertEqual(self.reopen_validator.call_count, 2)
        self.byte_validator.assert_called_once(); self.legacy_retention.assert_not_called()
        self.assertLessEqual(self.runner.timeouts[1], self.runner.timeouts[0])

    def test_stage_numeric_drift_rejects_without_receipt(self):
        def fault(phase, job, folder, raw):
            if phase == "before_report": raw["frames"][0]["raw_error_m"] = .0000011
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "frame errors"): self.prepare()
        self.assertEqual(len(self.runner.jobs), 1); self.assertEqual(self.receipts(), [])

    def test_stage_changed_actual_bytes_reject(self):
        def fault(phase, job, folder, raw):
            if phase == "after_report": (folder / "character.glb").write_bytes(b"CHANGED_SYNTHETIC")
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "output bytes changed"): self.prepare()
        self.assertEqual(len(self.runner.jobs), 1); self.assertEqual(self.receipts(), [])

    def test_stage_output_omission_rejects_closed_file_inventory(self):
        def fault(phase, job, folder, raw):
            if phase == "before_report": raw["files"].pop("character.glb")
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "output closure differs"): self.prepare()
        self.assertEqual(len(self.runner.jobs), 1); self.assertEqual(self.receipts(), [])

    def test_worker_result_cannot_claim_engine_approval(self):
        def fault(phase, job, folder, raw):
            if phase == "result": raw["engine_import_verified"] = True
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "closed profile"): self.prepare()
        self.assertEqual(len(self.runner.jobs), 1); self.assertEqual(self.receipts(), [])

    def test_fresh_repair_or_changed_bytes_reject_before_completion(self):
        def fault(phase, job, folder, raw):
            if len(self.runner.jobs) == 2 and phase == "before_report": raw["saved_output_rebuilt_or_repaired"] = True
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "repaired output"): self.prepare()
        self.assertEqual(self.receipts(), [])

    def test_fresh_actual_output_changes_reject_despite_saved_report_hash(self):
        def fault(phase, job, folder, raw):
            if len(self.runner.jobs) == 2 and phase == "after_report": (folder / "native_positions.bin").write_bytes(b"CHANGED")
        self.runner.fault = fault
        with self.assertRaisesRegex(ValidationError, "output bytes changed"): self.prepare()
        self.assertEqual(self.receipts(), [])

    def test_source_guard_failure_prevents_any_new_worker(self):
        self.guard.side_effect = ProjectStorageError("SYNTHETIC_SOURCE_DRIFT")
        with self.assertRaisesRegex(ProjectStorageError, "SOURCE_DRIFT"): self.prepare()
        self.assertEqual(self.runner.jobs, []); self.assertEqual(self.receipts(), [])

    def test_precancel_precedes_job_root_creation_and_admission(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"): self.prepare()
        self.assertFalse((self.store.root / ".ucc-jobs").exists())
        self.admit.assert_not_called(); self.runner_factory.assert_not_called()

    def test_finalize_callback_error_leaves_no_success_receipt(self):
        def progress(phase):
            if phase == "FINALIZE_REGISTERED_NATIVE_SOURCE": raise RuntimeError("SYNTHETIC_FINALIZE_CALLBACK_FAILURE")
        with self.assertRaisesRegex(RuntimeError, "CALLBACK_FAILURE"): self.prepare(progress=progress)
        self.assertEqual(len(self.runner.jobs), 2); self.assertEqual(self.receipts(), [])

    def test_progress_does_not_report_unqualified_complete_before_success_return(self):
        events = []
        def progress(phase):
            events.append(phase)
            if phase == "FINALIZE_REGISTERED_NATIVE_SOURCE":
                self.assertEqual(self.receipts(), [])
        result = self.prepare(progress=progress)
        self.assertEqual(events, ["STAGE_REGISTERED_NATIVE_SOURCE", "REOPEN_REGISTERED_NATIVE_SOURCE",
            "VALIDATE_PRIVATE_REGISTERED_NATIVE_BYTES", "FINALIZE_REGISTERED_NATIVE_SOURCE"])
        self.assertNotIn("COMPLETE", events)
        self.assertTrue(result.production_receipt.is_file())

    def metadata_flood(self, *, cancel=False, duplicate=False):
        real_scandir = os.scandir
        attack = []
        def progress(phase):
            if phase == "STAGE_REGISTERED_NATIVE_SOURCE":
                work = next((self.store.root / ".ucc-jobs").glob("registered-native-source-*"))
                with real_scandir(work) as entries:
                    names = [entry.name for entry in entries]
                if duplicate:
                    names = [names[0], names[0], *names[1:]]
                attack.append((work, LazyMetadataFlood(names, cancel=self.cancel if cancel else None)))
        def scan(path):
            if attack and Path(path) == attack[0][0]:
                return attack[0][1]
            return real_scandir(path)
        expected = "cancel" if cancel else "inventory changed"
        with patch(MODULE + "os.scandir", side_effect=scan):
            with self.assertRaisesRegex(ProjectStorageError, expected):
                self.prepare(progress=progress)
        self.assertEqual(self.runner.jobs, [])
        self.assertEqual(self.receipts(), [])
        return attack[0][1]

    def test_lazy_metadata_directory_flood_stops_at_first_foreign_entry(self):
        flood = self.metadata_flood()
        self.assertEqual(flood.consumed, len(flood.admitted_names) + 1)
        self.assertLessEqual(flood.consumed, 6)
        self.assertTrue(flood.closed)

    def test_lazy_metadata_directory_scan_checks_caller_cancel_per_entry(self):
        flood = self.metadata_flood(cancel=True)
        self.assertEqual(flood.consumed, 1)
        self.assertTrue(flood.closed)

    def test_lazy_metadata_directory_scan_rejects_duplicate_entry_immediately(self):
        flood = self.metadata_flood(duplicate=True)
        self.assertEqual(flood.consumed, 2)
        self.assertTrue(flood.closed)

    def test_final_metadata_scan_rejects_sixth_entry_without_consuming_flood(self):
        real_scandir = os.scandir; attack = []
        def guard():
            receipts = self.receipts()
            if receipts and not attack:
                work = receipts[0].parent
                with real_scandir(work) as entries:
                    names = [entry.name for entry in entries]
                self.assertEqual(len(names), 5)
                attack.append((work, LazyMetadataFlood(names)))
        def scan(path):
            if attack and Path(path) == attack[0][0]:
                return attack[0][1]
            return real_scandir(path)
        self.guard.side_effect = guard
        with patch(MODULE + "os.scandir", side_effect=scan):
            with self.assertRaisesRegex(ProjectStorageError, "inventory changed"):
                self.prepare()
        self.assertEqual(attack[0][1].consumed, 6)
        self.assertTrue(attack[0][1].closed)
        self.assert_no_success_receipt()

    def test_final_source_drift_does_not_leave_success_receipt(self):
        def guard():
            if self.receipts():
                raise ProjectStorageError("SYNTHETIC_FINAL_SOURCE_DRIFT")
        self.guard.side_effect = guard
        with self.assertRaisesRegex(ProjectStorageError, "FINAL_SOURCE_DRIFT"): self.prepare()
        self.assert_no_success_receipt()

    def test_final_receipt_changed_to_foreign_bytes_is_preserved(self):
        foreign = []
        def guard():
            receipts = self.receipts()
            if receipts:
                path = receipts[0]
                path.write_bytes(b"FOREIGN_RECEIPT_PRESERVE"); foreign.append(path)
                raise ProjectStorageError("SYNTHETIC_FOREIGN_RECEIPT")
        self.guard.side_effect = guard
        with self.assertRaisesRegex(ProjectStorageError, "FOREIGN_RECEIPT"): self.prepare()
        self.assertEqual(foreign[0].read_bytes(), b"FOREIGN_RECEIPT_PRESERVE")

    def test_receipt_replaced_before_final_descriptor_admission_is_preserved(self):
        path = self.root / "unit-receipt.json"; path.write_bytes(b"SYNTHETIC_ORIGINAL")
        expected = identity(path), sha256(path.read_bytes()).hexdigest()
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(b"FOREIGN_REPLACEMENT"); replacement.replace(path)
        finalize = Mock()
        with self.assertRaisesRegex(ProjectStorageError, "changed before final admission"):
            _finish_owned_receipt(path, expected, finalize)
        finalize.assert_not_called()
        self.assertEqual(path.read_bytes(), b"FOREIGN_REPLACEMENT")

    def test_final_caller_cancel_does_not_leave_owned_success_receipt(self):
        def guard():
            if self.receipts(): self.cancel.set()
        self.guard.side_effect = guard
        with self.assertRaisesRegex(ProjectStorageError, "cancel"): self.prepare()
        self.assert_no_success_receipt()

    def test_metadata_drift_during_final_output_validation_blocks_completion(self):
        calls = []
        def outputs(*args):
            _outputs(*args); calls.append(True)
            if len(calls) == 3:
                receipt = self.receipts()[0]
                (receipt.parent / "runtime_request.json").write_bytes(b"FOREIGN_CHANGED_REQUEST")
        with patch(MODULE + "_outputs", side_effect=outputs):
            with self.assertRaisesRegex(ProjectStorageError, "metadata changed"):
                self.prepare()
        self.assert_no_success_receipt()

    def test_source_drift_during_final_output_validation_blocks_completion(self):
        calls = []; drifted = []
        def outputs(*args):
            _outputs(*args); calls.append(True)
            if len(calls) == 3: drifted.append(True)
        def guard():
            if drifted: raise ProjectStorageError("SYNTHETIC_FINAL_OUTPUT_SOURCE_DRIFT")
        self.guard.side_effect = guard
        with patch(MODULE + "_outputs", side_effect=outputs):
            with self.assertRaisesRegex(ProjectStorageError, "FINAL_OUTPUT_SOURCE_DRIFT"):
                self.prepare()
        self.assert_no_success_receipt()

    def test_foreign_metadata_entry_is_preserved_and_rejected(self):
        foreign = []
        def progress(phase):
            if phase == "STAGE_REGISTERED_NATIVE_SOURCE":
                work = next((self.store.root / ".ucc-jobs").glob("registered-native-source-*"))
                path = work / "FOREIGN.txt"; path.write_bytes(b"FOREIGN_PRESERVE"); foreign.append(path)
        with self.assertRaisesRegex(ProjectStorageError, "inventory changed"): self.prepare(progress=progress)
        self.assertEqual(foreign[0].read_bytes(), b"FOREIGN_PRESERVE")
        self.assertEqual(self.runner.jobs, []); self.assertEqual(self.receipts(), [])

    def test_replaced_metadata_directory_is_not_adopted(self):
        replacement = []
        def progress(phase):
            if phase == "STAGE_REGISTERED_NATIVE_SOURCE":
                work = next((self.store.root / ".ucc-jobs").glob("registered-native-source-*"))
                work.rename(work.with_name("preserved-original")); work.mkdir()
                (work / "FOREIGN.txt").write_bytes(b"FOREIGN_REPLACEMENT"); replacement.append(work)
        with self.assertRaisesRegex(ProjectStorageError, "directory was replaced"): self.prepare(progress=progress)
        self.assertEqual((replacement[0] / "FOREIGN.txt").read_bytes(), b"FOREIGN_REPLACEMENT")
        self.assertEqual(self.runner.jobs, []); self.assertEqual(self.receipts(), [])
