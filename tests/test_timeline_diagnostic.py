"""Synthetic timeline proof contracts; real Blender CI is the only integration evidence."""
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
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.jobs.timeline_diagnostic import (
    TimelineEvidenceError, check_saved_master_timeline, compare_timelines,
    validate_timeline_response,
)


def synthetic_frames() -> dict:
    hashed = ["a", "b", "c", "b", "a"]
    moved = [0, 100, 200, 100, 0]
    return {
        "status": "REAL_BLENDER_KEYFRAMED_SKIN_TIMELINE_MEASURED",
        "fps": 24, "duration_seconds": 1.0,
        "keyframes": [1, 13, 25],
        "sampled_frames": [
            {
                "frame": frame, "evaluated_sha256": digest * 64,
                "evaluated_vertex_count": 19158,
                "moved_vertices": count,
                "max_displacement_local": .02 if count else 0.0,
            }
            for frame, digest, count in zip((1, 7, 13, 19, 25), hashed, moved)
        ],
        "selected_deform_bone": "head",
        "rotation_axis_index": 0, "rotation_degrees": 20.0,
        "rig_bone_count": 163, "rig_weight_sha256": "d" * 64,
        "rig_rest_sha256": "e" * 64, "evaluated_vertex_count": 19158,
        "action_keyframes_inserted": 3, "action_assigned": True,
        "timeline_interpolation_evaluated": True,
        "source_master_saved": False,
        "original_animation_imported": False,
        "user_animation_playback_verified": False,
        "retargeting_verified": False, "engine_import_verified": False,
        "blender_version": "5.3.0",
    }


class TimelineContracts(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.store = ProjectStore(self.root / "hero")
        self.store.save(CharacterProject.new("Hero"))
        root = self.root / "staged-contract"
        root.mkdir()
        source = root / "not-a-real-blender-human.blend"
        source.write_bytes(b"BLENDER" + b"synthetic-test" * 200)
        stage = stage_unverified_master(self.store, source, authorized_source_root=root)
        self.saved = stage.project
        self.master = stage.master_path
        self.blender = self.root / "not-real-blender"
        self.worker = self.root / "not-real-worker.py"
        self.blender.write_text("test only", encoding="utf-8")
        self.worker.write_text("# not executed", encoding="utf-8")
        self.cancel = Event()
        self.details = synthetic_frames()
        self.invocations = []

    def response(self, job, **kwargs):
        self.invocations.append(job)
        directory = self.store.root / ".ucc-jobs" / job.job_id
        directory.mkdir(parents=True)
        (directory / "candidate.blend").write_bytes(
            kwargs["staged_inputs"]["candidate.blend"].read_bytes()
        )
        return JobResult(job.job_id, job.operation, "ok", dict(self.details)), directory

    def execute(self, **changes):
        options = dict(
            blender_exe=self.blender, worker_script=self.worker,
            expected_project_id=self.saved.project_id,
            expected_revision=self.saved.revision,
            expected_master_blend=self.saved.master_blend,
            cancel=self.cancel,
        )
        options.update(changes)
        with patch("ucc.jobs.timeline_diagnostic.BlenderJobRunner.run",
                   side_effect=self.response):
            return check_saved_master_timeline(self.store, **options)

    def test_two_worker_runs_and_no_saved_master_changes(self):
        original_project = self.store.file.read_bytes()
        original_master = self.master.read_bytes()
        result = self.execute()
        self.assertEqual(len(result.worker_job_ids), 2)
        self.assertNotEqual(*result.worker_job_ids)
        self.assertEqual(len(self.invocations), 2)
        self.assertEqual(result.evidence["sampled_frames"][2]["moved_vertices"], 200)
        self.assertTrue(all(x.operation == "verify_keyframed_timeline"
                            for x in self.invocations))
        self.assertFalse(any(x.options for x in self.invocations))
        self.assertEqual(self.store.file.read_bytes(), original_project)
        self.assertEqual(self.master.read_bytes(), original_master)

    def test_keyframe_protocol_disallows_user_supplied_motion(self):
        with self.assertRaisesRegex(ValidationError, "needs input_project"):
            JobRequest.new("verify_keyframed_timeline")
        with self.assertRaisesRegex(ValidationError, "fixed"):
            JobRequest.new("verify_keyframed_timeline", input_project="candidate.blend",
                           options={"bone": "UserBone", "motion": [1, 2, 3]})
        with self.assertRaises(ValidationError):
            JobRequest.new("verify_keyframed_timeline", input_project="../secrets.blend")
        job = JobRequest.new("verify_keyframed_timeline", input_project="candidate.blend")
        self.assertEqual(JobRequest.from_dict(job.as_dict()), job)

    def test_fake_status_bad_frames_and_false_certification_rejected(self):
        for change in (
            {"action_assigned": False},
            {"action_keyframes_inserted": 0},
            {"fps": 48},
            {"user_animation_playback_verified": True},
            {"retargeting_verified": True},
            {"source_master_saved": True},
            {"sampled_frames": []},
            {"sampled_frames": synthetic_frames()["sampled_frames"][:-1]},
        ):
            with self.subTest(change=change), self.assertRaises(TimelineEvidenceError):
                validate_timeline_response({**synthetic_frames(), **change})

    def test_two_workers_must_agree_on_each_frame_hash(self):
        modified = synthetic_frames()
        rows = [dict(x) for x in modified["sampled_frames"]]
        rows[1]["evaluated_sha256"] = "f" * 64
        modified["sampled_frames"] = rows
        with self.assertRaisesRegex(TimelineEvidenceError, "disagree"):
            compare_timelines(synthetic_frames(), modified)

        count = 0
        def difference(job, **kwargs):
            nonlocal count
            count += 1
            result, folder = self.response(job, **kwargs)
            if count == 2:
                result = replace(result, details=modified)
            return result, folder
        with patch("ucc.jobs.timeline_diagnostic.BlenderJobRunner.run",
                   side_effect=difference):
            with self.assertRaises(TimelineEvidenceError):
                check_saved_master_timeline(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load(), self.saved)

    def test_cancellation_stale_version_and_tampered_master_fail(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.execute()
        self.cancel.clear()
        with self.assertRaises(ProjectConflict):
            self.execute(expected_revision=999)
        self.assertEqual(self.invocations, [])

        def cancelled(job, **kw):
            result = self.response(job, **kw)
            self.cancel.set()
            return result
        with patch("ucc.jobs.timeline_diagnostic.BlenderJobRunner.run",
                   side_effect=cancelled):
            with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
                check_saved_master_timeline(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                    cancel=self.cancel,
                )
        self.assertEqual(self.store.load(), self.saved)
        self.master.write_bytes(b"BLENDER" + b"altered" * 200)
        self.cancel.clear()
        with self.assertRaisesRegex(ProjectStorageError, "SHA-256"):
            self.execute()


if __name__ == "__main__":
    unittest.main()
