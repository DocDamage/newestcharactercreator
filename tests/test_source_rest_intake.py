"""Synthetic source-rest contracts; no external source-rig compatibility claim."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from blender_bridge.bvh_motion import LocalBvhMotion
from blender_bridge.source_rest_intake import inspect_source_rest_profile, SourceRestIntakeError
from blender_bridge.rest_calibration import RestCalibrationError
from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import (
    MAX_PROFILE_BYTES, read_source_rest_profile, validate_source_rest_profile, SourceRestProfileError,
)
from ucc.jobs.protocol import JobRequest
from ucc.jobs.reviewed_evidence import validate_reviewed_evidence, compare_reviewed_evidence, ReviewedEvidenceError
from test_reviewed_evidence import reviewed, PAIRS


def profile(source_sha="a" * 64, pairs=PAIRS, axis="Y_UP_TO_Z_UP"):
    return {
        "schema_version": 1, "source_bvh_sha256": source_sha, "axis_profile": axis,
        "frame_semantics": "BONE_REST_AXES_ONLY", "matrix_layout": "ROW_MAJOR_LOCAL_TO_BVH_REST",
        "provenance": {"provider": "Original synthetic test", "method": "Authored test frames",
                       "reference": "No production or purchased source"},
        "joint_frames": [
            {"source": p["source"], "parent": pairs[i-1]["source"] if i else None,
             "head": [0., float(i), 0.], "tail": [0., float(i + 1), 0.],
             "rotation": [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]}
            for i, p in enumerate(pairs)
        ],
    }


def motion(pairs=PAIRS):
    names = tuple(p["source"] for p in pairs)
    return LocalBvhMotion(.04, 25, {}, names,
        {n.casefold(): names[i-1].casefold() if i else None for i, n in enumerate(names)},
        {n.casefold(): (0., 1., 0.) if i else (0., 0., 0.) for i, n in enumerate(names)}, {},
        {names[-1].casefold(): (0., 1., 0.)})


class SourceRestIntakeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "source-rest.json"

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
        return sha256(self.path.read_bytes()).hexdigest()

    def worker(self, value):
        digest = self.write(value)
        return inspect_source_rest_profile(self.path, digest, motion(), "a" * 64, "Y_UP_TO_Z_UP", PAIRS)

    def test_exact_byte_binding_and_nonzero_bone_roll_are_validation_only(self):
        value = profile()
        value["joint_frames"][1]["rotation"] = [[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]]
        digest = self.write(value)
        original = self.path.read_bytes()
        parsed, measured = read_source_rest_profile(self.path, "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
        self.assertEqual(measured, digest)
        result = self.worker(parsed)
        self.assertTrue(result["validation_only"])
        self.assertFalse(result["source_channel_interpretation_changed"])
        self.assertFalse(result["source_roll_independently_verified"])
        self.assertNotEqual(result["joint_frames"][0]["rest_rotation_sha256"],
                            result["joint_frames"][1]["rest_rotation_sha256"])
        self.assertEqual(original, self.path.read_bytes())

    def test_schema_names_bindings_nonfinite_and_improper_frames_fail_both_boundaries(self):
        for case in ("sha", "axis", "semantics", "layout", "version", "missing", "duplicate",
                     "order", "reflect", "shear", "nan", "bool", "shape", "direction", "extra", "provenance"):
            value = profile()
            if case == "sha": value["source_bvh_sha256"] = "b" * 64
            if case == "axis": value["axis_profile"] = "Z_UP_IDENTITY"
            if case == "semantics": value["frame_semantics"] = "USE_AS_BVH_CHANNEL_AXES"
            if case == "layout": value["matrix_layout"] = "COLUMN_MAJOR"
            if case == "version": value["schema_version"] = True
            if case == "missing": value["joint_frames"].pop()
            if case == "duplicate": value["joint_frames"][1] = deepcopy(value["joint_frames"][0])
            if case == "order": value["joint_frames"].reverse()
            if case == "reflect": value["joint_frames"][0]["rotation"][0][0] = -1.
            if case == "shear": value["joint_frames"][0]["rotation"][0][1] = .1
            if case == "nan": value["joint_frames"][0]["head"][0] = float("nan")
            if case == "bool": value["joint_frames"][0]["head"][0] = False
            if case == "shape": value["joint_frames"][0]["rotation"].pop()
            if case == "direction": value["joint_frames"][0]["tail"] = [1., 0., 0.]
            if case == "extra": value["source_file"] = "../../private.blend"
            if case == "provenance": value["provenance"]["method"] = ""
            with self.subTest(case=case, gate="app"), self.assertRaises(ValidationError):
                validate_source_rest_profile(value, "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
            with self.subTest(case=case, gate="worker"), self.assertRaises((SourceRestIntakeError, RestCalibrationError)):
                self.worker(value)

    def test_actual_bvh_origin_end_site_and_parent_are_checked_independently(self):
        for case in ("origin", "end", "parent"):
            value = profile()
            if case == "origin":
                value["joint_frames"][0]["head"][0] += .125
                value["joint_frames"][0]["tail"][0] += .125
            if case == "end": value["joint_frames"][-1]["tail"][1] += .1
            if case == "parent": value["joint_frames"][-1]["parent"] = PAIRS[0]["source"]
            validate_source_rest_profile(value, "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
            with self.subTest(case=case), self.assertRaises(SourceRestIntakeError):
                self.worker(value)

    def test_duplicate_keys_malformed_utf8_and_oversize_are_rejected(self):
        for payload in (b'{"schema_version":1,"schema_version":1}', b'\xff', b'[]',
                        b' ' * (MAX_PROFILE_BYTES + 1), b'{', b'[' * 2000 + b'0' + b']' * 2000):
            self.path.write_bytes(payload)
            with self.subTest(payload=payload[:30]), self.assertRaises(ValidationError):
                read_source_rest_profile(self.path, "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
            with self.assertRaises((SourceRestIntakeError, RestCalibrationError)):
                inspect_source_rest_profile(self.path, sha256(payload).hexdigest(), motion(),
                                            "a" * 64, "Y_UP_TO_Z_UP", PAIRS)

    def test_staged_tamper_and_unsafe_protocol_options_fail(self):
        digest = self.write(profile())
        self.path.write_bytes(self.path.read_bytes() + b"\n")
        with self.assertRaisesRegex(SourceRestIntakeError, "SHA-256"):
            inspect_source_rest_profile(self.path, digest, motion(), "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
        options = {"axis_profile": "Y_UP_TO_Z_UP", "reviewed_mapping": PAIRS,
                   "source_rest_profile_sha256": digest}
        JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend", options=options)
        for bad in (True, "A" * 64, "../../profile.json", None):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend",
                               options={**options, "source_rest_profile_sha256": bad})
        with self.assertRaises(ValidationError):
            JobRequest.new("verify_reviewed_bvh_chain", input_project="candidate.blend",
                           options={**options, "profile_path": "/arbitrary/file"})

    def test_all_64_joint_records_are_validated_including_the_last(self):
        pairs = [{"source": f"S{i}", "target": f"T{i}"} for i in range(64)]
        value = profile(pairs=pairs)
        validate_source_rest_profile(value, "a" * 64, "Y_UP_TO_Z_UP", pairs)
        digest = self.write(value)
        result = inspect_source_rest_profile(self.path, digest, motion(pairs),
                                             "a" * 64, "Y_UP_TO_Z_UP", pairs)
        self.assertEqual(result["joint_count"], 64)
        value["joint_frames"][-1]["head"][0] += .125
        value["joint_frames"][-1]["tail"][0] += .125
        digest = self.write(value)
        with self.assertRaisesRegex(SourceRestIntakeError, "rest head"):
            inspect_source_rest_profile(self.path, digest, motion(pairs),
                                        "a" * 64, "Y_UP_TO_Z_UP", pairs)

    def test_evidence_cannot_certify_application_roll_or_other_profile(self):
        data = reviewed()
        value = profile(data["source_sha256"])
        digest = self.write(value)
        data["source_rest_frame_intake"] = inspect_source_rest_profile(
            self.path, digest, motion(), data["source_sha256"], "Y_UP_TO_Z_UP", PAIRS)
        options = {"source_rest_profile": value, "source_rest_profile_sha256": digest}
        validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS, **options)
        compare_reviewed_evidence(data, data, "Y_UP_TO_Z_UP", PAIRS, **options)
        with self.assertRaises(ValidationError):
            validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS)
        for field, changed in (("profile_sha256", "f" * 64), ("joint_count", 2),
                               ("validation_only", False), ("source_channel_interpretation_changed", True),
                               ("source_roll_independently_verified", True)):
            bad = deepcopy(data)
            bad["source_rest_frame_intake"][field] = changed
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_reviewed_evidence(bad, "Y_UP_TO_Z_UP", PAIRS, **options)
        second = deepcopy(data)
        second["source_rest_frame_intake"]["joint_frames"][0]["rest_head_error_local"] = 1e-6
        with self.assertRaisesRegex(ReviewedEvidenceError, "disagree"):
            compare_reviewed_evidence(data, second, "Y_UP_TO_Z_UP", PAIRS, **options)

    def test_audited_workers_must_agree_on_conversion_traces(self):
        from test_channel_bone_conversion import proof
        data = reviewed()
        value = profile(data["source_sha256"])
        digest = self.write(value)
        data["source_rest_frame_intake"] = inspect_source_rest_profile(
            self.path, digest, motion(), data["source_sha256"], "Y_UP_TO_Z_UP", PAIRS)
        data["source_frame_conversion"] = proof(data["mapped_bone_count"], data["source_frame_count"])
        data["source_frame_conversion"].update(profile_sha256=digest, mapping_sha256=data["reviewed_mapping_sha256"])
        options = {"source_rest_profile": value, "source_rest_profile_sha256": digest, "audit_source_frames": True}
        compare_reviewed_evidence(data, data, "Y_UP_TO_Z_UP", PAIRS, **options)
        second = deepcopy(data)
        second["source_frame_conversion"]["traces"][-1]["trace_sha256"] = "f"*64
        with self.assertRaisesRegex(ReviewedEvidenceError, "channel/bone"):
            compare_reviewed_evidence(data, second, "Y_UP_TO_Z_UP", PAIRS, **options)

    def test_symlink_is_rejected_when_host_supports_it(self):
        self.write(profile())
        link = self.path.with_name("redirected.json")
        try:
            link.symlink_to(self.path)
        except OSError:
            self.skipTest("Windows symlink privilege unavailable")
        with self.assertRaises(ValidationError):
            read_source_rest_profile(link, "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
        with self.assertRaises(SourceRestIntakeError):
            inspect_source_rest_profile(link, sha256(self.path.read_bytes()).hexdigest(), motion(),
                                        "a" * 64, "Y_UP_TO_Z_UP", PAIRS)
