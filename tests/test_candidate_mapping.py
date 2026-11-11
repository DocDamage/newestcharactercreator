"""Candidate mapping is metadata only; these tests do not run Blender or retarget motion."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.animations.candidate_mapping import (
    BoneMappingError, PROFILES, REQUIRED_ROLES, infer_profile, propose_mapping,
)


def mixamo_bones():
    return tuple(PROFILES["mixamo"].values())


def unreal_bones(profile="unreal_ue5"):
    return tuple(PROFILES[profile].values())


class CandidateMappingTests(unittest.TestCase):
    def test_infers_mixamo_and_unreal5_from_realistic_bone_names(self):
        s = [f"mixamorig:{n}" for n in mixamo_bones()]
        t = unreal_bones()
        self.assertEqual(infer_profile(s), "mixamo")
        self.assertEqual(infer_profile(t), "unreal_ue5")
        report = propose_mapping(s, t).to_dict()
        self.assertEqual(report["source_profile"], "mixamo")
        self.assertEqual(report["target_profile"], "unreal_ue5")
        self.assertFalse(report["retargeted"])
        self.assertFalse(report["engine_validated"])
        self.assertFalse(report["can_execute_without_manual_review"])
        self.assertEqual(report["required_roles_unmapped"], [])
        self.assertGreaterEqual(report["mapped_role_count"], len(REQUIRED_ROLES))

    def test_mixamo_unprefixed(self):
        report = propose_mapping(mixamo_bones(), unreal_bones())
        self.assertIn("hand.L", {x.role for x in report.candidates})
        hand = next(x for x in report.candidates if x.role == "hand.L")
        self.assertEqual((hand.source, hand.target), ("LeftHand", "hand_l"))

    def test_ue4_to_ue5_spine_variation(self):
        source = unreal_bones("unreal_ue4")
        target = unreal_bones("unreal_ue5")
        report = propose_mapping(source, target)
        self.assertEqual(report.source_profile, "unreal_ue4")
        self.assertEqual(report.target_profile, "unreal_ue5")
        upper = next(x for x in report.candidates if x.role == "spine.upper")
        self.assertEqual((upper.source, upper.target), ("spine_03", "spine_05"))

    def test_mirror_roles_never_swapped(self):
        report = propose_mapping(mixamo_bones(), unreal_bones())
        items = {x.role:x for x in report.candidates}
        self.assertEqual(items["upper_arm.L"].source, "LeftArm")
        self.assertEqual(items["upper_arm.L"].target, "upperarm_l")
        self.assertEqual(items["upper_arm.R"].source, "RightArm")
        self.assertEqual(items["upper_arm.R"].target, "upperarm_r")

    def test_sparse_skeleton_does_not_invent_roles(self):
        report = propose_mapping(["Hips", "Head", "LeftArm"], ["pelvis", "head", "upperarm_l"])
        self.assertEqual(report.candidates, ())
        self.assertEqual(len(report.required_roles_unmapped), len(REQUIRED_ROLES))
        self.assertTrue(any("unidentified" in w for w in report.warnings))

    def test_profile_hint_explicit_but_no_hallucination(self):
        report = propose_mapping(["Hips", "Head"], ["pelvis", "head"],
                                 source_hint="mixamo", target_hint="unreal_ue4")
        self.assertEqual({x.role for x in report.candidates}, {"hips", "head"})
        self.assertTrue(report.required_roles_unmapped)

    def test_override_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(BoneMappingError, "Unknown rig profile"):
            propose_mapping(["Hips"], ["pelvis"], source_hint="rigify")

    def test_duplicate_bone_names_fail_even_case_insensitive(self):
        with self.assertRaisesRegex(BoneMappingError, "Duplicate"):
            propose_mapping(["LeftArm", "leftarm"], ["upperarm_l"])

    def test_duplicate_mixamo_normalized_alias_fails(self):
        # This array contains two actual different names that normalize to one bone.
        source = list(mixamo_bones()) + ["mixamorig:LeftArm"]
        with self.assertRaisesRegex(BoneMappingError, "Ambiguous"):
            propose_mapping(source, unreal_bones())

    def test_reject_pathlike_and_control_names(self):
        for bad in ["../../Hips", "bad\\name", "Hips\n", ""]:
            with self.subTest(bad=repr(bad)), self.assertRaises(BoneMappingError):
                propose_mapping([bad], ["pelvis"])

    def test_deterministic_roles_not_input_order(self):
        s, t = list(mixamo_bones()), list(unreal_bones())
        report1 = propose_mapping(s, t)
        report2 = propose_mapping(list(reversed(s)), list(reversed(t)))
        self.assertEqual([x.to_dict() for x in report1.candidates],
                         [x.to_dict() for x in report2.candidates])

    def test_reports_no_matching_profile_for_mixed_or_custom(self):
        report = propose_mapping(["DEF-upper_arm.L", "DEF-hand.L", "ORG-spine"],
                                 ["pelvis", "head", "upperarm_l"])
        self.assertIsNone(report.source_profile)
        self.assertEqual(report.candidates, ())
        self.assertFalse(report.to_dict()["can_execute_without_manual_review"])

    def test_required_semantics_are_core_body_not_toes(self):
        self.assertIn("upper_arm.L", REQUIRED_ROLES)
        self.assertIn("foot.R", REQUIRED_ROLES)
        self.assertNotIn("toe.L", REQUIRED_ROLES)
        self.assertNotIn("root", REQUIRED_ROLES)

    def test_mismatched_target_bones_remain_ignored(self):
        report = propose_mapping(mixamo_bones(), list(unreal_bones()) + ["ik_hand_gun"])
        self.assertIn("ik_hand_gun", report.ignored_target_bones)

    def test_fingerprint_is_full_source_inventory(self):
        a = propose_mapping(mixamo_bones(), unreal_bones())
        b = propose_mapping(list(mixamo_bones()) + ["twist_unknown"], unreal_bones())
        self.assertNotEqual(a.source_fingerprint, b.source_fingerprint)
        self.assertEqual([x.to_dict() for x in a.candidates], [x.to_dict() for x in b.candidates])


if __name__ == '__main__':
    unittest.main()
