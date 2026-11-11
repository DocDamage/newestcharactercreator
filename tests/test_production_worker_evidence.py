"""Synthetic contract tests only; no fabricated Blender/MPFB integration proof."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
from verify_production_worker import EvidenceError, verify_geometry


def created() -> dict:
    return {
        "method": "HumanService", "rig_choice": "default",
        "blender_version": "5.3.0",
        "created_meshes": [{"name": "Human", "vertex_count": 18000}],
        "rigs": [{"name": "HumanRig", "bone_count": 65}],
    }


def inspected() -> dict:
    return {
        "blender_version": "5.3.0",
        "mesh_count": 1, "vertex_count": 18000,
        "armatures": [{"name": "HumanRig", "bone_count": 65}],
    }


class ProductionWorkerEvidenceTests(unittest.TestCase):
    def test_valid_reopen_maintains_geometry(self):
        stats = verify_geometry(created(), inspected())
        self.assertEqual(stats["created_vertex_count"], 18000)
        self.assertEqual(stats["reopened_bone_count"], 65)
        self.assertEqual(stats["blender_version"], "5.3.0")

    def test_only_real_mpfb_service_is_eligible(self):
        for change in ({"method": "fake"}, {"rig_choice": "none"}):
            with self.subTest(change=change):
                bad = {**created(), **change}
                with self.assertRaises(EvidenceError):
                    verify_geometry(bad, inspected())

    def test_empty_or_tiny_created_mesh_does_not_pass(self):
        for meshes in ([], None, [{"vertex_count": 100}], [{"vertex_count": True}]):
            with self.subTest(meshes=meshes):
                bad = {**created(), "created_meshes": meshes}
                with self.assertRaises(EvidenceError):
                    verify_geometry(bad, inspected())

    def test_missing_created_rig_does_not_pass(self):
        for rigs in ([], None, [{"bone_count": 4}], [{"bone_count": True}]):
            with self.subTest(rigs=rigs):
                bad = {**created(), "rigs": rigs}
                with self.assertRaises(EvidenceError):
                    verify_geometry(bad, inspected())

    def test_invalid_reopened_mesh_does_not_pass(self):
        for value in (0, 100, True, None):
            with self.subTest(value=value):
                bad = {**inspected(), "vertex_count": value}
                with self.assertRaises(EvidenceError):
                    verify_geometry(created(), bad)

    def test_missing_reopened_rig_does_not_pass(self):
        for armatures in ([], None, [{"bone_count": 4}], [{"bone_count": "65"}]):
            with self.subTest(armatures=armatures):
                bad = {**inspected(), "armatures": armatures}
                with self.assertRaises(EvidenceError):
                    verify_geometry(created(), bad)

    def test_reopen_must_preserve_both_vertices_and_bones(self):
        for change in ({"vertex_count": 17999},
                       {"armatures": [{"bone_count": 64}]}):
            with self.subTest(change=change):
                bad = {**inspected(), **change}
                with self.assertRaisesRegex(EvidenceError, "lost"):
                    verify_geometry(created(), bad)

    def test_reopen_must_use_same_blender_version(self):
        for version in ("5.2.0", "", None):
            with self.subTest(version=version):
                bad = {**inspected(), "blender_version": version}
                with self.assertRaisesRegex(EvidenceError, "versions differ"):
                    verify_geometry(created(), bad)

    def test_missing_creation_version_does_not_pass(self):
        bad = copy.deepcopy(created())
        bad["blender_version"] = ""
        with self.assertRaises(EvidenceError):
            verify_geometry(bad, inspected())


if __name__ == "__main__":
    unittest.main()
