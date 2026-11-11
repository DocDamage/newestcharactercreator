"""Original test-only BVH fixtures; no user, Fab or third-party animation data."""
from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

from blender_bridge.bvh_motion import LocalBvhError, read_local_bvh


def write_original_bvh(path: Path, frames: int = 25, *, joint: str = "head") -> None:
    root = (
        f"HIERARCHY\nROOT {joint}\n{{\nOFFSET 0 0 0\n"
        "CHANNELS 3 Xrotation Yrotation Zrotation\n"
        "End Site\n{\nOFFSET 0 0.1 0\n}\n}\n"
        f"MOTION\nFrames: {frames}\nFrame Time: 0.041666667\n"
    )
    rows = [
        f"{20 * math.sin(math.pi * i / (frames - 1)):.7f} 0 0"
        for i in range(frames)
    ]
    path.write_text(root + "\n".join(rows) + "\n", encoding="utf-8")


class BvhRotationParserContracts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "ci-original.bvh"
        write_original_bvh(self.path)

    def test_local_original_bvh_parses_real_frame_values(self):
        parsed = read_local_bvh(self.path)
        self.assertEqual(parsed.frames, 25)
        self.assertAlmostEqual(parsed.frame_time, 1 / 24, places=6)
        src, dst, rotations = parsed.eligible_rotation(["head", "neck"])
        self.assertEqual((src, dst), ("head", "head"))
        self.assertEqual(len(rotations), 25)
        self.assertAlmostEqual(rotations[0][0], 0)
        self.assertAlmostEqual(rotations[12][0], 20, places=3)
        self.assertAlmostEqual(rotations[-1][0], 0)

    def test_reject_mismatched_bone_and_no_automatic_aliases(self):
        parsed = read_local_bvh(self.path)
        with self.assertRaisesRegex(LocalBvhError, "no automatic retarget"):
            parsed.eligible_rotation(["UpperArm", "spine"])
        with self.assertRaisesRegex(LocalBvhError, "ambiguous"):
            parsed.eligible_rotation(["Head", "head"])

    def test_reject_missing_frame_and_nonfinite_motion(self):
        raw = self.path.read_text()
        self.path.write_text(raw + "0 0 0\n", encoding="utf-8")
        with self.assertRaisesRegex(LocalBvhError, "motion rows"):
            read_local_bvh(self.path)
        self.path.write_text(raw.replace("20.0000000 0 0", "nan 0 0"), encoding="utf-8")
        with self.assertRaisesRegex(LocalBvhError, "non-finite"):
            read_local_bvh(self.path)

    def test_reject_unsafe_large_rotation_and_unsupported_speed(self):
        raw = self.path.read_text()
        self.path.write_text(raw.replace("20.0000000 0 0", "700 0 0"), encoding="utf-8")
        with self.assertRaises(LocalBvhError):
            read_local_bvh(self.path)
        self.path.write_text(raw.replace("Frame Time: 0.041666667", "Frame Time: 0"), encoding="utf-8")
        with self.assertRaisesRegex(LocalBvhError, "timing"):
            read_local_bvh(self.path)

    def test_reject_redirected_file_before_read(self):
        alias = self.path.with_name("link.bvh")
        try:
            alias.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest("OS cannot create symlink")
        with self.assertRaisesRegex(LocalBvhError, "regular"):
            read_local_bvh(alias)


if __name__ == "__main__":
    unittest.main()
