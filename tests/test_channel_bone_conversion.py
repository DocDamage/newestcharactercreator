"""Synthetic basis audits, not proof of source skeleton or visual compatibility."""
from copy import deepcopy
import unittest

from blender_bridge.channel_bone_conversion import (
    CONVENTION, ConversionTrace, ChannelBoneConversionError, convert_channel_delta, residual,
)
from blender_bridge.rest_calibration import (
    axis_rotation, multiply, transpose, Z_UP_IDENTITY as I, RestCalibrationError,
)
from ucc.core.errors import ValidationError
from ucc.jobs.channel_conversion_evidence import validate_channel_conversion
from ucc.jobs.protocol import JobRequest


def proof(joints=3, frames=25):
    return {"convention": CONVENTION, "coordinate_change_applied": True,
            "source_channel_interpretation_changed": False, "target_motion_changed_by_source_roll": False,
            "profile_sha256": "b"*64, "mapping_sha256": "c"*64, "joint_count": joints,
            "source_frame_count": frames, "max_roundtrip_residual": 0., "max_target_equivalence_residual": 0.,
            "traces": [{"trace_sha256": "d"*64, "frames_measured": frames,
                        "max_roundtrip_residual": 0., "max_target_equivalence_residual": 0.} for _ in range(joints)]}


class ChannelBoneConversionTests(unittest.TestCase):
    def test_nonzero_start_noncommuting_channels_and_independent_rest_frames(self):
        start = multiply(axis_rotation("Xrotation", 23), axis_rotation("Yrotation", -17))
        current = multiply(axis_rotation("Zrotation", 41), axis_rotation("Xrotation", -36))
        source = axis_rotation("Yrotation", 73)
        axes, target = axis_rotation("Zrotation", 29), axis_rotation("Xrotation", -48)
        result, channel, bone, rt, eq = convert_channel_delta(start, current, source, axes, target)
        expected_channel = multiply(transpose(start), current)
        transfer = multiply(transpose(target), axes)
        expected = multiply(multiply(transfer, expected_channel), transpose(transfer))
        self.assertLess(residual(result, expected), 1e-12)
        self.assertLess(residual(channel, expected_channel), 1e-12)
        self.assertGreater(residual(bone, channel), .1)
        self.assertLess(max(rt, eq), 1e-12)
        self.assertGreater(residual(channel, multiply(current, transpose(start))), .1)

    def test_source_roll_changes_bone_coordinates_not_target_motion(self):
        current = axis_rotation("Xrotation", 37)
        a, _, bone_a, _, _ = convert_channel_delta(I, current, I, I, I)
        b, _, bone_b, _, _ = convert_channel_delta(I, current, axis_rotation("Yrotation", 90), I, I)
        self.assertLess(residual(a, b), 1e-12)
        self.assertGreater(residual(bone_a, bone_b), .5)
        first, second = ConversionTrace(), ConversionTrace()
        first.apply(1, I, current, I, I, I)
        second.apply(1, I, current, axis_rotation("Yrotation", 90), I, I)
        self.assertNotEqual(first.report()["trace_sha256"], second.report()["trace_sha256"])

    def test_identity_reference_roundtrip_and_trace_requires_every_frame(self):
        trace = ConversionTrace()
        r = axis_rotation("Zrotation", 45)
        self.assertLess(residual(trace.apply(1, r, r, r, r, r), I), 1e-12)
        for invalid in (1, 3, True):
            with self.assertRaises(ChannelBoneConversionError):
                trace.apply(invalid, I, I, I, I, I)
        self.assertEqual(trace.report()["frames_measured"], 1)

    def test_reflection_shear_and_nonfinite_cannot_be_converted(self):
        for bad in (((-1,0,0),(0,1,0),(0,0,1)), ((1,.1,0),(0,1,0),(0,0,1)),
                    ((float("nan"),0,0),(0,1,0),(0,0,1))):
            with self.assertRaises(RestCalibrationError):
                convert_channel_delta(I, I, bad, I, I)

    def test_proof_binding_counts_residuals_and_false_claims_fail_closed(self):
        raw = {"source_frame_conversion": proof(), "reviewed_mapping_sha256": "c"*64,
               "mapped_bone_count": 3, "source_frame_count": 25}
        validate_channel_conversion(raw, True, "b"*64)
        with self.assertRaises(ValidationError):
            validate_channel_conversion(raw, False, None)
        changes = {"convention": "INFER_CHANNEL_AXES", "coordinate_change_applied": False,
                   "target_motion_changed_by_source_roll": True, "source_channel_interpretation_changed": True,
                   "profile_sha256": "f"*64, "mapping_sha256": "f"*64, "joint_count": True,
                   "source_frame_count": 24, "max_roundtrip_residual": .1,
                   "max_target_equivalence_residual": float("nan"), "traces": [], "extra": True}
        for key, value in changes.items():
            bad = deepcopy(raw)
            bad["source_frame_conversion"][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                validate_channel_conversion(bad, True, "b"*64)
        for key, value in (("frames_measured", 24), ("trace_sha256", "bad"),
                           ("max_roundtrip_residual", 1e-4), ("max_target_equivalence_residual", True)):
            bad = deepcopy(raw)
            bad["source_frame_conversion"]["traces"][-1][key] = value
            with self.subTest(trace=key), self.assertRaises(ValidationError):
                validate_channel_conversion(bad, True, "b"*64)

    def test_protocol_requires_exact_convention_profile_and_literal_render_flag(self):
        base = {"axis_profile": "Y_UP_TO_Z_UP", "reviewed_mapping": [
            {"source": f"S{i}", "target": f"T{i}"} for i in range(3)]}
        options = {**base, "source_rest_profile_sha256": "b"*64, "source_frame_conversion": CONVENTION,
                   "render_private_frames": True}
        JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend", options=options)
        for bad in ({**base, "source_frame_conversion": CONVENTION},
                    {**base, "render_private_frames": True},
                    {**options, "source_frame_conversion": "AUTO"},
                    {**options, "render_private_frames": 1}, {**options, "render_private_frames": False}):
            with self.subTest(options=bad), self.assertRaises(ValidationError):
                JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend", options=bad)
