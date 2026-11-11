"""Synthetic-only multi-bone evidence contracts; actual Blender CI is separate."""
from __future__ import annotations

import unittest

from ucc.jobs.multibone_evidence import (
    MultiBoneEvidenceError, compare_multibone_evidence, validate_multibone_evidence,
)


def valid_report() -> dict:
    hashes = ["a", "b", "c", "b", "a"]
    return {
        "status": "REAL_MPFB_MULTIBONE_BVH_CHAIN_GEOMETRY_MEASURED",
        "axis_profile": "Y_UP_TO_Z_UP",
        "rest_direction_alignment_verified": True,
        "rest_scale_consistency_verified": True,
        "relative_rest_length_scale": .99,
        "bone_roll_calibrated": False,
        "source_orientation_calibrated": False,
        "retargeting_verified": False,
        "source_sha256": "f" * 64,
        "source_frame_count": 25,
        "source_frame_time": .041666667,
        "mapped_bone_count": 2,
        "mapped_bones": [
            {"source": "neck03", "target": "neck03", "parent": None,
             "weighted_vertices": 120, "max_delta_degrees": 10.0,
             "rest_alignment_cos": None},
            {"source": "head", "target": "head", "parent": "neck03",
             "weighted_vertices": 200, "max_delta_degrees": 20.0,
             "rest_alignment_cos": .993},
        ],
        "per_bone_deformation": [
            {"bone": "neck03", "moved_vertices": 120, "max_displacement_local": .02},
            {"bone": "head", "moved_vertices": 500, "max_displacement_local": .05},
        ],
        "frame_sample_count": 5,
        "sampled_frames": [
            {"frame": index, "evaluated_sha256": digest * 64,
             "evaluated_vertex_count": 19158,
             "moved_vertices": moved,
             "max_displacement_local": .04 if moved else 0.0}
            for index, digest, moved in zip((1, 7, 13, 19, 25),
                                            hashes, (0, 450, 800, 450, 0))
        ],
        "distinct_geometry_states": 3,
        "keyframes_inserted": 50,
        "rig_bone_count": 163,
        "rig_weight_sha256": "c" * 64,
        "rig_rest_sha256": "d" * 64,
        "blender_version": "5.3.0",
        "source_translation_ignored": True,
        "user_clip_evaluated_in_blender": True,
        "animation_visual_quality_verified": False,
        "engine_import_verified": False,
        "source_master_saved": False,
        "source_bvh_modified": False,
    }


class MultiBoneEvidenceTests(unittest.TestCase):
    def test_valid_real_report_shape_requires_independently_moving_bones(self):
        report = valid_report()
        self.assertEqual(validate_multibone_evidence(
            report, axis_profile="Y_UP_TO_Z_UP"
        ), report)
        self.assertEqual(compare_multibone_evidence(
            report, dict(report), "Y_UP_TO_Z_UP"
        )["mapped_bone_count"], 2)

    def test_reject_fake_mapping_or_unproven_calibration(self):
        for change in (
            {"axis_profile": "Z_UP_IDENTITY"},
            {"bone_roll_calibrated": True},
            {"retargeting_verified": True},
            {"rest_direction_alignment_verified": False},
            {"source_master_saved": True},
            {"mapped_bone_count": 3},
            {"mapped_bones": valid_report()["mapped_bones"][:1]},
            {"per_bone_deformation": valid_report()["per_bone_deformation"][:1]},
            {"keyframes_inserted": 25},
            {"source_orientation_calibrated": True},
            {"source_sha256": "no-hash"},
            {"distinct_geometry_states": 1},
            {"sampled_frames": []},
        ):
            with self.subTest(change=change), self.assertRaises(MultiBoneEvidenceError):
                validate_multibone_evidence(
                    {**valid_report(), **change}, axis_profile="Y_UP_TO_Z_UP",
                )

    def test_reject_unlinked_child_or_missing_per_bone_movement(self):
        for key, change in (
            ("mapped_bones", [{"source": "neck03", "target": "neck03",
                               "weighted_vertices": 120, "max_delta_degrees": 10,
                               "parent": None, "rest_alignment_cos": None},
                              {"source": "head", "target": "head",
                               "weighted_vertices": 200, "max_delta_degrees": 20,
                               "parent": "spine", "rest_alignment_cos": .999}]),
            ("per_bone_deformation", [
                {"bone": "neck03", "moved_vertices": 0, "max_displacement_local": 0},
                {"bone": "head", "moved_vertices": 500, "max_displacement_local": .04},
            ]),
        ):
            with self.subTest(key=key), self.assertRaises(MultiBoneEvidenceError):
                validate_multibone_evidence(
                    {**valid_report(), key: change}, axis_profile="Y_UP_TO_Z_UP",
                )

    def test_double_blender_processes_must_agree(self):
        updated = valid_report()
        samples = [dict(x) for x in updated["sampled_frames"]]
        samples[1]["evaluated_sha256"] = "e" * 64
        updated["sampled_frames"] = samples
        with self.assertRaisesRegex(MultiBoneEvidenceError, "disagreed"):
            compare_multibone_evidence(valid_report(), updated, "Y_UP_TO_Z_UP")


if __name__ == "__main__":
    unittest.main()
