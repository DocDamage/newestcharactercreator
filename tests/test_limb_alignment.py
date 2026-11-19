"""Non-shipping motion math for the closed native preview adjustment."""
from copy import deepcopy
from math import radians, sin
import unittest

from fixtures.limb_alignment import synthetic_chains
from ucc.animations.native_math import pose_digest
from ucc.animations.native_preview_adjustments import (
    adjusted_native_preview_source,
    preview_adjustment_declarations,
    validate_preview_adjustments,
)
from ucc.core.errors import ValidationError


class LimbAlignmentTests(unittest.TestCase):
    def test_measured_axis_turns_preserve_every_joint_center_and_distal_pose(self):
        source, profile = synthetic_chains()
        previous = deepcopy(source)
        validate_preview_adjustments(profile)
        result = adjusted_native_preview_source(source, profile)
        self.assertEqual(source, previous)
        self.assertEqual(preview_adjustment_declarations(profile), {"limb_alignment": profile["limb_alignment"]})
        names = [bone["name"] for bone in source["bones"]]
        by_name = dict(zip(names, result["frames"][1]["poses"], strict=True))
        self.assertAlmostEqual(by_name["left_hip"][0], 1.)
        self.assertAlmostEqual(by_name["left_hip"][1], 0.)
        self.assertAlmostEqual(by_name["left_upper"][2], sin(radians(2.)))
        self.assertAlmostEqual(by_name["left_forearm"][2], sin(radians(1.)))
        self.assertAlmostEqual(result["frames"][2]["poses"][names.index("right_forearm")][2],
                               sin(radians(-1.5)))
        for frame, adjusted in zip(source["frames"], result["frames"], strict=True):
            for key in ("frame", "armature_world"):
                self.assertEqual(frame[key], adjusted[key])
            for name, before, after in zip(names, frame["poses"], adjusted["poses"], strict=True):
                self.assertEqual([before[i] for i in (3, 7, 11)], [after[i] for i in (3, 7, 11)])
                if name.split("_")[1] in {"knee", "foot", "hand", "finger"}:
                    self.assertEqual(before, after)
            self.assertEqual(adjusted["pose_sha256"], pose_digest(adjusted["armature_world"], adjusted["poses"]))

    def test_stale_clock_and_unmatched_or_branched_chains_fail_closed(self):
        source, profile = synthetic_chains()
        stale = {**source, "first_frame": 11}
        with self.assertRaisesRegex(ValidationError, "entire measured source clock"):
            adjusted_native_preview_source(stale, profile)
        bad_tip = deepcopy(profile)
        bad_tip["pairs"][3]["target_tip"] = "target_right_forearm"
        with self.assertRaisesRegex(ValidationError, "direct matching"):
            adjusted_native_preview_source(source, bad_tip)
        branch = {**source, "bones": [*source["bones"], {"name": "helper", "parent": "left_forearm"}]}
        with self.assertRaisesRegex(ValidationError, "direct matching"):
            adjusted_native_preview_source(branch, profile)

    def test_declarations_reject_mixed_policies_and_discontinuous_or_ambiguous_schedules(self):
        for label in ("overlap", "neutral", "unknown", "duplicate", "upper_jump", "forearm_jump"):
            _, profile = synthetic_chains()
            rule = profile["limb_alignment"]
            if label == "overlap":
                profile["forearm_roll"] = {}
            elif label == "neutral":
                del profile["mesh_strain_reference"]
            elif label == "unknown":
                rule["another_axis"] = "Z"
            elif label == "duplicate":
                rule["upper_arm_turns"] *= 2
            elif label == "upper_jump":
                rule["upper_arm_turns"][0]["angle_degrees"] = 4.5
            else:
                rule["forearm_angle_tenths"]["left"][2] = 26
            with self.subTest(label=label), self.assertRaises(ValidationError):
                validate_preview_adjustments(profile)


if __name__ == "__main__":
    unittest.main()
