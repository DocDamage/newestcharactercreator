"""Synthetic Blender-style pose tests; not actual MPFB/Blender integration proof."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from blender_bridge.pose_deformation import (
    PoseProbeError, _movement, _pose_candidates, probe_pose_deformation,
)


class Basis:
    def __init__(self, angles):
        self.angles = tuple(angles)

    def copy(self):
        return Basis(self.angles)


class PoseBone:
    def __init__(self, name):
        self.name = name
        self.rotation_mode = "QUATERNION"
        self.rotation_euler = [0.0, 0.0, 0.0]

    @property
    def matrix_basis(self):
        return Basis(self.rotation_euler)

    @matrix_basis.setter
    def matrix_basis(self, basis):
        self.rotation_euler[:] = basis.angles


class BlenderStub:
    def __init__(self):
        root = SimpleNamespace(name="Root", parent=None, use_deform=True)
        child = SimpleNamespace(name="Arm", parent=root, use_deform=True)
        self.arm = PoseBone("Arm")
        self.rig = SimpleNamespace(
            type="ARMATURE",
            data=SimpleNamespace(bones=[root, child], pose_position="POSE"),
            pose=SimpleNamespace(bones={"Arm": self.arm}),
        )
        self.human = SimpleNamespace(
            type="MESH", data=SimpleNamespace(vertices=[
                SimpleNamespace(index=i, groups=[
                    SimpleNamespace(group=0, weight=1.0)
                ]) for i in range(200)
            ]),
            vertex_groups=[SimpleNamespace(index=0, name="Arm")],
        )
        self.data = SimpleNamespace(objects=[self.human, self.rig])
        self.context = SimpleNamespace(
            view_layer=SimpleNamespace(update=lambda: None),
        )
        self.opens = []
        self.saves = []
        self.ops = SimpleNamespace(wm=SimpleNamespace(
            open_mainfile=lambda **kw: self.opens.append(kw),
            save_as_mainfile=lambda **kw: self.saves.append(kw),
        ))
        self.app = SimpleNamespace(version_string="5.3.0")

    def coordinates(self):
        offset = sum(self.arm.rotation_euler)
        points = tuple((float(i) / 1000, offset * (i + 1) / 100, 0.0)
                       for i in range(200))
        digest = sha256()
        for xyz in points:
            digest.update(struct.pack("<qqq", *(round(v * 1_000_000) for v in xyz)))
        return points, digest.hexdigest()


class ProbeUnitContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "test.blend"
        self.source.write_bytes(b"BLENDER" + b"synthetic-contract-only" * 180)
        self.blender = BlenderStub()
        self.rig_data = {"bone_count": 163, "rig_binding_verified": True,
                         "weight_sha256": "a" * 64, "rig_rest_sha256": "b" * 64}

    def probe(self):
        with patch("blender_bridge.pose_deformation._evaluated_vertices",
                   side_effect=lambda bpy, human: self.blender.coordinates()):
            with patch("blender_bridge.pose_deformation.rig_fingerprint",
                       return_value=self.rig_data):
                return probe_pose_deformation(self.blender, self.source)

    def test_weighted_bone_moves_mesh_and_is_restored_without_saving(self):
        original = self.source.read_bytes()
        result = self.probe()
        self.assertEqual(result["status"], "REAL_STATIC_SKIN_POSE_MOVEMENT_MEASURED")
        self.assertEqual(result["selected_deform_bone"], "Arm")
        self.assertGreater(result["moved_vertex_count"], 16)
        self.assertNotEqual(result["neutral_evaluated_sha256"],
                            result["posed_evaluated_sha256"])
        self.assertEqual(result["neutral_evaluated_sha256"],
                         result["restored_evaluated_sha256"])
        self.assertEqual(self.blender.arm.rotation_euler, [0.0, 0.0, 0.0])
        self.assertEqual(self.blender.arm.rotation_mode, "QUATERNION")
        self.assertEqual(self.blender.saves, [])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(result["animation_clip_playback_verified"])

    def test_no_weighted_nonroot_bones_rejected(self):
        self.blender.human.data.vertices[0].groups[0].weight = 0
        self.blender.human.vertex_groups[0].name = "Missing Bone"
        with self.assertRaisesRegex(PoseProbeError, "non-root deform bones"):
            _pose_candidates(self.blender.human, self.blender.rig)

    def test_zero_pose_deformation_fails_without_source_mutation(self):
        def no_movement(bpy, human):
            coords = tuple((float(i) / 1000, 0.0, 0.0) for i in range(200))
            return coords, "a" * 64
        with patch("blender_bridge.pose_deformation._evaluated_vertices",
                   side_effect=no_movement):
            with patch("blender_bridge.pose_deformation.rig_fingerprint",
                       return_value=self.rig_data):
                with self.assertRaisesRegex(PoseProbeError, "No weighted deform bone moved"):
                    probe_pose_deformation(self.blender, self.source)
        self.assertEqual(self.blender.arm.rotation_euler, [0.0, 0.0, 0.0])
        self.assertEqual(self.blender.saves, [])

    def test_restoration_failure_is_rejected(self):
        class BrokenBasis(PoseBone):
            @PoseBone.matrix_basis.setter
            def matrix_basis(self, basis):
                pass
        self.blender.arm = BrokenBasis("Arm")
        with self.assertRaisesRegex(PoseProbeError, "restore"):
            self.probe()

    def test_mismatched_mesh_topology_fails(self):
        with self.assertRaisesRegex(PoseProbeError, "topology"):
            _movement(((0.0, 0.0, 0.0),), ())

    def test_redirected_source_fails_before_any_blender_execution(self):
        alias = self.source.with_name("alias.blend")
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with patch("blender_bridge.pose_deformation.rig_fingerprint",
                   return_value=self.rig_data):
            with self.assertRaisesRegex(PoseProbeError, "regular"):
                probe_pose_deformation(self.blender, alias)
        self.assertEqual(self.blender.opens, [])


if __name__ == "__main__":
    unittest.main()
