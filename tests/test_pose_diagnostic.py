"""Project-bound pose diagnostic contract tests. Fake Blender proof is test-only."""
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
from ucc.jobs.pose_diagnostic import (
    PoseEvidenceError, check_saved_master_pose, validate_pose_evidence,
    verify_repeated_pose,
)
from ucc.jobs.protocol import JobRequest, JobResult


def synthetic_pose_evidence() -> dict:
    return {
        "status": "REAL_STATIC_SKIN_POSE_MOVEMENT_MEASURED",
        "selected_deform_bone": "UpperArm.L",
        "rotation_axis_index": 0,
        "rotation_degrees": 20.0,
        "moved_vertex_count": 500,
        "max_vertex_displacement_local": .03,
        "evaluated_vertex_count": 19000,
        "neutral_evaluated_sha256": "a" * 64,
        "posed_evaluated_sha256": "b" * 64,
        "restored_evaluated_sha256": "a" * 64,
        "rig_bone_count": 163,
        "rig_weight_sha256": "c" * 64,
        "rig_rest_sha256": "d" * 64,
        "rig_binding_verified": True,
        "source_master_saved": False,
        "animation_clip_playback_verified": False,
        "retargeting_verified": False,
        "engine_import_verified": False,
        "blender_version": "5.3.0",
    }


class SavedRigPoseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = ProjectStore(self.root / "project")
        self.store.save(CharacterProject.new("Rig Check"))
        staging = self.root / "mock-stage"
        staging.mkdir()
        source = staging / "test.blend"
        source.write_bytes(b"BLENDER" + b"synthetic-saved-master" * 140)
        saved = stage_unverified_master(
            self.store, source, authorized_source_root=staging,
        )
        self.initial = saved.project
        self.master = saved.master_path
        self.executable = self.root / "not-actual-blender"
        self.worker = self.root / "mock-entrypoint.py"
        self.executable.write_text("not executed", encoding="utf-8")
        self.worker.write_text("# not executed", encoding="utf-8")
        self.cancel = Event()
        self.operations = []
        self.calls = 0
        self.details = synthetic_pose_evidence()

    def response(self, job, **kwargs):
        self.calls += 1
        self.operations.append(job.operation)
        output = self.store.root / ".ucc-jobs" / job.job_id
        output.mkdir(parents=True)
        (output / "candidate.blend").write_bytes(
            kwargs["staged_inputs"]["candidate.blend"].read_bytes()
        )
        return JobResult(job.job_id, job.operation, "ok", dict(self.details)), output

    def invoke(self, **kwargs):
        params = dict(
            blender_exe=self.executable, worker_script=self.worker,
            expected_project_id=self.initial.project_id,
            expected_revision=self.initial.revision,
            expected_master_blend=self.initial.master_blend,
            cancel=self.cancel,
        )
        params.update(kwargs)
        with patch("ucc.jobs.pose_diagnostic.BlenderJobRunner.run",
                   side_effect=self.response):
            return check_saved_master_pose(self.store, **params)

    def test_two_independent_workers_and_no_authoritative_mutation(self):
        metadata = self.store.file.read_bytes()
        master = self.master.read_bytes()
        result = self.invoke()
        self.assertEqual(self.operations,
                         ["verify_skin_deformation", "verify_skin_deformation"])
        self.assertEqual(len(result.worker_job_ids), 2)
        self.assertNotEqual(result.worker_job_ids[0], result.worker_job_ids[1])
        self.assertEqual(result.evidence["moved_vertex_count"], 500)
        self.assertEqual(result.master_blend, self.initial.master_blend)
        self.assertFalse(result.animation_playback_verified)
        self.assertEqual(self.store.file.read_bytes(), metadata)
        self.assertEqual(self.master.read_bytes(), master)

    def test_reject_invalid_protocol_options(self):
        with self.assertRaisesRegex(ValidationError, "needs input_project"):
            JobRequest.new("verify_skin_deformation")
        with self.assertRaisesRegex(ValidationError, "fixed"):
            JobRequest.new("verify_skin_deformation", input_project="candidate.blend",
                           options={"angle_degrees": 120})
        with self.assertRaises(ValidationError):
            JobRequest.new("verify_skin_deformation", input_project="../../private.blend")
        req = JobRequest.new("verify_skin_deformation", input_project="candidate.blend")
        self.assertEqual(JobRequest.from_dict(req.as_dict()), req)

    def test_forged_success_or_unrestored_pose_is_rejected(self):
        for mod in (
            {"moved_vertex_count": 0},
            {"source_master_saved": True},
            {"engine_import_verified": True},
            {"restored_evaluated_sha256": "e" * 64},
            {"posed_evaluated_sha256": "a" * 64},
            {"rotation_axis_index": 9},
            {"max_vertex_displacement_local": 0.0},
            {"rig_weight_sha256": "notasha"},
        ):
            with self.subTest(modification=mod):
                with self.assertRaises(PoseEvidenceError):
                    validate_pose_evidence({**synthetic_pose_evidence(), **mod})

    def test_worker_disagreement_rejects_without_metadata_write(self):
        original_bytes = self.store.file.read_bytes()
        first = synthetic_pose_evidence()
        second = {**first, "selected_deform_bone": "Other"}
        with self.assertRaisesRegex(PoseEvidenceError, "disagreed"):
            verify_repeated_pose(first, second)

        def mismatch(job, **kwargs):
            result, work = self.response(job, **kwargs)
            if self.calls == 2:
                result = replace(result, details=second)
            return result, work
        with patch("ucc.jobs.pose_diagnostic.BlenderJobRunner.run",
                   side_effect=mismatch):
            with self.assertRaisesRegex(PoseEvidenceError, "disagreed"):
                check_saved_master_pose(
                    self.store, blender_exe=self.executable,
                    worker_script=self.worker,
                    expected_project_id=self.initial.project_id,
                    expected_revision=self.initial.revision,
                    expected_master_blend=self.initial.master_blend,
                )
        self.assertEqual(self.store.file.read_bytes(), original_bytes)

    def test_changed_project_during_worker_rejected(self):
        def changed(job, **kwargs):
            answer = self.response(job, **kwargs)
            if self.calls == 2:
                current = self.store.load()
                self.store.save(replace(current, name="Other Editor",
                                        revision=current.revision + 1),
                                expected_revision=current.revision)
            return answer
        with patch("ucc.jobs.pose_diagnostic.BlenderJobRunner.run",
                   side_effect=changed):
            with self.assertRaises(ProjectConflict):
                check_saved_master_pose(
                    self.store, blender_exe=self.executable,
                    worker_script=self.worker,
                    expected_project_id=self.initial.project_id,
                    expected_revision=self.initial.revision,
                    expected_master_blend=self.initial.master_blend,
                )
        self.assertEqual(self.store.load().name, "Other Editor")

    def test_source_content_address_mismatch_never_invokes_blender(self):
        self.master.write_bytes(b"BLENDER" + b"tampered" * 200)
        with self.assertRaisesRegex(ProjectStorageError, "SHA-256"):
            self.invoke()
        self.assertEqual(self.operations, [])

    def test_cancellation_before_and_during_worker(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.invoke()
        self.assertEqual(self.operations, [])
        self.cancel.clear()

        def cancel_second(job, **kwargs):
            answer = self.response(job, **kwargs)
            if self.calls == 1:
                self.cancel.set()
            return answer
        with patch("ucc.jobs.pose_diagnostic.BlenderJobRunner.run",
                   side_effect=cancel_second):
            with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
                check_saved_master_pose(
                    self.store, blender_exe=self.executable,
                    worker_script=self.worker,
                    expected_project_id=self.initial.project_id,
                    expected_revision=self.initial.revision,
                    expected_master_blend=self.initial.master_blend,
                    cancel=self.cancel,
                )
        self.assertEqual(self.store.load(), self.initial)

    def test_missing_executable_and_stale_revision_rejected(self):
        with self.assertRaises(ValidationError):
            self.invoke(blender_exe=self.root / "missing-blender")
        with self.assertRaises(ProjectConflict):
            self.invoke(expected_revision=999)
        self.assertEqual(self.operations, [])


if __name__ == "__main__":
    unittest.main()
