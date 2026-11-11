"""Synthetic bpy refit unit tests. Real Blender verification runs in CI separately."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

from blender_bridge.refit_revision import (
    RefitError, apply_body_revision, rig_fingerprint,
)


def armature():
    bones = [
        SimpleNamespace(name=f"Bone{i}", head_local=(0.0, 0.0, 0.0),
                        tail_local=(0.0, 0.1 + i * .01, 0.0))
        for i in range(6)
    ]
    return SimpleNamespace(type="ARMATURE", data=SimpleNamespace(bones=bones))


def human_with_binding(rig):
    groups = [SimpleNamespace(index=i, name=f"Bone{i}") for i in range(6)]
    vertices = [
        SimpleNamespace(index=i, groups=[
            SimpleNamespace(group=i % 6, weight=1.0)
        ])
        for i in range(160)
    ]
    return SimpleNamespace(
        type="MESH", name="MPFB Human",
        data=SimpleNamespace(vertices=vertices),
        vertex_groups=groups,
        parent=rig,
        modifiers=[SimpleNamespace(type="ARMATURE", object=rig)],
    )


class FakeBlender:
    def __init__(self):
        self.rig = armature()
        self.human = human_with_binding(self.rig)
        self.data = SimpleNamespace(objects=[self.human, self.rig])
        self.calls = []
        self.ops = SimpleNamespace(wm=SimpleNamespace(
            open_mainfile=self.open_mainfile,
            save_as_mainfile=self.save_as_mainfile,
        ))

    def open_mainfile(self, **kw):
        self.calls.append(("open", kw))

    def save_as_mainfile(self, **kw):
        self.calls.append(("save", kw))
        Path(kw["filepath"]).write_bytes(b"BLENDER" + b"test-only" * 250)


class TestRefitRevision(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "candidate.blend"
        self.source.write_bytes(b"BLENDER" + b"test-only" * 250)
        self.destination = self.root / "updated.blend"
        self.bpy = FakeBlender()
        self.values = {"height": .82, "muscle": .22, "weight": .88}
        self.previous = {"height": .5, "muscle": .5, "weight": .5}
        self.state = dict(self.previous)
        self.reapply = []
        self.refits = []
        self.target = SimpleNamespace(
            get_macro_info_dict_from_basemesh=lambda _: dict(self.state),
            reapply_macro_details=lambda human: self.reapply.append(human),
        )
        self.humansvc = SimpleNamespace(refit=self.refit)
        self.props = SimpleNamespace(get_value=lambda name, **kw: True,
                                     set_value=self.set_value)

    def set_value(self, name, value, *, entity_reference):
        self.state[name] = value

    def refit(self, human):
        self.refits.append(human)
        self.bpy.rig.data.bones[0].head_local = (0.0, 0.01, 0.0)

    def evidence(self, bpy, base, target, requested):
        return {
            "macro_parameters_observed": dict(requested),
            "macro_evaluated_vertices": 160,
            "macro_evaluated_sha256": ("a" if requested == self.previous else "b") * 64,
            "macro_active_shape_keys": 6,
            "macro_shape_evaluated": True,
            "visual_deformation_verified": False,
        }

    def run_revision(self):
        with patch("blender_bridge.refit_revision.inspect_applied_macro",
                   side_effect=self.evidence):
            return apply_body_revision(
                self.bpy, self.source, self.destination, self.values,
                self.humansvc, self.target, self.props,
            )

    def test_weight_fingerprint_detects_live_modifier_and_weight_groups(self):
        result = rig_fingerprint(self.bpy, self.bpy.human)
        self.assertTrue(result["rig_binding_verified"])
        self.assertEqual(result["weighted_vertices"], 160)
        self.assertEqual(result["bone_count"], 6)
        self.assertEqual(len(result["weight_sha256"]), 64)

    def test_existing_geometry_refit_only_saves_new_file(self):
        source_bytes = self.source.read_bytes()
        result = self.run_revision()
        self.assertEqual(result["previous_macros"], self.previous)
        self.assertEqual(result["macro_parameters_observed"], self.values)
        self.assertTrue(result["refit_saved"])
        self.assertEqual(result["previous_rig"]["weight_sha256"],
                         result["updated_rig"]["weight_sha256"])
        self.assertNotEqual(result["previous_rig"]["rig_rest_sha256"],
                            result["updated_rig"]["rig_rest_sha256"])
        self.assertEqual(len(self.reapply), 1)
        self.assertEqual(len(self.refits), 1)
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertTrue(self.destination.is_file())

    def test_noop_controls_refused_before_mutation(self):
        self.values = dict(self.previous)
        with self.assertRaisesRegex(RefitError, "already match"):
            self.run_revision()
        self.assertEqual(self.reapply, [])
        self.assertFalse(self.destination.exists())

    def test_no_armature_modifier_fails_closed(self):
        self.bpy.human.modifiers.clear()
        with self.assertRaisesRegex(RefitError, "armature modifier"):
            self.run_revision()
        self.assertFalse(self.destination.exists())

    def test_changed_bone_weights_do_not_save(self):
        def bad_refit(human):
            human.data.vertices[0].groups[0].weight = .7
        self.humansvc.refit = bad_refit
        with self.assertRaisesRegex(RefitError, "weight"):
            self.run_revision()
        self.assertFalse(self.destination.exists())

    def test_reject_overwriting_existing_output(self):
        self.destination.write_bytes(b"Important original")
        with self.assertRaisesRegex(RefitError, "unused"):
            self.run_revision()
        self.assertEqual(self.destination.read_bytes(), b"Important original")


if __name__ == "__main__":
    unittest.main()
