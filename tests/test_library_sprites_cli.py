import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.cli import main
from ucc.core.errors import ValidationError
from ucc.library.provenance import AssetLibrary, AssetPolicyError, LicensePolicy
from ucc.sprites.plan import CameraProfile, build_plan


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / "external.fbx"
        self.asset.write_bytes(b"test fixture metadata only")

    def test_unknown_license_blocks_every_use_except_inventory(self):
        policy = LicensePolicy("Fab", "not yet reviewed", "https://example.com")
        with AssetLibrary(self.root / "index.db") as library:
            entry = library.register("sample-clip", self.asset, policy)
            self.assertEqual(entry.size_bytes, self.asset.stat().st_size)
            library.require_permission("sample-clip", "inventory")
            for op, target in (("engine_export", "unreal"), ("ai_input", None), ("ship_source", None)):
                with self.assertRaises(AssetPolicyError):
                    library.require_permission("sample-clip", op, target)
        with AssetLibrary(self.root / "index.db") as library:
            self.assertEqual(library.get("sample-clip").sha256, entry.sha256)

    def test_explicit_reviewed_engine_permissions(self):
        policy = LicensePolicy("owner", "Custom", "https://example.com", reviewed=True,
                               can_use_non_unreal=True, can_use_unreal=True, ai_input_allowed=False)
        with AssetLibrary(self.root / "index.db") as library:
            library.register("clip", self.asset, policy)
            library.require_permission("clip", "engine_export", "godot")
            with self.assertRaises(AssetPolicyError):
                library.require_permission("clip", "ai_input")
            with self.assertRaises(AssetPolicyError):
                library.require_permission("clip", "ship_source")
            library.require_permission("clip", "engine_export", "unreal")

    def test_ue_only_blocks_cross_engine(self):
        policy = LicensePolicy("Fab", "UE only", "https://example.com", reviewed=True,
                               ue_only=True, can_use_non_unreal=False, can_use_unreal=True)
        with AssetLibrary(self.root / "index.db") as library:
            library.register("ue", self.asset, policy)
            library.require_permission("ue", "engine_export", "unreal")
            with self.assertRaises(AssetPolicyError):
                library.require_permission("ue", "engine_export", "unity")

    def test_reusing_id_for_different_files_is_blocked(self):
        policy = LicensePolicy("owner", "Custom", "https://example.com")
        with AssetLibrary(self.root / "index.db") as library:
            library.register("clip", self.asset, policy)
            self.asset.write_bytes(b"altered contents")
            with self.assertRaises(AssetPolicyError):
                library.register("clip", self.asset, policy)


class SpriteTests(unittest.TestCase):
    def test_render_plan_deterministic_not_claim_render(self):
        cam = CameraProfile(directions=8, pitch_deg=25)
        first = build_plan({"walk": 4, "idle": 2}, cam, width=64, height=128, fps=12).to_dict()
        second = build_plan({"idle": 2, "walk": 4}, cam, width=64, height=128, fps=12).to_dict()
        self.assertEqual(first, second)
        self.assertFalse(first["rendered"])
        self.assertEqual(len(first["frames"]), 48)
        self.assertEqual(len({x["file_name"] for x in first["frames"]}), 48)
        self.assertEqual(first["camera"]["angles"], list(cam.angles()))

    def test_custom_angles(self):
        cam = CameraProfile(directions=3, custom_yaws=(10., 20., 280.))
        self.assertEqual(cam.angles(), (10., 20., 280.))
        with self.assertRaises(ValidationError):
            CameraProfile(directions=8, custom_yaws=(0.,))

    def test_reject_expensive_or_unsafe_plans(self):
        cam = CameraProfile(directions=16)
        with self.assertRaises(ValidationError):
            build_plan({"run": 1000}, cam)
        with self.assertRaises(ValidationError):
            build_plan({"a/../../b": 1}, cam)
        with self.assertRaises(ValidationError):
            build_plan({"walk": 2}, cam, width=0)


class CLITests(unittest.TestCase):
    def test_metadata_init_info_morph(self):
        with tempfile.TemporaryDirectory() as directory:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["new", directory, "--name", "Draft Zero"]), 0)
            self.assertEqual(json.loads(out.getvalue())["geometry_state"], "not_generated")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["morph", directory, "height", "0.6"]), 0)
            self.assertEqual(json.loads(out.getvalue())["revision"], 2)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["info", directory]), 0)
            self.assertIn("Master geometry has not passed", out.getvalue())

    def test_cli_sprite_plan_only(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["plan-sprites", "--directions", "4", "--clip", "idle:3"]), 0)
        self.assertEqual(len(json.loads(out.getvalue())["frames"]), 12)
