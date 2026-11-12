"""Synthetic staging/race contracts; actual Blender acceptance is separate."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from blender_bridge.bvh_motion import read_local_bvh
from blender_bridge.source_rest_intake import inspect_source_rest_profile
from ucc.core.errors import ValidationError, ProjectStorageError
from ucc.jobs.protocol import JobResult
from ucc.library.provenance import AssetPolicyError
import test_bvh_clip_diagnostic as bvh_contracts
from test_reviewed_evidence import reviewed, PAIRS
from test_source_rest_intake import profile


class SourceRestCoordinatorTests(unittest.TestCase):
    invoke = bvh_contracts.LocalBvhPreviewContractTests.invoke

    def setUp(self):
        bvh_contracts.LocalBvhPreviewContractTests.setUp(self)
        lines = ["HIERARCHY"]
        for i, pair in enumerate(PAIRS):
            lines += [f'{"ROOT" if i == 0 else "JOINT"} {pair["source"]}', "{",
                      "OFFSET 0 0 0" if i == 0 else "OFFSET 0 1 0",
                      "CHANNELS 3 Xrotation Yrotation Zrotation"]
        lines += ["End Site", "{", "OFFSET 0 1 0", "}", "}", "}", "}",
                  "MOTION", "Frames: 25", "Frame Time: 0.041666667"]
        lines += [" ".join([f"{i % 5} 0 0"] * 3) for i in range(25)]
        self.source.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.rest = self.root / "rest.json"
        self.rest.write_text(json.dumps(profile(sha256(self.source.read_bytes()).hexdigest())), encoding="utf-8")
        self.mode = "valid"

    def runner(self, job, **kwargs):
        self.calls += 1
        folder = self.store.root / ".ucc-jobs" / job.job_id
        folder.mkdir(parents=True)
        self.assertEqual(set(kwargs["staged_inputs"]),
                         {"candidate.blend", "motion.bvh", "source_rest_frames.json"})
        for name, source in kwargs["staged_inputs"].items():
            (folder / name).write_bytes(source.read_bytes())
        staged = folder / "source_rest_frames.json"
        evidence = deepcopy(reviewed())
        evidence["source_sha256"] = sha256(self.source.read_bytes()).hexdigest()
        evidence["source_rest_frame_intake"] = inspect_source_rest_profile(
            staged, job.options["source_rest_profile_sha256"], read_local_bvh(self.source),
            evidence["source_sha256"], "Y_UP_TO_Z_UP", PAIRS)
        artifact = b"BLENDER" + b"SYNTHETIC_UNIT_ONLY" * 800
        (folder / "review_motion.blend").write_bytes(artifact)
        evidence["visual_review_blend"] = {"name": "review_motion.blend", "bytes": len(artifact),
                                            "sha256": sha256(artifact).hexdigest()}
        if self.mode == "staged": staged.write_bytes(staged.read_bytes() + b" ")
        if self.mode == "original": self.rest.write_bytes(self.rest.read_bytes() + b" ")
        if self.mode == "deleted": self.rest.unlink()
        if self.mode == "cancel": self.cancel.set()
        return JobResult(job.job_id, job.operation, "ok", evidence), folder

    def check(self, **kwargs):
        return self.invoke(multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
                           reviewed_mapping=PAIRS, source_rest_profile=self.rest, **kwargs)

    def test_two_workers_bind_staged_bytes_and_preserve_original_files(self):
        original = [p.read_bytes() for p in (self.rest, self.source, self.master, self.store.file)]
        result = self.check()
        self.assertEqual(self.calls, 2)
        self.assertTrue(result.evidence["source_rest_frame_intake"]["validation_only"])
        self.assertEqual(original, [p.read_bytes() for p in (self.rest, self.source, self.master, self.store.file)])

    def test_profile_mutation_cancellation_and_permission_fail_closed(self):
        for mode in ("staged", "original", "deleted", "cancel"):
            self.mode = mode
            original = self.rest.read_bytes()
            with self.subTest(mode=mode), self.assertRaises(ProjectStorageError):
                self.check()
            self.cancel.clear()
            self.rest.write_bytes(original)
        self.calls = 0
        from dataclasses import replace
        with self.assertRaises(AssetPolicyError):
            self.check(permission=replace(self.policy, ue_only=True))
        self.assertEqual(self.calls, 0)

    def test_binding_rejects_before_worker_and_profile_requires_reviewed_operation(self):
        data = json.loads(self.rest.read_text(encoding="utf-8"))
        data["source_bvh_sha256"] = "0" * 64
        self.rest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.check()
        with self.assertRaises(ValidationError):
            self.invoke(source_rest_profile=self.rest)
        self.assertEqual(self.calls, 0)
