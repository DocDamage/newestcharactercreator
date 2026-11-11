"""Synthetic-only MPFB macro morphology contract tests.

These stubs are not evidence of an actual Blender deformation; Linux integration
CI separately evaluates a real MPFB generated and reopened body mesh.
"""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_bridge.morphs import (
    MorphEvidenceError, build_macro_info, check_macro_values, inspect_applied_macro,
)


class FakeEvaluated:
    def __init__(self):
        self.cleared = False
        self.mesh = SimpleNamespace(
            vertices=[
                SimpleNamespace(co=(float(i) / 100, 1.0, -0.1)) for i in range(150)
            ]
        )

    def to_mesh(self):
        return self.mesh

    def to_mesh_clear(self):
        self.cleared = True


class FakeHuman:
    type = "MESH"

    def __init__(self):
        self.data = SimpleNamespace(
            vertices=[None] * 19000,
            shape_keys=SimpleNamespace(key_blocks=[
                SimpleNamespace(name="Basis", value=0),
                SimpleNamespace(name="$md-universal", value=.6),
            ]),
        )
        self.evaluated = FakeEvaluated()

    def evaluated_get(self, depsgraph):
        return self.evaluated


class MorphsContractTests(unittest.TestCase):
    def setUp(self):
        self.human = FakeHuman()
        self.values = {"height": .85, "muscle": .2, "weight": .75}
        self.target = SimpleNamespace(
            get_default_macro_info_dict=lambda: {
                "height": .5, "muscle": .5, "weight": .5, "age": .5,
                "race": {"asian": .33, "caucasian": .33, "african": .33},
            },
            get_macro_info_dict_from_basemesh=lambda _: dict(self.values),
        )
        self.bpy = SimpleNamespace(
            context=SimpleNamespace(
                view_layer=SimpleNamespace(update=lambda: None),
                evaluated_depsgraph_get=lambda: object(),
            ),
        )

    def test_build_preserves_other_mpfb_defaults(self):
        macro = build_macro_info(self.target, self.values)
        self.assertEqual(macro["height"], .85)
        self.assertEqual(macro["weight"], .75)
        self.assertEqual(macro["age"], .5)
        self.assertEqual(macro["race"]["asian"], .33)

    def test_real_evaluation_code_hashes_vertex_coordinates(self):
        report = inspect_applied_macro(
            self.bpy, self.human, self.target, self.values
        )
        self.assertTrue(report["macro_shape_evaluated"])
        self.assertEqual(report["macro_evaluated_vertices"], 150)
        self.assertEqual(report["macro_active_shape_keys"], 1)
        self.assertEqual(len(report["macro_evaluated_sha256"]), 64)
        self.assertTrue(self.human.evaluated.cleared)
        self.assertFalse(report["visual_deformation_verified"])

    def test_rejects_invalid_morph_requests(self):
        for values in (
            {}, {"height": .2}, {**self.values, "age": .2},
            {**self.values, "weight": True},
            {**self.values, "height": float("nan")},
            {**self.values, "height": 1.01},
        ):
            with self.subTest(values=values), self.assertRaises(MorphEvidenceError):
                check_macro_values(values)

    def test_rejects_wrong_targetservice_read_back(self):
        target = SimpleNamespace(
            get_macro_info_dict_from_basemesh=lambda _: {
                **self.values, "weight": .5
            }
        )
        with self.assertRaisesRegex(MorphEvidenceError, "differed"):
            inspect_applied_macro(self.bpy, self.human, target, self.values)

    def test_rejects_no_active_shape_keys(self):
        self.human.data.shape_keys.key_blocks[1].value = 0
        with self.assertRaisesRegex(MorphEvidenceError, "active shape keys"):
            inspect_applied_macro(self.bpy, self.human, self.target, self.values)
        self.assertTrue(self.human.evaluated.cleared)


if __name__ == "__main__":
    unittest.main()
