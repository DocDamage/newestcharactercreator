"""Synthetic metadata/structure fixtures; no purchased animation or real retarget proof."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.metadata import (
    AnimationMetadataError, inspect_animation_file, inspect_bvh, inspect_gltf_animations,
)
from ucc.library.provenance import AssetPolicyError, LicensePolicy


BVH_SOURCE = """HIERARCHY
ROOT Hips
{
 OFFSET 0.0 0.0 0.0
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT Knee
 {
  OFFSET 0.0 -0.5 0.0
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site
  {
   OFFSET 0 -0.4 0
  }
 }
}
MOTION
Frames: 3
Frame Time: 0.0333333
0 0 0 0 0 0 0 0 0
1 0 0 0 0 0 0 0 0
2 0 0 0 0 0 0 0 0
"""


def synthetic_glb(document: dict) -> bytes:
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * ((4 - len(payload) % 4) % 4)
    body = struct.pack("<I4s", len(payload), b"JSON") + payload
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def animation_doc() -> dict:
    return {"asset": {"version": "2.0"}, "nodes": [
        {"name": "Hips", "children": [1]}, {"name": "Knee"}],
        "skins": [{"joints": [0, 1]}],
        "accessors": [
            {"type": "SCALAR", "count": 4, "min": [0], "max": [0.12]},
            {"type": "VEC4", "count": 4},
        ],
        "animations": [{"name": "Walk", "samplers": [{"input": 0, "output": 1}],
            "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}}]}],
    }


class AnimationIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "local_assets.db"
        self.bvh = self.root / "motion.bvh"
        self.bvh.write_text(BVH_SOURCE, encoding="utf-8")
        self.policy = LicensePolicy("Fab", "unreviewed", "https://example.org/private-animation",
                                    reviewed=False)

    def test_real_bvh_metadata_from_all_frames(self):
        result = inspect_bvh(self.bvh)
        self.assertEqual(result.status, "METADATA_EXTRACTED")
        self.assertEqual(result.format, "bvh")
        self.assertEqual(result.bone_names, ("Hips", "Knee"))
        self.assertEqual(result.clips[0].frame_count, 3)
        self.assertEqual(result.clips[0].track_count, 9)
        self.assertAlmostEqual(result.clips[0].duration_seconds, 0.1, places=4)
        self.assertEqual(len(result.skeleton_fingerprint), 64)
        self.assertFalse(result.to_dict()["retarget_verified"])

    def test_motion_frame_count_mismatch_is_rejected(self):
        self.bvh.write_text(BVH_SOURCE.replace("Frames: 3", "Frames: 4"))
        with self.assertRaisesRegex(AnimationMetadataError, "incomplete"):
            inspect_bvh(self.bvh)

    def test_malformed_channel_and_numeric_data_rejected(self):
        self.bvh.write_text(BVH_SOURCE.replace("CHANNELS 3", "CHANNELS 4"))
        with self.assertRaisesRegex(AnimationMetadataError, "channel declaration"):
            inspect_bvh(self.bvh)
        self.bvh.write_text(BVH_SOURCE.replace("1 0 0 0 0 0 0 0 0", "NaN 0 0 0 0 0 0 0 0"))
        with self.assertRaisesRegex(AnimationMetadataError, "finite"):
            inspect_bvh(self.bvh)

    def test_duplicate_joint_and_extra_frame_rejected(self):
        self.bvh.write_text(BVH_SOURCE.replace("JOINT Knee", "JOINT Hips"))
        with self.assertRaisesRegex(AnimationMetadataError, "duplicate"):
            inspect_bvh(self.bvh)
        self.bvh.write_text(BVH_SOURCE + "1 2 3 4 5 6 7 8 9\n")
        with self.assertRaisesRegex(AnimationMetadataError, "Extra"):
            inspect_bvh(self.bvh)

    def test_no_external_file_or_symlink_discovery(self):
        link = self.root / "linked.bvh"
        try:
            link.symlink_to(self.bvh)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(AnimationMetadataError, "non-symlink"):
            inspect_animation_file(link)

    def test_valid_gltf_metadata_with_animation_duration(self):
        gltf = self.root / "motion.gltf"
        gltf.write_text(json.dumps(animation_doc()))
        result = inspect_animation_file(gltf)
        self.assertEqual(result.format, "gltf")
        self.assertEqual(result.clips[0].name, "Walk")
        self.assertEqual(result.clips[0].animated_bones, ("Knee",))
        self.assertEqual(result.clips[0].duration_seconds, 0.12)
        self.assertIsNone(result.clips[0].fps)
        self.assertIn("External glTF buffers not loaded or verified", result.warnings)

    def test_glb_animation_metadata_read_only(self):
        glb = self.root / "motion.glb"
        glb.write_bytes(synthetic_glb(animation_doc()))
        result = inspect_animation_file(glb)
        self.assertEqual(result.status, "METADATA_EXTRACTED")
        self.assertEqual(len(result.clips), 1)
        self.assertFalse(result.to_dict()["preview_verified"])

    def test_gltf_time_bound_missing_not_invented(self):
        doc = animation_doc()
        doc["accessors"][0].pop("max")
        result = inspect_gltf_animations(doc, "gltf")
        self.assertIsNone(result.clips[0].duration_seconds)
        self.assertTrue(any("unknown" in w for w in result.clips[0].warnings))

    def test_invalid_gltf_indices_and_tracks_rejected(self):
        doc = animation_doc()
        doc["animations"][0]["channels"][0]["sampler"] = 99
        with self.assertRaisesRegex(AnimationMetadataError, "sampler"):
            inspect_gltf_animations(doc, "gltf")
        doc = animation_doc()
        doc["animations"][0]["channels"][0]["target"]["path"] = "execute"
        with self.assertRaisesRegex(AnimationMetadataError, "Unsupported"):
            inspect_gltf_animations(doc, "gltf")

    def test_reject_parent_collision_and_bad_time(self):
        doc = animation_doc()
        doc["nodes"].append({"name": "DuplicateParent", "children": [1]})
        with self.assertRaisesRegex(AnimationMetadataError, "multiple parents"):
            inspect_gltf_animations(doc, "gltf")
        doc = animation_doc()
        doc["accessors"][0]["max"] = [float("nan")]
        with self.assertRaisesRegex(AnimationMetadataError, "finite"):
            inspect_gltf_animations(doc, "gltf")

    def test_fbx_and_uasset_are_unparsed_not_false_success(self):
        for extension in (".fbx", ".uasset"):
            source = self.root / ("test" + extension)
            source.write_bytes(b"fixture_not_actual_animation")
            result = inspect_animation_file(source)
            self.assertEqual(result.status, "REQUIRES_CONVERSION")
            self.assertEqual(len(result.clips), 0)
            self.assertFalse(result.to_dict()["engine_validated"])

    def test_index_unreviewed_policy_and_reopen(self):
        with AnimationCatalog(self.db_path) as catalog:
            result = catalog.index_file("owned-01", self.bvh, self.policy)
            self.assertEqual(result.status, "METADATA_EXTRACTED")
            self.assertEqual(len(result.clips), 1)
            self.assertEqual(catalog.index_file("owned-01", self.bvh, self.policy).sha256, result.sha256)
            self.assertIn("BLOCKED", result.rights["godot"])
            self.assertIn("BLOCKED", result.rights["ai_input"])
            self.assertEqual(len(catalog.list_sources()), 1)
        with AnimationCatalog(self.db_path) as catalog:
            result = catalog.get("owned-01")
            self.assertEqual(result.clips[0].name, "motion")
            self.assertEqual(result.bone_names, ("Hips", "Knee"))
            with self.assertRaises(AssetPolicyError):
                catalog.library.require_permission("owned-01", "engine_export", "unity")

    def test_known_reviewed_policy_approved_engine_but_not_AI(self):
        policy = LicensePolicy("owner", "custom", "https://example.org/copyright",
                               reviewed=True, can_use_non_unreal=True, can_use_unreal=True)
        with AnimationCatalog(self.db_path) as catalog:
            result = catalog.index_file("a", self.bvh, policy)
            self.assertEqual(result.rights["godot"], "allowed_by_reviewed_policy")
            self.assertIn("BLOCKED", result.rights["ai_input"])
            self.assertIn("BLOCKED", result.rights["ship_source"])

    def test_preserves_existing_v1_asset_library(self):
        from ucc.library.provenance import AssetLibrary
        with AssetLibrary(self.db_path) as library:
            library.register("original", self.bvh, self.policy)
        with AnimationCatalog(self.db_path) as catalog:
            self.assertIsNotNone(catalog.library.get("original"))
            catalog.index_file("index-now", self.bvh, self.policy)
        with AssetLibrary(self.db_path) as library:
            self.assertEqual(library.db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(len(library.list_assets()), 2)

    def test_malformed_file_does_not_create_catalog_rows(self):
        self.bvh.write_text("Not BVH\n")
        with AnimationCatalog(self.db_path) as catalog:
            with self.assertRaises(AnimationMetadataError):
                catalog.index_file("bad", self.bvh, self.policy)
            self.assertEqual(catalog.list_sources(), ())
            self.assertIsNone(catalog.library.get("bad"))

    def test_same_source_id_cannot_change_bytes_or_permission(self):
        with AnimationCatalog(self.db_path) as catalog:
            catalog.index_file("pinned", self.bvh, self.policy)
            self.bvh.write_text(BVH_SOURCE.replace("Frames: 3", "Frames: 2").replace(
                "2 0 0 0 0 0 0 0 0\n", ""))
            with self.assertRaises(AssetPolicyError):
                catalog.index_file("pinned", self.bvh, self.policy)
            self.assertEqual(len(catalog.get("pinned").clips), 1)

    def test_license_must_remain_exact_for_same_asset(self):
        with AnimationCatalog(self.db_path) as catalog:
            catalog.index_file("fixed-policy", self.bvh, self.policy)
            new_policy = LicensePolicy("Fab", "unreviewed", "https://example.org/private-animation",
                                       reviewed=True)
            with self.assertRaises(AssetPolicyError):
                catalog.index_file("fixed-policy", self.bvh, new_policy)

    def test_catalog_output_is_private_metadata_not_motion_bytes(self):
        with AnimationCatalog(self.db_path) as catalog:
            report = catalog.index_file("safe", self.bvh, self.policy).to_dict()
            self.assertNotIn(str(self.root), json.dumps(report))
            self.assertFalse(report["engine_validated"])
            self.assertEqual(report["clips"][0]["track_count"], 9)


if __name__ == "__main__":
    unittest.main()


class AnimationCLITests(unittest.TestCase):
    def test_inspect_and_index_without_private_source_disclosure(self):
        import contextlib
        import io
        from ucc.cli import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "walk.bvh"
            file.write_text(BVH_SOURCE)
            database = root / "private.db"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["inspect-animation", str(file)]), 0)
            self.assertEqual(json.loads(output.getvalue())["clips"][0]["frame_count"], 3)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["index-animation", str(file), "--database", str(database),
                                       "--asset-id", "walk01", "--provider", "Fab",
                                       "--license-name", "unreviewed", "--source-uri", "https://fab.com/listing/abc"]), 0)
            data = json.loads(output.getvalue())
            self.assertNotIn(directory, json.dumps(data))
            self.assertEqual(data["status"], "METADATA_EXTRACTED")
            self.assertEqual(data["permissions"]["godot"].split(":")[0], "BLOCKED")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["list-animations", "--database", str(database)]), 0)
            self.assertEqual(len(json.loads(output.getvalue())), 1)

    def test_cannot_claim_reviewed_rights_without_matching_policy(self):
        import contextlib
        import io
        from ucc.cli import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "walk.bvh"
            file.write_text(BVH_SOURCE)
            policy = root / "license.json"
            policy.write_text(json.dumps(LicensePolicy("Fab", "unreviewed", "https://source.invalid",
                                                        reviewed=True, can_use_unreal=True).to_dict()))
            with contextlib.redirect_stderr(io.StringIO()):
                result = main(["index-animation", str(file), "--database", str(root / "db.sqlite"),
                               "--asset-id", "walk", "--provider", "Fab", "--license-name", "unreviewed",
                               "--source-uri", "https://different.invalid", "--policy-file", str(policy)])
            self.assertEqual(result, 2)
