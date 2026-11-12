"""Original, synthetic BVH parent/rest-axis tests — not real Blender proof."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from blender_bridge.bvh_motion import LocalBvhError, read_local_bvh
from blender_bridge.bvh_multichain import MultiBvhError, select_explicit_chain


def write_two_bone_bvh(path: Path, *, offset: str = "0 0.033 0.017",
                       order: str = "Xrotation Yrotation Zrotation") -> None:
    hierarchy = (
        "HIERARCHY\nROOT neck03\n{\nOFFSET 0 0 0\n"
        "CHANNELS 3 Xrotation Yrotation Zrotation\n"
        f"JOINT head\n{{\nOFFSET {offset}\n"
        f"CHANNELS 3 {order}\n"
        "End Site\n{\nOFFSET 0 0.1 0\n}\n}\n}\n"
        "MOTION\nFrames: 25\nFrame Time: 0.041666667\n"
    )
    values = [
        f"{10 * math.sin(math.pi * i / 24):.7f} 0 0 "
        f"{20 * math.sin(math.pi * i / 24):.7f} 0 0"
        for i in range(25)
    ]
    path.write_text(hierarchy + "\n".join(values) + "\n", encoding="utf-8")


class FakeRig:
    def __init__(self):
        neck_parent = SimpleNamespace(name="neck02", parent=None,
                                      head_local=(0, 0, -.05), use_deform=True)
        neck = SimpleNamespace(name="neck03", parent=neck_parent,
                               head_local=(0, 0, 0), use_deform=True)
        head = SimpleNamespace(name="head", parent=neck,
                               head_local=(0, -.017, .033), use_deform=True)
        self.data = SimpleNamespace(bones=[neck_parent, neck, head])
        self.pose = SimpleNamespace(bones=[
            SimpleNamespace(name=n) for n in ("neck02", "neck03", "head")
        ])


class MultiBoneFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name) / "original-two-bones.bvh"
        write_two_bone_bvh(self.source)
        self.motion = read_local_bvh(self.source)
        self.rig = FakeRig()
        groups = [SimpleNamespace(index=0, name="neck03"),
                  SimpleNamespace(index=1, name="head")]
        vertices = [
            SimpleNamespace(groups=[
                SimpleNamespace(group=i % 2, weight=1.0)
            ]) for i in range(240)
        ]
        self.human = SimpleNamespace(vertex_groups=groups, data=SimpleNamespace(vertices=vertices))

    def test_actual_bvh_parents_and_rest_offsets_are_parsed(self):
        self.assertEqual(self.motion.source_bones, ("neck03", "head"))
        self.assertEqual(self.motion.parents, {"neck03": None, "head": "neck03"})
        self.assertEqual(self.motion.offsets["head"], (0.0, .033, .017))
        self.assertEqual(self.motion.end_site_offsets["head"], (0.0, 0.1, 0.0))
        self.assertEqual(self.motion.channel_orders["head"], (
            "Xrotation", "Yrotation", "Zrotation",
        ))
        result, evidence = select_explicit_chain(
            self.motion, self.human, self.rig, "Y_UP_TO_Z_UP",
        )
        self.assertEqual([r["target"] for r in result], ["neck03", "head"])
        self.assertEqual(result[0]["weighted_vertices"], 120)
        self.assertEqual(result[1]["weighted_vertices"], 120)
        self.assertGreater(result[1]["rest_alignment_cos"], .99)
        self.assertTrue(evidence["rest_length_scale_measured"])
        self.assertFalse(evidence["rest_scale_consistency_verified"])
        self.assertFalse(evidence["bone_roll_calibrated"])

    def test_explicit_wrong_axis_fails_without_fallback(self):
        with self.assertRaisesRegex(MultiBvhError, "does not align"):
            select_explicit_chain(
                self.motion, self.human, self.rig, "Z_UP_IDENTITY",
            )
        with self.assertRaisesRegex(MultiBvhError, "explicit"):
            select_explicit_chain(self.motion, self.human, self.rig, "")

    def test_reject_wrong_parent_or_missing_skin_weights(self):
        self.rig.data.bones[2].parent = self.rig.data.bones[0]
        with self.assertRaisesRegex(MultiBvhError, "parents differ"):
            select_explicit_chain(self.motion, self.human, self.rig, "Y_UP_TO_Z_UP")
        self.rig = FakeRig()
        self.human.vertex_groups[1].name = "other"
        with self.assertRaisesRegex(MultiBvhError, "weighted"):
            select_explicit_chain(self.motion, self.human, self.rig, "Y_UP_TO_Z_UP")

    def test_reject_invalid_bvh_rest_offsets_and_rotation_order(self):
        write_two_bone_bvh(self.source, offset="0 NaN 1")
        with self.assertRaisesRegex(LocalBvhError, "Non-finite"):
            read_local_bvh(self.source)
        write_two_bone_bvh(self.source, offset="0 0 0")
        with self.assertRaisesRegex(MultiBvhError, "rest-direction"):
            select_explicit_chain(
                read_local_bvh(self.source), self.human, self.rig, "Y_UP_TO_Z_UP",
            )
        write_two_bone_bvh(self.source, order="Zrotation Xrotation Yrotation")
        with self.assertRaisesRegex(MultiBvhError, "XYZ"):
            select_explicit_chain(
                read_local_bvh(self.source), self.human, self.rig, "Y_UP_TO_Z_UP",
            )

    def test_reject_duplicate_or_nonfinite_terminal_end_site_offset(self):
        original = self.source.read_text(encoding="utf-8")
        broken = original.replace(
            "End Site\n{\nOFFSET 0 0.1 0",
            "End Site\n{\nOFFSET 0 NaN 0",
        )
        self.source.write_text(broken, encoding="utf-8")
        with self.assertRaisesRegex(LocalBvhError, "Non-finite"):
            read_local_bvh(self.source)
        self.source.write_text(original.replace(
            "End Site\n{\nOFFSET 0 0.1 0",
            "End Site\n{\nOFFSET 0 0.1 0\nOFFSET 0 0.1 0",
        ), encoding="utf-8")
        with self.assertRaisesRegex(LocalBvhError, "Duplicate terminal"):
            read_local_bvh(self.source)

    def test_manual_reviewed_three_bone_names_preserve_parent_and_skin_evidence(self):
        source = self.source.with_name("ci-only-review-roles.bvh")
        header = (
            "HIERARCHY\\nROOT SourceNeck02\\n{\\nOFFSET 0 0 0\\n"
            "CHANNELS 3 Xrotation Yrotation Zrotation\\n"
            "JOINT SourceNeck03\\n{\\nOFFSET 0 0.05 0\\n"
            "CHANNELS 3 Xrotation Yrotation Zrotation\\n"
            "JOINT SourceHead\\n{\\nOFFSET 0 0.033 0.017\\n"
            "CHANNELS 3 Xrotation Yrotation Zrotation\\n"
            "End Site\\n{\\nOFFSET 0 0.1 0\\n}\\n}\\n}\\n}\\n"
            "MOTION\\nFrames: 25\\nFrame Time: 0.041666667\\n"
        )
        rows = [
            " ".join(f"{x * math.sin(math.pi * i / 24):.7f} 0 0"
                     for x in (9, 14, 19))
            for i in range(25)
        ]
        source.write_text(header + "\\n".join(rows) + "\\n", encoding="utf-8")
        motion = read_local_bvh(source)
        mapping = [
            {"source": "SourceNeck02", "target": "neck02"},
            {"source": "SourceNeck03", "target": "neck03"},
            {"source": "SourceHead", "target": "head"},
        ]
        groups = [SimpleNamespace(index=i, name=name) for i, name in
                  enumerate(("neck02", "neck03", "head"))]
        self.human.vertex_groups = groups
        self.human.data.vertices = [
            SimpleNamespace(groups=[SimpleNamespace(group=i % 3, weight=1.0)])
            for i in range(300)
        ]
        mapped, details = select_explicit_chain(
            motion, self.human, self.rig, "Y_UP_TO_Z_UP", mapping,
        )
        self.assertEqual([m["target"] for m in mapped], ["neck02", "neck03", "head"])
        self.assertEqual(mapped[2]["target_parent"], "neck03")
        self.assertTrue(details["rest_scale_consistency_verified"])
        self.assertEqual(details["mapping_method"], "EXPLICIT_USER_REVIEWED_PAIRS")
        self.rig.data.bones[2].parent = self.rig.data.bones[0]
        with self.assertRaisesRegex(MultiBvhError, "parents differ"):
            select_explicit_chain(motion, self.human, self.rig, "Y_UP_TO_Z_UP", mapping)

    def test_reject_inadequate_source_chains(self):
        one = self.source.with_name("one.bvh")
        one.write_text(
            "HIERARCHY\nROOT head\n{\nOFFSET 0 0 0\n"
            "CHANNELS 3 Xrotation Yrotation Zrotation\n"
            "End Site\n{\nOFFSET 0 1 0\n}\n}\n"
            "MOTION\nFrames: 5\nFrame Time: 0.041666667\n"
            "0 0 0\n10 0 0\n20 0 0\n10 0 0\n0 0 0\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MultiBvhError, "2–4"):
            select_explicit_chain(
                read_local_bvh(one), self.human, self.rig, "Y_UP_TO_Z_UP",
            )


if __name__ == "__main__":
    unittest.main()
