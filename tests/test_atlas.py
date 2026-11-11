"""Generated test pixels validate atlas mechanics; no product artwork is shipped."""
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.sprites.plan import CameraProfile, build_plan
from ucc.sprites.atlas import AtlasError, pack_frames

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow optional dependency not installed")
class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.frames = self.root / "frames"
        self.frames.mkdir()
        self.output = self.root / "export"
        self.plan = build_plan({"idle": 2}, CameraProfile(directions=4), width=64, height=64)

    def create_frames(self, plan=None, mode="RGBA"):
        plan = plan or self.plan
        for frame in plan.frames:
            path = self.frames / frame.file_name
            path.parent.mkdir(parents=True, exist_ok=True)
            if mode == "RGBA":
                image = Image.new("RGBA", (plan.width, plan.height), (0, 0, 0, 0))
                for x in range(6, 40):
                    for y in range(4, 42):
                        image.putpixel((x, y), (210, 50, 150, 255))
            else:
                image = Image.new("RGB", (plan.width, plan.height), (255, 0, 0))
            image.save(path)
            image.close()

    def test_pack_real_rgba_files_and_manifest_positions(self):
        self.create_frames()
        result = pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)
        self.assertEqual(result.frame_count, 8)
        self.assertEqual(result.sheet_files, ("sprite_sheet_000.png",))
        manifest = json.loads((self.output / result.manifest).read_text())
        self.assertEqual(manifest["frame_count"], 8)
        self.assertEqual(len(manifest["frames"]), 8)
        self.assertEqual(len({(f["rect"]["x"], f["rect"]["y"]) for f in manifest["frames"]}), 8)
        self.assertEqual(manifest["alpha"], "straight_rgba")
        with Image.open(self.output / result.sheet_files[0]) as sheet:
            self.assertEqual(sheet.mode, "RGBA")
            self.assertEqual(sheet.size, (256, 128))
            self.assertEqual(sheet.getpixel((6, 4)), (210, 50, 150, 255))
            self.assertEqual(sheet.getpixel((0, 0))[3], 0)

    def test_multiple_pages_no_overwrite(self):
        plan = build_plan({"walk": 6}, CameraProfile(directions=2), width=128, height=128)
        self.create_frames(plan)
        result = pack_frames(plan, self.frames, self.output, max_sheet_side=256)
        self.assertEqual(len(result.sheet_files), 3)
        with self.assertRaisesRegex(AtlasError, "already exists"):
            pack_frames(plan, self.frames, self.output, max_sheet_side=256)

    def test_missing_frame_fails_before_publishing(self):
        self.create_frames()
        (self.frames / self.plan.frames[-1].file_name).unlink()
        with self.assertRaisesRegex(AtlasError, "Missing"):
            pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)
        self.assertEqual(list(self.output.glob("sprite_sheet_*.png")), [])
        self.assertFalse((self.output / "sprite_atlas.json").exists())

    def test_wrong_resolution_fails(self):
        self.create_frames()
        frame = self.frames / self.plan.frames[0].file_name
        Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(frame)
        with self.assertRaisesRegex(AtlasError, "Wrong size"):
            pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)

    def test_rgb_without_alpha_rejected(self):
        self.create_frames(mode="RGB")
        with self.assertRaisesRegex(AtlasError, "no alpha"):
            pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)

    def test_publish_failure_rolls_back_all_outputs(self):
        self.create_frames()
        original_replace = __import__("os").replace
        called = 0
        def fail_second(source, target):
            nonlocal called
            called += 1
            if called == 2:
                raise OSError("injected publication failure")
            return original_replace(source, target)
        with patch("ucc.sprites.atlas.os.replace", side_effect=fail_second):
            with self.assertRaises(OSError):
                pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)
        self.assertFalse((self.output / "sprite_sheet_000.png").exists())
        self.assertFalse((self.output / "sprite_atlas.json").exists())
        self.assertEqual(list(self.output.glob(".ucc-atlas-staging-*")), [])

    def test_blank_frame_requires_explicit_opt_in(self):
        self.create_frames()
        Image.new("RGBA", (64,64), (0,0,0,0)).save(self.frames / self.plan.frames[0].file_name)
        with self.assertRaisesRegex(AtlasError, "Fully transparent"):
            pack_frames(self.plan, self.frames, self.output, max_sheet_side=256)
        self.assertEqual(pack_frames(self.plan, self.frames, self.output,
                                     max_sheet_side=256, allow_blank=True).frame_count, 8)


@unittest.skipIf(Image is None, "Pillow optional dependency not installed")
class AtlasCLITests(unittest.TestCase):
    def test_cli_pack_png_images(self):
        from ucc.cli import main
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            for d in range(2):
                p = root / "frames" / "idle" / f"dir-{d:02d}" / "frame-0000.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (32,32), (255,0,0,255)).save(p)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["pack-sprites", "--frames-dir", str(root/"frames"),
                           "--output-dir", str(root/"out"), "--directions", "2",
                           "--width", "32", "--height", "32", "--clip", "idle:1"])
            self.assertEqual(rc, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["frame_count"], 2)
            self.assertTrue((root/"out"/data["manifest"]).is_file())
