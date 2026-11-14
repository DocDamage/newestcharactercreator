"""Private bitmap integrity tests; synthetic pixels are not visual acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.private_render_png import png
from ucc.core.errors import ValidationError
from ucc.jobs.private_render_evidence import png_measurements, verify_private_renders, verify_native_renders, VIEWS


class PrivateRenderEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = [png(phase=i*9) for i in range(5)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.root = self.folder / "review_frames"
        self.root.mkdir()
        self.raw = {"source_frame_count": 25, "visual_review_blend": {"sha256": "d"*64},
                    "full_timeline_frames": [{"frame": i, "evaluated_sha256": f"{i:064x}"} for i in range(1,26)]}
        self.manifest = {"schema_version": 1, "method": "CYCLES_CPU_EVALUATED_SKIN_CLAY_V1",
                         "source_bvh_sha256": "a"*64, "source_rest_profile_sha256": "b"*64,
                         "source_master_sha256": "c"*64, "review_action_sha256": "d"*64,
                         "conversion_convention": "BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1",
                         "source_frame_count": 25, "rendered_frames": [1,7,13,19,25],
                         "animation_visual_quality_verified": False, "images": []}
        for i, frame in enumerate(self.manifest["rendered_frames"]):
            for view in VIEWS:
                record = self.write(f"frame_{frame:04}_{view}.png", self.images[i])
                record.update(frame=frame, view=view, width=256, height=384,
                              evaluated_sha256=f"{frame:064x}", opaque_pixels=64000,
                              opaque_bounds=[25,30,224,349])
                self.manifest["images"].append(record)
        self.raw["private_review_renders"] = {"index": self.write("index.html", b"PRIVATE TEST INDEX"),
                                             "image_count": 15, "animation_visual_quality_verified": False}
        self.save_manifest()

    def write(self, name, data):
        (self.root / name).write_bytes(data)
        return {"name": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}

    def save_manifest(self, payload=None):
        self.raw["private_review_renders"]["manifest"] = self.write(
            "manifest.json", payload if payload is not None else json.dumps(self.manifest).encode())

    def verify(self):
        return verify_private_renders(self.folder, self.raw, source_sha="a"*64, profile_sha="b"*64, master_sha="c"*64)

    def test_all_png_filters_independently_decode_same_pixels(self):
        expected = {"opaque_pixels": 64000, "opaque_bounds": [25,30,224,349]}
        for method in range(5):
            with self.subTest(method=method):
                self.assertEqual(png_measurements(png(method)), expected)

    def test_complete_private_bound_set_returns_local_index(self):
        self.assertEqual(self.verify(), str(self.root / "index.html"))

    def test_checksum_truncation_blank_clipping_and_excess_decoding_fail(self):
        damaged = bytearray(self.images[0])
        damaged[-5] ^= 1
        for data in (bytes(damaged), self.images[0][:-5], png(blank=True), png(clipped=True), png(bomb=True)):
            with self.subTest(length=len(data)), self.assertRaises(ValidationError):
                png_measurements(data)

    def test_provenance_frame_coverage_skin_hash_and_approval_must_match(self):
        original = deepcopy(self.manifest)
        for field, value in (("source_bvh_sha256", "f"*64), ("source_rest_profile_sha256", "f"*64),
                             ("source_master_sha256", "f"*64), ("review_action_sha256", "f"*64),
                             ("conversion_convention", "AUTO"), ("rendered_frames", [True,7,13,19,25]),
                             ("source_frame_count", True), ("animation_visual_quality_verified", True)):
            self.manifest = {**deepcopy(original), field: value}
            self.save_manifest()
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.verify()
        for field, value in (("frame", True), ("view", "back"), ("evaluated_sha256", "f"*64),
                             ("opaque_pixels", 1), ("opaque_bounds", [0,0,255,383]), ("name", "../escape.png")):
            self.manifest = deepcopy(original)
            self.manifest["images"][0][field] = value
            self.save_manifest()
            with self.subTest(record=field), self.assertRaises(ValidationError):
                self.verify()

    def test_rehashed_bad_manifest_missing_image_and_tamper_fail(self):
        for payload in (b'{"schema_version":1,"schema_version":1}', b'NaN', b'\xff', b'['*2000+b'0'+b']'*2000):
            self.save_manifest(payload)
            with self.assertRaises(ValidationError):
                self.verify()
        self.save_manifest()
        name = self.manifest["images"][-1]["name"]
        path = self.root / name
        path.write_bytes(path.read_bytes() + b"tampered")
        with self.assertRaises(ValidationError):
            self.verify()
        path.unlink()
        with self.assertRaises(ValidationError):
            self.verify()

    def test_repeated_still_images_do_not_pass_as_animation_evidence(self):
        for record in self.manifest["images"]:
            record.update(self.write(record["name"], self.images[0]))
        self.save_manifest()
        with self.assertRaisesRegex(ValidationError, "changing"):
            self.verify()

    def native_manifest(self, *, hip=False):
        bindings = {key: value*64 for key, value in (("source_sha256", "a"), ("snapshot_sha256", "b"),
                    ("mapping_sha256", "c"), ("master_sha256", "e"))}
        self.raw.update(bindings=bindings, timeline={"sha256": "f"*64})
        timeline = {"source_first_frame": 7, "full_timeline_frames": self.raw["full_timeline_frames"]}
        for row in timeline["full_timeline_frames"]:
            row["root_world_head"] = [row["frame"]*.1, 0., 1.]
            if hip:row["hip_midpoint_world"] = [row["frame"]*.02, 0., 1.]
        if hip:timeline["root_motion_policy"]="SOURCE_HIP_MIDPOINT_V1"
        for key in ("source_bvh_sha256", "source_rest_profile_sha256", "source_master_sha256"):
            del self.manifest[key]
        self.manifest.update(**bindings, timeline_sha256="f"*64, source_first_frame=7,
                             conversion_convention="NATIVE_ANATOMICAL_REFERENCE_V1",
                             camera_translation_policy="FOLLOW_HIP_MIDPOINT_TRANSLATION" if hip else "FOLLOW_ROOT_TRANSLATION")
        for row in self.manifest["images"]:
            row["camera_hip_offset_world" if hip else "camera_root_offset_world"] = [(row["frame"]-1)*(.02 if hip else .1), 0., 0.]
        self.save_manifest()
        return timeline

    def test_native_manifest_binds_all_inputs_and_camera_to_measured_root(self):
        timeline=self.native_manifest()
        self.assertEqual(verify_native_renders(self.folder, self.raw, timeline), str(self.root / "index.html"))
        original = deepcopy(self.manifest)
        for fault in ("map", "snapshot", "timeline", "first", "camera", "root"):
            self.manifest = deepcopy(original)
            if fault == "map": self.manifest["mapping_sha256"] = "f"*64
            if fault == "snapshot": self.manifest["snapshot_sha256"] = "f"*64
            if fault == "timeline": self.manifest["timeline_sha256"] = "a"*64
            if fault == "first": self.manifest["source_first_frame"] = 1
            if fault == "camera": self.manifest["camera_translation_policy"] = "STATIC"
            if fault == "root": self.manifest["images"][-1]["camera_root_offset_world"] = [0., 0., 0.]
            self.save_manifest()
            with self.subTest(fault=fault), self.assertRaises(ValidationError):
                verify_native_renders(self.folder, self.raw, timeline)

    def test_anchored_camera_must_follow_actual_hip_instead_of_compensated_floor_root(self):
        timeline=self.native_manifest(hip=True)
        self.assertEqual(verify_native_renders(self.folder,self.raw,timeline),str(self.root/"index.html"))
        self.manifest["images"][-1]["camera_hip_offset_world"]=[2.4,0.,0.]
        self.save_manifest()
        with self.assertRaisesRegex(ValidationError,"trajectory"):verify_native_renders(self.folder,self.raw,timeline)
