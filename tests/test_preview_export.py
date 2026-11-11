"""Synthetic-bpy tests: static GLB export must bake evaluated geometry.

Not Blender integration proof; actual MPFB glTF comparison runs in separate CI.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from blender_bridge.preview_export import PreviewExportError, export_static_glb


class FakeMesh:
    def __init__(self, name: str, vertices: int):
        self.name, self.type = name, "MESH"
        self.data = SimpleNamespace(vertices=[None] * vertices)
        self.selected = None
        self.hidden = True
        self.matrix_world = SimpleNamespace(copy=lambda: ("copied-world-transform", name))
        self.evaluated = False

    def select_set(self, value):
        self.selected = value

    def hide_set(self, value):
        self.hidden = value

    def evaluated_get(self, graph):
        self.evaluated = True
        return self


class FakeBlender:
    def __init__(self, meshes, result={"FINISHED"}):
        self.objects = list(meshes)
        self.baked = []
        self.result = result
        self.calls = []
        self.app = SimpleNamespace(version_string="5.3.0")
        self.data = SimpleNamespace(
            meshes=SimpleNamespace(
                new_from_object=self.new_from_object,
                remove=lambda mesh: None,
            ),
            objects=SimpleNamespace(new=self.new_object),
        )
        scene = SimpleNamespace(
            objects=self.objects,
            collection=SimpleNamespace(
                objects=SimpleNamespace(link=lambda obj: self.objects.append(obj))
            ),
        )
        self.context = SimpleNamespace(
            scene=scene,
            view_layer=SimpleNamespace(
                objects=SimpleNamespace(active=None),
                update=lambda: None,
            ),
            evaluated_depsgraph_get=lambda: "fake-depsgraph",
        )
        self.ops = SimpleNamespace(
            wm=SimpleNamespace(open_mainfile=self.open_file),
            export_scene=SimpleNamespace(gltf=self.export),
        )

    def new_from_object(self, evaluated, **kwargs):
        self.calls.append(("bake", kwargs))
        self.baked.append(evaluated)
        return SimpleNamespace(vertices=list(evaluated.data.vertices))

    def new_object(self, name, mesh):
        result = FakeMesh(name, len(mesh.vertices))
        result.data = mesh
        return result

    def open_file(self, **kwargs):
        self.calls.append(("open", kwargs))

    def export(self, **kwargs):
        self.calls.append(("export", kwargs))
        Path(kwargs["filepath"]).write_bytes(b"glTF" + b"synthetic-preview-only" * 20)
        return self.result


class StaticPreviewExportContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "saved.blend"
        self.source.write_bytes(b"BLENDER" + b"synthetic" * 20)
        self.output = self.root / "preview.glb"

    def test_static_glb_uses_evaluated_geometry_not_original_shape_keys(self):
        cube = FakeMesh("startup cube", 8)
        body = FakeMesh("human body", 19158)
        blender = FakeBlender([cube, body])
        unchanged = self.source.read_bytes()
        result = export_static_glb(blender, self.source, self.output)
        self.assertEqual(result["selected_vertex_count"], 19158)
        self.assertEqual(result["selected_mesh_count"], 1)
        self.assertTrue(result["evaluated_geometry_baked"])
        self.assertEqual(result["blender_version"], "5.3.0")
        self.assertFalse(result["engine_import_verified"])
        self.assertEqual(self.source.read_bytes(), unchanged)
        self.assertFalse(cube.selected)
        self.assertFalse(body.selected)
        self.assertTrue(body.evaluated)
        self.assertIs(blender.baked[0], body)
        temporary = blender.context.view_layer.objects.active
        self.assertIsNot(temporary, body)
        self.assertTrue(temporary.selected)
        self.assertFalse(temporary.hidden)
        self.assertEqual(temporary.matrix_world,
                         ("copied-world-transform", "human body"))
        self.assertEqual(blender.calls[0][0], "open")
        self.assertEqual(blender.calls[-2][0], "bake")
        settings = blender.calls[-1][1]
        self.assertEqual(settings["export_format"], "GLB")
        self.assertTrue(settings["use_selection"])
        self.assertEqual(settings["export_materials"], "NONE")
        for flag in ("export_skins", "export_animations", "export_morph",
                     "export_cameras", "export_lights", "export_texcoords"):
            self.assertFalse(settings[flag])

    def test_missing_body_or_excessive_vertices_rejected_before_export(self):
        for meshes in ([FakeMesh("cube", 8)],
                       [FakeMesh("huge", 250001)]):
            with self.subTest(count=len(meshes[0].data.vertices)):
                b = FakeBlender(meshes)
                with self.assertRaisesRegex(PreviewExportError, "substantial"):
                    export_static_glb(b, self.source, self.output)
                self.assertFalse(any(call[0] == "export" for call in b.calls))

    def test_existing_output_never_overwritten(self):
        self.output.write_bytes(b"existing user data")
        with self.assertRaisesRegex(PreviewExportError, "new regular"):
            export_static_glb(FakeBlender([FakeMesh("human", 200)]),
                              self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing user data")

    def test_failed_export_does_not_claim_success(self):
        b = FakeBlender([FakeMesh("human", 200)], result={"CANCELLED"})
        with self.assertRaisesRegex(PreviewExportError, "did not finish"):
            export_static_glb(b, self.source, self.output)

    def test_reject_source_symlink(self):
        linked = self.root / "redirect.blend"
        try:
            linked.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported")
        with self.assertRaisesRegex(PreviewExportError, "regular staged"):
            export_static_glb(FakeBlender([FakeMesh("human", 200)]),
                              linked, self.output)


if __name__ == "__main__":
    unittest.main()
