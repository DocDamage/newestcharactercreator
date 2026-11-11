"""Synthetic bpy-style contract checks, NOT a real Blender animation clip."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from blender_bridge.timeline_animation import (
    TimelineProbeError, validate_timeline_frame_stats, verify_keyframed_timeline,
)


class FakeBone:
    def __init__(self, rig):
        self.rig = rig
        self.rotation_mode = "QUATERNION"
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.keys = []

    @property
    def matrix_basis(self):
        return SimpleNamespace(copy=lambda: tuple(self.rotation_euler))

    @matrix_basis.setter
    def matrix_basis(self, value):
        self.rotation_euler[:] = value

    def keyframe_insert(self, *, data_path, frame, group):
        self.keys.append((frame, tuple(self.rotation_euler)))
        if not self.rig.animation_data:
            self.rig.animation_data = SimpleNamespace(
                action=SimpleNamespace(name="TEST ONLY"), nla_tracks=[]
            )
        return True


class FakeScene:
    def __init__(self, rig):
        self.frame_current = 1
        self.render = SimpleNamespace(fps=30, fps_base=1.0)
        self.rig = rig

    def frame_set(self, frame):
        self.frame_current = frame
        keys = dict(self.rig.pose.bones["head"].keys)
        if 1 not in keys:
            return
        before = 1 if frame <= 13 else 13
        after = 13 if frame <= 13 else 25
        portion = (frame - before) / (after - before)
        left, right = keys[before], keys[after]
        self.rig.pose.bones["head"].rotation_euler[:] = [
            a + (b - a) * portion for a, b in zip(left, right)
        ]


class FakeBpy:
    def __init__(self):
        self.rig = SimpleNamespace(
            type="ARMATURE",
            animation_data=None,
            data=SimpleNamespace(pose_position="POSE"),
        )
        self.rig.animation_data_clear = lambda: setattr(self.rig, "animation_data", None)
        self.bone = FakeBone(self.rig)
        self.rig.pose = SimpleNamespace(bones={"head": self.bone})
        self.scene = FakeScene(self.rig)
        self.human = SimpleNamespace(
            type="MESH", data=SimpleNamespace(vertices=[0] * 19158),
        )
        self.data = SimpleNamespace(
            objects=[self.human, self.rig],
            actions=SimpleNamespace(remove=lambda action, **kw: None),
        )
        self.context = SimpleNamespace(
            scene=self.scene,
            view_layer=SimpleNamespace(update=lambda: None),
        )
        self.app = SimpleNamespace(version_string="5.3.0")

    def evaluated(self):
        value = self.bone.rotation_euler[0]
        points = tuple((i * .0001, value * i / 1000, 0.0) for i in range(200))
        digest = sha256()
        for point in points:
            digest.update(struct.pack("<qqq", *(round(x * 1_000_000) for x in point)))
        return points, digest.hexdigest()


class KeyframeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test-only.blend"
        self.path.write_bytes(b"BLENDER" + b"synthetic-not-real" * 100)
        self.bpy = FakeBpy()
        self.pose = {
            "selected_deform_bone": "head", "rotation_axis_index": 0,
            "rig_weight_sha256": "a" * 64,
        }
        self.rig = {
            "weight_sha256": "a" * 64,
            "rig_rest_sha256": "b" * 64, "bone_count": 163,
        }

    def execute(self, *, sample=None):
        if sample is None:
            sample = lambda bpy, human: self.bpy.evaluated()
        with patch("blender_bridge.timeline_animation.probe_pose_deformation",
                   return_value=self.pose):
            with patch("blender_bridge.timeline_animation.rig_fingerprint",
                       return_value=self.rig):
                with patch("blender_bridge.timeline_animation._evaluated_vertices",
                           side_effect=sample):
                    return verify_keyframed_timeline(self.bpy, self.path)

    def test_keyframes_are_inserted_and_five_frames_read_from_blender(self):
        original = self.path.read_bytes()
        result = self.execute()
        self.assertEqual(result["keyframes"], [1, 13, 25])
        self.assertEqual([x["frame"] for x in result["sampled_frames"]],
                         [1, 7, 13, 19, 25])
        self.assertEqual([frame for frame, _ in self.bone.keys]
                         if False else [frame for frame, _ in self.bpy.bone.keys],
                         [1, 13, 25])
        self.assertGreater(result["sampled_frames"][2]["moved_vertices"], 16)
        self.assertEqual(result["sampled_frames"][0]["evaluated_sha256"],
                         result["sampled_frames"][-1]["evaluated_sha256"])
        self.assertEqual(self.bpy.rig.animation_data, None)
        self.assertEqual(self.bpy.bone.rotation_mode, "QUATERNION")
        self.assertEqual(self.bpy.scene.render.fps, 30)
        self.assertEqual(self.bpy.scene.frame_current, 1)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(result["user_animation_playback_verified"])

    def test_never_overwrites_existing_animation(self):
        self.bpy.rig.animation_data = SimpleNamespace(
            action=SimpleNamespace(name="Real user clip"), nla_tracks=[]
        )
        with self.assertRaisesRegex(TimelineProbeError, "already has animation"):
            self.execute()
        self.assertEqual(self.bpy.bone.keys, [])

    def test_no_interpolation_fails_closed(self):
        points = tuple((float(i), 0.0, 0.0) for i in range(200))
        def no_motion(bpy, human):
            return points, "c" * 64
        with self.assertRaises(TimelineProbeError):
            self.execute(sample=no_motion)
        self.assertEqual(self.path.read_bytes(),
                         b"BLENDER" + b"synthetic-not-real" * 100)

    def test_sample_validator_rejects_missing_sample(self):
        with self.assertRaisesRegex(TimelineProbeError, "five"):
            validate_timeline_frame_stats([])


if __name__ == "__main__":
    unittest.main()
