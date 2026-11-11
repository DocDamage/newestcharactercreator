"""Contract and rollback tests only, not actual Blender rigging evidence."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.body_revision import apply_saved_body_revision
from ucc.jobs.geometry_evidence import EvidenceError
from ucc.jobs.protocol import JobRequest, JobResult


def rig(hash_value: str, rest: str) -> dict:
    return {
        "bone_count": 163, "bone_names": ["A", "B", "C", "D", "E"],
        "bone_weight_groups": ["A", "B", "C", "D", "E"],
        "weighted_vertices": 19158, "weight_sha256": hash_value,
        "rig_rest_sha256": rest, "armature_modifier_count": 1,
        "rig_binding_verified": True, "animation_deformation_verified": False,
    }


class ExistingMasterRefitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ProjectStore(self.root / "character")
        first = self.store.save(CharacterProject.new("Character"))
        stage = self.root / "fake-worker"
        stage.mkdir()
        source = stage / "fake.blend"
        source.write_bytes(b"BLENDER" + b"only-a-synthetic-contract-test" * 200)
        initial = stage_unverified_master(
            self.store, source, authorized_source_root=stage
        )
        self.old = initial.master_path
        self.before_data = self.old.read_bytes()
        saved = self.store.load()
        desired = {"height": .82, "muscle": .22, "weight": .8}
        self.saved = self.store.save(
            replace(saved, parameters=tuple(sorted(desired.items())),
                    revision=saved.revision + 1),
            expected_revision=saved.revision,
        )
        self.values = desired
        self.blender = self.root / "not-real-blender"
        self.blender.write_bytes(b"unit-test-only")
        self.worker = self.root / "not-real-worker.py"
        self.worker.write_text("# unit test only", encoding="utf-8")
        self.rig_before = rig("a" * 64, "1" * 64)
        self.rig_after = rig("a" * 64, "2" * 64)
        self.cancel = Event()
        self.operations = []

    def responses(self, job, **kwargs):
        folder = self.store.root / ".ucc-jobs" / job.job_id
        folder.mkdir(parents=True)
        self.operations.append(job.operation)
        staged = kwargs["staged_inputs"]
        if job.operation == "refit_human":
            (folder / "candidate.blend").write_bytes(
                staged["candidate.blend"].read_bytes()
            )
            (folder / "refitted_human.blend").write_bytes(
                b"BLENDER" + b"changed-unit-test-data" * 300
            )
            details = {
                "staged_blend": "refitted_human.blend", "refit_saved": True,
                "previous_macros": {"height": .5, "muscle": .5, "weight": .5},
                "previous_evaluated_sha256": "0" * 64,
                "previous_rig": self.rig_before,
                "updated_rig": self.rig_after,
            }
        else:
            (folder / "refit_candidate.blend").write_bytes(
                staged["refit_candidate.blend"].read_bytes()
            )
            details = {"rig_binding": self.rig_after}
        details.update({
            "macro_parameters_observed": dict(self.values),
            "macro_evaluated_vertices": 19158,
            "macro_evaluated_sha256": "c" * 64,
            "macro_active_shape_keys": 6,
            "macro_shape_evaluated": True,
            "visual_deformation_verified": False,
        })
        return JobResult(job.job_id, job.operation, "ok", details), folder

    def execute(self, **changes):
        options = {
            "blender_exe": self.blender, "worker_script": self.worker,
            "expected_project_id": self.saved.project_id,
            "expected_revision": self.saved.revision,
            "expected_master_blend": self.saved.master_blend,
            "cancel": self.cancel,
        }
        options.update(changes)
        with patch("ucc.jobs.body_revision.BlenderJobRunner.run",
                   side_effect=self.responses):
            return apply_saved_body_revision(self.store, **options)

    def test_new_revision_preserves_original_and_real_evidence_labels(self):
        output = self.execute()
        self.assertEqual(self.operations, ["refit_human", "inspect_character"])
        self.assertNotEqual(output.revision.master_path, self.old)
        self.assertEqual(self.old.read_bytes(), self.before_data)
        self.assertEqual(self.store.load().revision, self.saved.revision + 1)
        self.assertEqual(self.store.load().geometry_state, "generated_unverified")
        self.assertEqual(output.observed["weighted_vertices"], 19158)
        self.assertEqual(output.observed["reopened_bones"], 163)
        self.assertTrue(output.observed["morph_save_reopen_verified"])
        self.assertFalse(output.observed["animation_deformation_verified"])
        self.assertNotEqual(self.store.load().export_readiness(), ())

    def test_refit_workflow_rejects_bad_protocol_options(self):
        with self.assertRaises(ValidationError):
            JobRequest.new("refit_human", input_project="candidate.blend")
        with self.assertRaises(ValidationError):
            JobRequest.new("refit_human", input_project="candidate.blend",
                           options={"macro_parameters": self.values, "path": "../../x"})
        with self.assertRaises(ValidationError):
            JobRequest.new("refit_human", input_project="../unsafe.blend",
                           options={"macro_parameters": self.values})
        req = JobRequest.new("refit_human", input_project="candidate.blend",
                             options={"macro_parameters": self.values})
        self.assertEqual(req.operation, "refit_human")

    def test_revision_and_master_must_be_current(self):
        for opt in (
            {"expected_revision": 100}, {"expected_project_id": "other"},
            {"expected_master_blend": "master/versions/" + "0" * 64 + ".blend"},
        ):
            with self.subTest(opt=opt), self.assertRaises(ProjectConflict):
                self.execute(**opt)
        self.assertEqual(self.operations, [])
        self.assertEqual(self.old.read_bytes(), self.before_data)

    def test_rig_weight_loss_rejected_before_project_save(self):
        self.rig_after = {**self.rig_after, "weight_sha256": "b" * 64}
        with self.assertRaisesRegex(EvidenceError, "weight"):
            self.execute()
        self.assertEqual(self.store.load(), self.saved)
        self.assertEqual(self.old.read_bytes(), self.before_data)

    def test_different_rig_on_reopen_rejected(self):
        def changed(job, **kwargs):
            answer, directory = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                answer = replace(answer, details={
                    **answer.details,
                    "rig_binding": {**self.rig_after, "rig_rest_sha256": "d" * 64}
                })
            return answer, directory
        with patch("ucc.jobs.body_revision.BlenderJobRunner.run", side_effect=changed):
            with self.assertRaisesRegex(EvidenceError, "independent reopen"):
                apply_saved_body_revision(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_no_shape_change_cannot_commit(self):
        def identical(job, **kwargs):
            answer, directory = self.responses(job, **kwargs)
            if job.operation == "refit_human":
                answer = replace(answer, details={
                    **answer.details, "previous_evaluated_sha256": "c" * 64
                })
            return answer, directory
        with patch("ucc.jobs.body_revision.BlenderJobRunner.run", side_effect=identical):
            with self.assertRaisesRegex(EvidenceError, "did not cause"):
                apply_saved_body_revision(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_concurrent_project_save_cannot_promote_refit(self):
        def raced(job, **kwargs):
            response = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                project = self.store.load()
                self.store.save(replace(project, name="Other editor",
                                        revision=project.revision + 1),
                                expected_revision=project.revision)
            return response
        with patch("ucc.jobs.body_revision.BlenderJobRunner.run", side_effect=raced):
            with self.assertRaises(ProjectConflict):
                apply_saved_body_revision(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load().name, "Other editor")
        self.assertEqual(self.store.load().master_blend, self.saved.master_blend)

    def test_cancellation_does_not_write_pointer(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.execute()
        self.assertEqual(self.operations, [])
        self.cancel.clear()
        def late(job, **kwargs):
            response = self.responses(job, **kwargs)
            if job.operation == "inspect_character":
                self.cancel.set()
            return response
        with patch("ucc.jobs.body_revision.BlenderJobRunner.run", side_effect=late):
            with self.assertRaises(ProjectStorageError):
                apply_saved_body_revision(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend, cancel=self.cancel,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_missing_or_redirected_master_rejected(self):
        self.old.write_bytes(b"BLENDER" + b"tampered" * 200)
        with self.assertRaisesRegex(ProjectStorageError, "SHA-256"):
            self.execute()
        self.assertEqual(self.operations, [])


if __name__ == "__main__":
    unittest.main()
