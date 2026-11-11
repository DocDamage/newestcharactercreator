"""Synthetic coordinator tests only; real Blender evidence lives in integration CI."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.geometry_evidence import EvidenceError
from ucc.jobs.humanoid_generation import generate_humanoid
from ucc.jobs.protocol import JobResult


class HumanoidGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ProjectStore(self.root / "hero")
        self.saved = self.store.save(CharacterProject.new("Hero"))
        self.blender = self.root / "fake-blender-for-contract-tests"
        self.script = self.root / "fake-worker.py"
        self.blender.write_text("unit-test-only", encoding="utf-8")
        self.script.write_text("# not executed", encoding="utf-8")
        self.bytes = b"BLENDER" + b"synthetic-not-a-real-mpfb-file" * 200
        self.calls = []
        self.requests = []
        self.cancel = Event()

    def responses(self, job, **kwargs):
        path = self.store.root / ".ucc-jobs" / job.job_id
        path.mkdir(parents=True, exist_ok=False)
        self.calls.append(job.operation)
        self.requests.append(job)
        controls = job.options["macro_parameters"]
        shape = {
            "macro_parameters_observed": dict(controls),
            "macro_evaluated_vertices": 19158,
            "macro_evaluated_sha256": "a" * 64,
            "macro_active_shape_keys": 3,
            "macro_shape_evaluated": True,
            "visual_deformation_verified": False,
            "engine_import_verified": False,
        }
        if job.operation == "create_human":
            (path / "generated_human.blend").write_bytes(self.bytes)
            details = {
                "staged_blend": "generated_human.blend", "method": "HumanService",
                "rig_choice": "default", "blender_version": "5.3.0",
                "created_meshes": [{"vertex_count": 19158}],
                "rigs": [{"bone_count": 163}],
                **shape,
            }
        else:
            source = kwargs["staged_inputs"]["candidate.blend"]
            (path / "candidate.blend").write_bytes(source.read_bytes())
            details = {
                "blender_version": "5.3.0", "mesh_count": 2,
                "vertex_count": 19166, "armatures": [{"bone_count": 163}],
                **shape,
            }
        return JobResult(job.job_id, job.operation, "ok", details), path

    def run_generation(self, **kwargs):
        options = {
            "blender_exe": self.blender, "worker_script": self.script,
            "expected_project_id": self.saved.project_id,
            "expected_revision": self.saved.revision, "cancel": self.cancel,
        }
        options.update(kwargs)
        with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run",
                   side_effect=self.responses):
            return generate_humanoid(self.store, **options)

    def test_independently_inspected_worker_promotes_unverified_master(self):
        output = self.run_generation()
        self.assertEqual(self.calls, ["create_human", "inspect_character"])
        self.assertEqual(self.requests[0].options, {
            "macro_parameters": {"height": .5, "muscle": .5, "weight": .5},
        })
        self.assertEqual(self.requests[1].options, self.requests[0].options)
        self.assertTrue(output.observed["morph_save_reopen_verified"])
        self.assertEqual(output.revision.project.revision, 2)
        self.assertEqual(output.geometry_state, "generated_unverified")
        self.assertEqual(self.store.load().geometry_state, "generated_unverified")
        self.assertEqual(output.revision.sha256, sha256(self.bytes).hexdigest())
        self.assertEqual(output.revision.master_path.read_bytes(), self.bytes)
        self.assertEqual(output.observed["reopened_bone_count"], 163)
        self.assertEqual(len(self.store.list_backups()), 1)
        self.assertIn("not passed", " ".join(self.store.load().export_readiness()))

    def test_saved_nondefault_controls_are_sent_and_persisted(self):
        changed = replace(
            self.saved, parameters=(("height", .85), ("muscle", .2), ("weight", .9)),
            revision=self.saved.revision + 1,
        )
        self.saved = self.store.save(changed, expected_revision=self.saved.revision)
        result = self.run_generation()
        self.assertEqual(self.requests[0].options["macro_parameters"], {
            "height": .85, "muscle": .2, "weight": .9,
        })
        self.assertEqual(result.observed["macro_parameters_observed"]["weight"], .9)
        self.assertEqual(self.store.load().parameters, self.saved.parameters)

    def test_wrong_mpbf_macro_or_evaluated_shape_hash_does_not_commit(self):
        for fault in ("macro_value", "reopened_hash"):
            with self.subTest(fault=fault):
                self.requests.clear()
                def altered(job, **kwargs):
                    result, folder = self.responses(job, **kwargs)
                    if job.operation == "inspect_character":
                        details = dict(result.details)
                        if fault == "macro_value":
                            details["macro_parameters_observed"] = {
                                "height": .9, "muscle": .5, "weight": .5
                            }
                        else:
                            details["macro_evaluated_sha256"] = "b" * 64
                        return replace(result, details=details), folder
                    return result, folder
                with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run",
                           side_effect=altered):
                    with self.assertRaises(ValidationError):
                        generate_humanoid(
                            self.store, blender_exe=self.blender, worker_script=self.script,
                            expected_project_id=self.saved.project_id,
                            expected_revision=self.saved.revision,
                        )
                self.assertEqual(self.store.load(), self.saved)
                self.assertFalse((self.store.root / "master").exists())

    def test_regeneration_blocks_unmapped_parts_or_animations(self):
        with self.assertRaisesRegex(ValidationError, "animation"):
            current = self.store.load()
            changed = replace(current, animations=("external-reference",),
                              revision=current.revision + 1)
            self.saved = self.store.save(changed, expected_revision=current.revision)
            self.run_generation()
        self.assertEqual(self.calls, [])

    def test_project_id_and_revision_checked_before_worker(self):
        with self.assertRaises(ProjectConflict):
            self.run_generation(expected_project_id="different")
        with self.assertRaises(ProjectConflict):
            self.run_generation(expected_revision=900)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.load(), self.saved)

    def test_second_editor_save_during_worker_blocks_promotion(self):
        def changed(job, **kwargs):
            result = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                current = self.store.load()
                self.store.save(replace(current, name="Concurrent edit", revision=2),
                                expected_revision=1)
            return result
        with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run", side_effect=changed):
            with self.assertRaises(ProjectConflict):
                generate_humanoid(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id, expected_revision=1,
                )
        current = self.store.load()
        self.assertEqual(current.name, "Concurrent edit")
        self.assertEqual(current.geometry_state, "not_generated")

    def test_missing_rig_does_not_save_project(self):
        def invalid(job, **kwargs):
            reply, root = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                reply = replace(reply, details={**reply.details, "armatures": []})
            return reply, root
        with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run", side_effect=invalid):
            with self.assertRaises(EvidenceError):
                generate_humanoid(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id, expected_revision=1,
                )
        self.assertEqual(self.store.load(), self.saved)
        self.assertFalse((self.store.root / "master").exists())

    def test_bytes_differ_between_creation_and_reopen(self):
        def tampered(job, **kwargs):
            result, root = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                (root / "candidate.blend").write_bytes(b"BLENDER" + b"changed" * 200)
            return result, root
        with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run", side_effect=tampered):
            with self.assertRaisesRegex(EvidenceError, "differs"):
                generate_humanoid(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id, expected_revision=1,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_fake_blender_header_cannot_be_committed(self):
        self.bytes = b"NOTBLEND" + b"synthetic" * 200
        with self.assertRaisesRegex(ProjectStorageError, "not a Blender-format"):
            self.run_generation()
        self.assertEqual(self.store.load(), self.saved)

    def test_cancellation_before_worker_and_before_commit(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.run_generation()
        self.assertEqual(self.calls, [])
        self.cancel.clear()
        def delayed_cancel(job, **kwargs):
            result = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                self.cancel.set()
            return result
        with patch("ucc.jobs.humanoid_generation.BlenderJobRunner.run",
                   side_effect=delayed_cancel):
            with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
                generate_humanoid(
                    self.store, blender_exe=self.blender, worker_script=self.script,
                    expected_project_id=self.saved.project_id, expected_revision=1,
                    cancel=self.cancel,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_missing_blender_and_worker_paths_fail_before_any_job(self):
        with self.assertRaises(ValidationError):
            self.run_generation(blender_exe=self.root / "missing")
        with self.assertRaises(ValidationError):
            self.run_generation(worker_script=self.root / "missing.py")
        self.assertEqual(self.calls, [])

    def test_job_directory_symlink_cannot_escape_project(self):
        other = self.root / "outside"
        other.mkdir()
        try:
            (self.store.root / ".ucc-jobs").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS cannot create symlink")
        with self.assertRaisesRegex(ProjectStorageError, "redirected"):
            self.run_generation()
        self.assertEqual(list(other.iterdir()), [])

    def test_source_worker_revision_stays_unverified_even_if_backend_passes(self):
        result = self.run_generation()
        self.assertIsNone(result.revision.project.rig_profile)
        self.assertNotEqual(result.revision.project.export_readiness(), ())


if __name__ == "__main__":
    unittest.main()
