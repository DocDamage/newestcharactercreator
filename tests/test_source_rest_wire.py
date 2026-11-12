"""Synthetic protocol capacity; not Blender deformation/compatibility evidence."""
from copy import deepcopy
import json
import unittest
from uuid import uuid4

from blender_bridge.result_encoding import encode_result
from ucc.jobs.protocol import JobResult, MAX_REQUEST_BYTES
from test_reviewed_evidence import reviewed


class SourceRestWireCapacity(unittest.TestCase):
    def test_64_maximum_length_names_and_240_frame_evidence_fit_existing_wire_limit(self):
        data = reviewed()
        sources = [f"S{i:02}" + "s" * 125 for i in range(64)]
        targets = [f"T{i:02}" + "t" * 125 for i in range(64)]
        data["mapped_bones"] = [
            {"source": s, "target": t, "parent": sources[i-1].casefold() if i else None,
             "target_parent": targets[i-1] if i else None}
            for i, (s, t) in enumerate(zip(sources, targets))]
        data["per_bone_deformation"] = [{**data["per_bone_deformation"][0], "bone": t} for t in targets]
        data["local_axis_proofs"] = [
            {**data["local_axis_proofs"][0], "source": s, "target": t} for s, t in zip(sources, targets)]
        data["joint_motion_metrics"] = [
            {**data["joint_motion_metrics"][0], "bone": t, "frames_measured": 240} for t in targets]
        data["max_bone_quaternion_step_degrees"] = {t: 1.2345678901234567 for t in targets}
        data["full_timeline_frames"] = [
            {**data["full_timeline_frames"][1], "frame": i+1,
             "max_displacement_local": .12345678901234567,
             "adjacent_max_displacement_local": .12345678901234567,
             "min_edge_length_ratio": .9876543210987654,
             "max_edge_stretch_ratio": 1.2345678901234567} for i in range(240)]
        data.update(source_frame_count=240, mapped_bone_count=64,
                    rest_residual_degrees=[.12345678901234567] * 64)
        data["source_rest_frame_intake"] = {
            "schema_version": 1, "profile_sha256": "b" * 64, "source_bvh_sha256": "a" * 64,
            "axis_profile": "Y_UP_TO_Z_UP", "joint_count": 64, "validation_only": True,
            "source_channel_interpretation_changed": False, "source_roll_independently_verified": False,
            "joint_frames": [
                {"source": s, "parent": sources[i-1] if i else None,
                 "rest_rotation_sha256": "c" * 64, "rest_head_error_local": 1.2345678901234567e-7,
                 "terminal_tail_error_local": 1.2345678901234567e-7,
                 "tail_axis_error_degrees": .12345678901234567} for i, s in enumerate(sources)]}
        reply = JobResult(str(uuid4()), "verify_reviewed_bvh_chain", "ok", data).as_dict()
        original = deepcopy(reply)
        encoded = encode_result(reply)
        self.assertLessEqual(len(encoded.encode("utf-8")), MAX_REQUEST_BYTES)
        self.assertEqual(json.loads(encoded), original)
        self.assertEqual(reply, original)

    def test_nonfinite_worker_data_cannot_be_serialized(self):
        with self.assertRaises(ValueError):
            encode_result({"invalid": float("nan")})
