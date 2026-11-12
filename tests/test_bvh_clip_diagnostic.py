"""Synthetic coordinator tests: real BVH/Blender acceptance is Linux integration CI."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
import math
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.bvh_clip_diagnostic import (
    BvhPreviewEvidenceError, check_selected_bvh, validate_local_bvh_report,
)
from ucc.jobs.protocol import JobRequest, JobResult
from ucc.library.provenance import LicensePolicy, AssetPolicyError


def fixture(path: Path) -> None:
    root = (
        "HIERARCHY\nROOT head\n{\nOFFSET 0 0 0\n"
        "CHANNELS 3 Xrotation Yrotation Zrotation\n"
        "End Site\n{\nOFFSET 0 0.1 0\n}\n}\n"
        "MOTION\nFrames: 25\nFrame Time: 0.041666667\n"
    )
    rows = [
        f"{20 * math.sin(math.pi * idx / 24):.7f} 0 0" for idx in range(25)
    ]
    path.write_text(root + "\n".join(rows) + "\n", encoding="utf-8")


def report(source: Path) -> dict:
    digests = ["a", "b", "c", "b", "a"]
    return {
        "status": "REAL_LOCAL_BVH_SOURCE_DRIVEN_MESH_MOTION_MEASURED",
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "source_bone": "head", "target_bone": "head",
        "mapping_method": "DIRECT_NAME_ROTATION_DELTA_NO_REST_CALIBRATION",
        "source_frame_count": 25, "source_frame_time": .041666667,
        "keyframes_inserted": 25,
        "frame_sample_count": 5,
        "sampled_frames": [
            {"frame": frame, "evaluated_sha256": digest * 64,
             "evaluated_vertex_count": 19158,
             "moved_vertices": count,
             "max_displacement_local": .04 if count else 0.0}
            for frame, digest, count in zip(
                (1, 7, 13, 19, 25), digests, (0, 100, 200, 100, 0)
            )
        ],
        "distinct_geometry_states": 3,
        "rig_bone_count": 163, "rig_weight_sha256": "d" * 64,
        "rig_rest_sha256": "e" * 64,
        "blender_version": "5.3.0",
        "source_translation_ignored": True,
        "source_orientation_calibrated": False,
        "user_clip_evaluated_in_blender": True,
        "retargeting_verified": False,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }


class LocalBvhPreviewContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = ProjectStore(self.root / "hero")
        self.store.save(CharacterProject.new("Human"))
        staging = self.root / "synthetic-source"
        staging.mkdir()
        fake = staging / "synthetic.blend"
        fake.write_bytes(b"BLENDER" + b"unit-test-contract-only" * 150)
        master = stage_unverified_master(
            self.store, fake, authorized_source_root=staging
        )
        self.saved = master.project
        self.master = master.master_path
        self.source = self.root / "original-motion.bvh"
        fixture(self.source)
        self.blender = self.root / "fake-blender-not-launched"
        self.worker = self.root / "fake-bridge.py"
        self.blender.write_bytes(b"unit-test-only")
        self.worker.write_bytes(b"unit-test-only")
        self.policy = LicensePolicy(
            provider="original", license_name="self-created motion",
            source_uri="local://original-motion", reviewed=True,
            local_preview_allowed=True,
        )
        self.cancel = Event()
        self.calls = 0
        self.details = report(self.source)

    def runner(self, job, **kwargs):
        self.calls += 1
        target = self.store.root / ".ucc-jobs" / job.job_id
        target.mkdir(parents=True)
        for rel, src in kwargs["staged_inputs"].items():
            (target / rel).write_bytes(src.read_bytes())
        return JobResult(job.job_id, job.operation, "ok", dict(self.details)), target

    def invoke(self, **kwargs):
        params = dict(
            blender_exe=self.blender, worker_script=self.worker,
            source_bvh=self.source, permission=self.policy,
            expected_project_id=self.saved.project_id,
            expected_revision=self.saved.revision,
            expected_master_blend=self.saved.master_blend,
            cancel=self.cancel,
        )
        params.update(kwargs)
        with patch("ucc.jobs.bvh_clip_diagnostic.BlenderJobRunner.run",
                   side_effect=self.runner):
            return check_selected_bvh(self.store, **params)

    def test_qualified_preview_has_two_distinct_workers_and_no_master_write(self):
        original_project = self.store.file.read_bytes()
        original_master = self.master.read_bytes()
        original_source = self.source.read_bytes()
        done = self.invoke()
        self.assertEqual(self.calls, 2)
        self.assertNotEqual(*done.worker_job_ids)
        self.assertEqual(done.clip_sha256, sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(done.evidence["target_bone"], "head")
        self.assertFalse(done.retargeting_verified)
        self.assertEqual(self.store.file.read_bytes(), original_project)
        self.assertEqual(self.master.read_bytes(), original_master)
        self.assertEqual(self.source.read_bytes(), original_source)

    def test_permission_fails_closed_without_blender_worker(self):
        for policy in (
            LicensePolicy("Fab", "unreviewed", "https://example.com"),
            replace(self.policy, reviewed=False),
            replace(self.policy, local_preview_allowed=False),
            replace(self.policy, ue_only=True),
        ):
            with self.subTest(policy=policy), self.assertRaises(AssetPolicyError):
                self.invoke(permission=policy)
        self.assertEqual(self.calls, 0)

    def test_legacy_policy_json_still_denies_local_preview(self):
        legacy = self.policy.to_dict()
        legacy.pop("local_preview_allowed")
        previous = LicensePolicy.from_dict(legacy)
        self.assertFalse(previous.allow("local_preview")[0])

    def test_worker_must_not_claim_calibration_or_engine_export(self):
        for bad in (
            {"source_orientation_calibrated": True},
            {"retargeting_verified": True},
            {"source_master_saved": True},
            {"source_sha256": "0" * 64},
            {"sampled_frames": []},
            {"source_bone": "Hips"},
        ):
            with self.subTest(change=bad):
                altered = {**report(self.source), **bad}
                if bad.get("source_sha256"):
                    # A valid hash shape can pass schema; coordinator catches
                    # the byte-level mismatch with the selected original.
                    with self.assertRaises(BvhPreviewEvidenceError):
                        self.details = altered
                        self.invoke()
                else:
                    with self.assertRaises(BvhPreviewEvidenceError):
                        validate_local_bvh_report(altered)
                self.details = report(self.source)

    def test_unsafe_worker_options_and_stale_revision(self):
        with self.assertRaisesRegex(ValidationError, "needs input_project"):
            JobRequest.new("verify_local_bvh_motion")
        with self.assertRaisesRegex(ValidationError, "fixed"):
            JobRequest.new("verify_local_bvh_motion", input_project="candidate.blend",
                           options={"script": "no"})
        with self.assertRaises(ValidationError):
            JobRequest.new("verify_local_bvh_motion", input_project="../escape.blend")
        with self.assertRaises(ProjectConflict):
            self.invoke(expected_revision=99)
        self.assertEqual(self.calls, 0)

    def test_multibone_job_preserves_rights_and_checks_real_evidence_contract(self):
        # Synthetic-only multi-bone frame/rig report; independent real Blender
        # CI is what proves actual neck03 -> head deformation.
        data = report(self.source)
        data.update({
            "status": "REAL_MPFB_MULTIBONE_BVH_CHAIN_GEOMETRY_MEASURED",
            "axis_profile": "Y_UP_TO_Z_UP",
            "rest_direction_alignment_verified": True,
            "rest_length_scale_measured": True,
            "rest_scale_consistency_verified": False,
            "relative_rest_length_scale": .99,
            "bone_roll_calibrated": False,
            "mapped_bone_count": 2,
            "mapped_bones": [
                {"source": "neck03", "target": "neck03",
                 "parent": None, "weighted_vertices": 110,
                 "max_delta_degrees": 10.0, "rest_alignment_cos": None},
                {"source": "head", "target": "head",
                 "parent": "neck03", "weighted_vertices": 450,
                 "max_delta_degrees": 20.0, "rest_alignment_cos": .99},
            ],
            "per_bone_deformation": [
                {"bone": "neck03", "moved_vertices": 200,
                 "max_displacement_local": .02},
                {"bone": "head", "moved_vertices": 1000,
                 "max_displacement_local": .04},
            ],
            "keyframes_inserted": 50,
        })
        self.details = data
        result = self.invoke(multi_axis_profile="Y_UP_TO_Z_UP")
        self.assertEqual(result.evidence["mapped_bone_count"], 2)
        self.assertEqual(self.calls, 2)
        self.assertFalse(result.retargeting_verified)
        self.assertEqual(self.store.load(), self.saved)

    def test_multibone_rejects_unselected_axis_before_worker(self):
        with self.assertRaisesRegex(ValidationError, "up-axis"):
            self.invoke(multi_axis_profile="AUTO_GUESS")
        self.assertEqual(self.calls, 0)

    def test_calibration_requires_explicit_source_axis_before_work(self):
        with self.assertRaisesRegex(ValidationError, "requires explicit"):
            self.invoke(calibrate_rest_axes=True)
        with self.assertRaisesRegex(ValidationError, "up-axis"):
            self.invoke(multi_axis_profile="AUTO_GUESS", calibrate_rest_axes=True)
        self.assertEqual(self.calls, 0)

    def test_calibrated_chain_uses_licensed_immutable_double_worker(self):
        from test_calibrated_evidence import valid
        detail = valid()
        detail["source_sha256"] = sha256(self.source.read_bytes()).hexdigest()
        self.details = detail
        original = (
            self.store.file.read_bytes(),
            self.master.read_bytes(),
            self.source.read_bytes(),
        )
        result = self.invoke(
            multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True
        )
        self.assertEqual(self.calls, 2)
        self.assertEqual(result.evidence["status"],
                         "REAL_BVH_REST_AXES_CALIBRATED_MESH_MOTION")
        self.assertEqual(result.evidence["mapped_bone_count"], 2)
        self.assertFalse(result.retargeting_verified)
        self.assertEqual((
            self.store.file.read_bytes(), self.master.read_bytes(),
            self.source.read_bytes(),
        ), original)

    def test_cancellation_and_concurrent_source_change_discard_evidence(self):
        self.cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.invoke()
        self.cancel.clear()
        self.assertEqual(self.calls, 0)
        def mutate_source(job, **kwargs):
            result = self.runner(job, **kwargs)
            if self.calls == 1:
                self.source.write_bytes(self.source.read_bytes() + b"modified")
            return result
        with patch("ucc.jobs.bvh_clip_diagnostic.BlenderJobRunner.run",
                   side_effect=mutate_source):
            with self.assertRaises(ProjectStorageError):
                check_selected_bvh(
                    self.store, blender_exe=self.blender, worker_script=self.worker,
                    source_bvh=self.source, permission=self.policy,
                    expected_project_id=self.saved.project_id,
                    expected_revision=self.saved.revision,
                    expected_master_blend=self.saved.master_blend,
                )
        self.assertEqual(self.store.load(), self.saved)


if __name__ == "__main__":
    unittest.main()
