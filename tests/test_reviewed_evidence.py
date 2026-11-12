"""Synthetic validation contracts only; actual MPFB evidence is in Blender CI."""
from __future__ import annotations

from copy import deepcopy
import unittest

from test_calibrated_evidence import valid
from ucc.animations.review_mapping import review_mapping_sha256
from ucc.jobs.reviewed_evidence import (
    ReviewedEvidenceError, compare_reviewed_evidence, validate_reviewed_evidence,
)


PAIRS = [
    {"source": "UCC_Source_Neck02", "target": "neck02"},
    {"source": "UCC_Source_Neck03", "target": "neck03"},
    {"source": "UCC_Source_Head", "target": "head"},
]


def reviewed() -> dict:
    v = valid()
    v["status"] = "REAL_REVIEWED_BVH_FULL_TIMELINE_MOTION"
    v["mapped_bone_count"] = 3
    v["rest_landmark_count"] = 3
    v["rest_residual_degrees"] = [.02, .03, .01]
    v["max_rest_residual_degrees"] = .03
    v["mapped_bones"] = [
        {"source": x["source"], "target": x["target"],
         "parent": PAIRS[i-1]["source"] if i else None,
         "target_parent": PAIRS[i-1]["target"] if i else "neck01"}
        for i, x in enumerate(PAIRS)
    ]
    v["per_bone_deformation"] = [
        {"bone": x["target"], "moved_vertices": 150,
         "max_displacement_local": .03} for x in PAIRS
    ]
    v["local_axis_proofs"] = [
        {"source": x["source"], "target": x["target"],
         "source_axes_to_target_sha256": "e" * 64,
         "target_rest_matrix_sha256": "b" * 64,
         "calibrated_test_delta_sha256": "c" * 64,
         "measured_rest_raw_determinant": 1.000014475,
         "bounded_rest_projection_delta": .00002}
        for x in PAIRS
    ]
    v["keyframes_inserted"] = 25 * 3
    samples = {x["frame"]: x for x in v["sampled_frames"]}
    v["full_timeline_frames"] = [
        {"frame": i, "evaluated_sha256": samples[i]["evaluated_sha256"]
         if i in samples else "b" * 64,
         "moved_vertices": samples[i]["moved_vertices"]
         if i in samples else 100,
         "max_displacement_local": samples[i]["max_displacement_local"]
         if i in samples else .05,
         "adjacent_max_displacement_local": 0.0 if i == 1 else .03}
        for i in range(1, 26)
    ]
    v["model_baseline_diagonal_local"] = 2.0
    v["max_adjacent_mesh_step_local"] = .03
    v["reviewed_mapping_sha256"] = review_mapping_sha256(PAIRS)
    v["explicit_mapping_reviewed_by_user"] = True
    v["max_bone_quaternion_step_degrees"] = {x["target"]: 2.0 for x in PAIRS}
    v["visual_review_blend"] = {
        "name": "review_motion.blend", "sha256": "d" * 64, "bytes": 500000,
    }
    v["visual_review_artifact_created"] = True
    v["joint_twist_visual_quality_verified"] = False
    return v


class ReviewedEvidenceContracts(unittest.TestCase):
    def test_three_independently_mapped_bones_and_all_frames(self):
        self.assertEqual(
            validate_reviewed_evidence(reviewed(), "Y_UP_TO_Z_UP", PAIRS)["mapped_bone_count"], 3
        )
        self.assertEqual(
            compare_reviewed_evidence(reviewed(), reviewed(), "Y_UP_TO_Z_UP", PAIRS)
            ["visual_review_blend"]["name"], "review_motion.blend"
        )

    def test_mapping_hierarchy_and_direction_cannot_be_faked(self):
        for key, value in (
            ("reviewed_mapping_sha256", "0" * 64),
            ("explicit_mapping_reviewed_by_user", False),
            ("visual_review_artifact_created", False),
            ("joint_twist_visual_quality_verified", True),
            ("animation_visual_quality_verified", True),
            ("retargeting_verified", True),
        ):
            with self.subTest(key=key), self.assertRaises(Exception):
                validate_reviewed_evidence({**reviewed(), key: value}, "Y_UP_TO_Z_UP", PAIRS)
        data = reviewed()
        data["mapped_bones"][1]["target_parent"] = "wrong"
        with self.assertRaisesRegex(ReviewedEvidenceError, "parent hierarchy"):
            validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS)

    def test_full_frame_movement_hash_bounds_and_review_file_required(self):
        for field, altered in (
            ("model_baseline_diagonal_local", .0),
            ("max_adjacent_mesh_step_local", 100.0),
            ("visual_review_blend", {"name": "../master.blend", "sha256": "e" * 64,
                                     "bytes": 500000}),
            ("max_bone_quaternion_step_degrees", {"head": 100.0}),
        ):
            with self.subTest(field=field), self.assertRaises(ReviewedEvidenceError):
                validate_reviewed_evidence({**reviewed(), field: altered},
                                           "Y_UP_TO_Z_UP", PAIRS)
        data = reviewed()
        data["full_timeline_frames"][6]["evaluated_sha256"] = "0" * 64
        with self.assertRaisesRegex(ReviewedEvidenceError, "disagree"):
            validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS)

    def test_two_blender_processes_must_agree_on_all_25_frame_hashes(self):
        data = deepcopy(reviewed())
        data["full_timeline_frames"][9]["evaluated_sha256"] = "0" * 64
        with self.assertRaisesRegex(ReviewedEvidenceError, "full-frame"):
            compare_reviewed_evidence(reviewed(), data, "Y_UP_TO_Z_UP", PAIRS)


if __name__ == "__main__":
    unittest.main()
