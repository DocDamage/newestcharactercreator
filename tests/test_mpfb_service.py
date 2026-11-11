"""Contract tests using synthetic Blender/MPFB stubs, not real geometry proof."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_bridge.mpfb_service import (
    MpfbServiceError, BUILTIN_RIGS, locate_human_service, inspect_service, create_human_with_rig,
)


class Obj:
    _next = 0

    def __init__(self, name: str, kind: str, count: int):
        Obj._next += 1
        self._ptr = Obj._next
        self.type, self.name = kind, name
        self.data = SimpleNamespace(vertices=[0] * count if kind == "MESH" else [],
                                    bones=[SimpleNamespace(name=f"B{i}") for i in range(count)]
                                    if kind == "ARMATURE" else [], shape_keys=None)

    def as_pointer(self):
        return self._ptr


class FakeService:
    def __init__(self, context):
        self.ctx = context
        self.fail_rig = False
        self.fail_base = False

    def create_human(self):
        if self.fail_base:
            raise RuntimeError("Failed")
        obj = Obj("UCC_Human", "MESH", 2000)
        self.ctx.data.objects.append(obj)
        return obj

    def add_builtin_rig(self, base, rig_name):
        if self.fail_rig:
            raise RuntimeError("No rig")
        obj = Obj("HumanRig", "ARMATURE", 65)
        self.ctx.data.objects.append(obj)
        return obj


class MpfbServiceTests(unittest.TestCase):
    def setUp(self):
        self.bpy = SimpleNamespace(data=SimpleNamespace(objects=[Obj("startup cube", "MESH", 8)]))
        self.service = FakeService(self.bpy)

    def test_discover_loaded_module(self):
        registry = {"bl_ext.user_default.mpfb.services.humanservice": object()}
        s, module = locate_human_service(registry, lambda name: SimpleNamespace(HumanService=FakeService))
        self.assertIs(s, FakeService)
        self.assertIn("bl_ext.user_default", module)

    def test_discover_package_only(self):
        registry = {"bl_ext.blender_org.mpfb": object()}
        calls = []
        def load(name):
            calls.append(name)
            return SimpleNamespace(HumanService=FakeService)
        _, name = locate_human_service(registry, load)
        self.assertEqual(calls, ["bl_ext.blender_org.mpfb.services.humanservice"])
        self.assertEqual(name, calls[0])

    def test_empty_modules_report_missing(self):
        report = inspect_service({}, lambda n: None)
        self.assertFalse(report["available"])
        self.assertIn("Enable MPFB", report["error"])

    def test_ambiguous_extension_fail_closed(self):
        packages = {"bl_ext.user_default.mpfb": object(), "bl_ext.blender_org.mpfb": object()}
        with self.assertRaisesRegex(MpfbServiceError, "exactly one"):
            locate_human_service(packages, lambda name: None)
        services = {x + ".services.humanservice": object() for x in packages}
        with self.assertRaisesRegex(MpfbServiceError, "Multiple"):
            locate_human_service(services, lambda name: None)

    def test_missing_service_methods(self):
        with self.assertRaisesRegex(MpfbServiceError, "API missing"):
            locate_human_service({"mpfb": object()}, lambda name: SimpleNamespace(HumanService=object))

    def test_create_human_and_rig_real_service_contract(self):
        result = create_human_with_rig(self.bpy, self.service, "game_engine")
        self.assertEqual(result["method"], "HumanService")
        self.assertEqual(result["new_mesh_vertices"], [2000])
        self.assertEqual(result["rigs"][0]["bone_count"], 65)
        self.assertFalse(result["verified_reopen"])
        self.assertFalse(result["visual_deformation_verified"])
        self.assertEqual(len(self.bpy.data.objects), 3)

    def test_defaults_use_toe_rig(self):
        self.assertIn("default", BUILTIN_RIGS)
        self.assertEqual(create_human_with_rig(self.bpy, self.service)["rig_choice"], "default")

    def test_no_extra_unapproved_rigs(self):
        with self.assertRaisesRegex(MpfbServiceError, "Unapproved"):
            create_human_with_rig(self.bpy, self.service, "some_custom_rig")
        self.assertEqual(len(self.bpy.data.objects), 1)

    def test_service_create_failure(self):
        self.service.fail_base = True
        with self.assertRaisesRegex(MpfbServiceError, "create_human"):
            create_human_with_rig(self.bpy, self.service)

    def test_service_rig_failure(self):
        self.service.fail_rig = True
        with self.assertRaisesRegex(MpfbServiceError, "rig creation failed"):
            create_human_with_rig(self.bpy, self.service)

    def test_insufficient_geometry(self):
        def bad_base():
            x = Obj("Tiny", "MESH", 3)
            self.bpy.data.objects.append(x)
            return x
        self.service.create_human = bad_base
        with self.assertRaisesRegex(MpfbServiceError, "insufficient geometry"):
            create_human_with_rig(self.bpy, self.service)

    def test_insufficient_rig(self):
        def tiny_rig(base, rig_name):
            x = Obj("tinyrig", "ARMATURE", 3)
            self.bpy.data.objects.append(x)
            return x
        self.service.add_builtin_rig = tiny_rig
        with self.assertRaisesRegex(MpfbServiceError, "insufficient bones"):
            create_human_with_rig(self.bpy, self.service)


if __name__ == "__main__":
    unittest.main()
