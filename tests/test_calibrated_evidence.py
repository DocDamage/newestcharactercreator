"""Synthetic proof-contract tests; real MPFB is verified only by Blender CI."""
from __future__ import annotations

import unittest

from ucc.jobs.calibrated_evidence import (
    CalibratedEvidenceError, compare_calibrated_evidence,
    validate_calibrated_evidence,
)


def valid() -> dict:
    return {
        "status": "REAL_BVH_REST_AXES_CALIBRATED_MESH_MOTION",
        "source_sha256": "f" * 64,
        "source_frame_count": 25,
        "source_frame_time": .041666667,
        "axis_profile": "Y_UP_TO_Z_UP",
        "source_to_target_axes_sha256": "e" * 64,
        "rest_landmark_count": 2,
        "rest_reference_pair": [0, 1],
        "rest_residual_degrees": [0.01, 0.3],
        "max_rest_residual_degrees": 0.3,
        "rest_axes_calibrated": True,
        "raw_rest_rotation_projected_with_bound": True,
        "maximum_rest_projection_delta": 0.00002,
        "bone_roll_independently_verified": False,
        "mapped_bone_count": 2,
        "mapped_bones": [
            {"source": "neck03", "target": "neck03", "parent": None},
            {"source": "head", "target": "head", "parent": "neck03"},
        ],
        "per_bone_deformation": [
            {"bone": "neck03", "moved_vertices": 400,
             "max_displacement_local": .025},
            {"bone": "head", "moved_vertices": 150,
             "max_displacement_local": .04},
        ],
        "local_axis_proofs": [
            {"source": src, "target": src,
             "source_axes_to_target_sha256": "e" * 64,
             "target_rest_matrix_sha256": matrix * 64,
             "calibrated_test_delta_sha256": delta * 64,
             "measured_rest_raw_determinant": 1.000014475,
             "bounded_rest_projection_delta": 0.00002}
            for src, matrix, delta in (
                ("neck03", "b", "c"), ("head", "a", "d")
            )
        ],
        "sampled_frames": [
            {"frame": frame, "evaluated_sha256": state * 64,
             "evaluated_vertex_count": 19158, "moved_vertices": count,
             "max_displacement_local": .05 if count else 0.0}
            for frame, state, count in (
                (1, "a", 0), (7, "b", 100), (13, "c", 500),
                (19, "b", 100), (25, "a", 0)
            )
        ],
        "distinct_geometry_states": 3,
        "keyframes_inserted": 50,
        "real_quaternion_action_inserted": True,
        "rig_bone_count": 163,
        "rig_weight_sha256": "4" * 64,
        "rig_rest_sha256": "5" * 64,
        "blender_version": "5.3.0",
        "source_translation_ignored": True,
        "user_clip_evaluated_in_blender": True,
        "retargeting_verified": False,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }


class CalibratedEvidenceContracts(unittest.TestCase):
    def test_valid_shape_requires_two_source_anatomical_references(self):
        sample = valid()
        self.assertEqual(validate_calibrated_evidence(sample, "Y_UP_TO_Z_UP"), sample)
        self.assertEqual(compare_calibrated_evidence(
            sample, dict(sample), "Y_UP_TO_Z_UP"
        )["mapped_bone_count"], 2)

    def test_wrong_axis_poor_fit_and_false_retarget_claim_rejected(self):
        for key, new in (
            ("axis_profile", "Z_UP_IDENTITY"),
            ("rest_axes_calibrated", False),
            ("raw_rest_rotation_projected_with_bound", False),
            ("maximum_rest_projection_delta", 0.01),
            ("bone_roll_independently_verified", True),
            ("retargeting_verified", True),
            ("animation_visual_quality_verified", True),
            ("source_master_saved", True),
            ("rest_landmark_count", 1),
            ("rest_reference_pair", [0, 0]),
            ("rest_residual_degrees", [0.0, 8.0]),
            ("source_to_target_axes_sha256", "invalid"),
            ("mapped_bone_count", 3),
            ("keyframes_inserted", 25),
            ("sampled_frames", []),
            ("real_quaternion_action_inserted", False),
        ):
            with self.subTest(key=key), self.assertRaises(CalibratedEvidenceError):
                validate_calibrated_evidence({**valid(), key: new}, "Y_UP_TO_Z_UP")

    def test_independent_bone_skinning_and_parent_proof_are_mandatory(self):
        for key, change in (
            ("per_bone_deformation", [
                {"bone": "neck03", "moved_vertices": 0,
                 "max_displacement_local": 0.0},
                valid()["per_bone_deformation"][1],
            ]),
            ("mapped_bones", [
                valid()["mapped_bones"][0],
                {"source": "head", "target": "head", "parent": "other"},
            ]),
            ("local_axis_proofs", [
                {"source": "neck03", "target": "neck03",
                 "source_axes_to_target_sha256": "e" * 64,
                 "target_rest_matrix_sha256": "b" * 64,
                 "calibrated_test_delta_sha256": "c" * 64,
                 "measured_rest_raw_determinant": 1.0,
                 "bounded_rest_projection_delta": 0.00002},
                {"source": "head", "target": "head",
                 "source_axes_to_target_sha256": "0" * 64,
                 "target_rest_matrix_sha256": "a" * 64,
                 "calibrated_test_delta_sha256": "d" * 64,
                 "measured_rest_raw_determinant": 1.0,
                 "bounded_rest_projection_delta": 0.00002},
            ]),
        ):
            with self.subTest(key=key), self.assertRaises(CalibratedEvidenceError):
                validate_calibrated_evidence(
                    {**valid(), key: change}, "Y_UP_TO_Z_UP"
                )

    def test_two_workers_disagree_on_real_frame_sha(self):
        differing = valid()
        samples = [dict(row) for row in differing["sampled_frames"]]
        samples[1]["evaluated_sha256"] = "9" * 64
        differing["sampled_frames"] = samples
        differing["distinct_geometry_states"] = 4
        with self.assertRaisesRegex(CalibratedEvidenceError, "disagreed"):
            compare_calibrated_evidence(valid(), differing, "Y_UP_TO_Z_UP")


if __name__ == "__main__":
    unittest.main()
