"""Pure-Python fake-bpy contract checks, NOT actual Blender/glTF proof."""
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

    def select_set(self, value):
        self.selected = value

    def hide_set(self, value):
        self.hidden = value


class FakeBlender:
    def __init__(self, meshes, result={"FINISHED"}):
        self.objects = meshes
        self.result = result
        self.calls = []
        self.app = SimpleNamespace(version_string="5.3.0")
        self.context = SimpleNamespace(
            scene=SimpleNamespace(objects=meshes),
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=None)),
        )
        self.ops = SimpleNamespace(
            wm=SimpleNamespace(open_mainfile=self.open_file),
            export_scene=SimpleNamespace(gltf=self.export),
        )

    def open_file(self, **kw):
        self.calls.append(("open", kw))

    def export(self, **kw):
        self.calls.append(("export", kw))
        Path(kw["filepath"]).write_bytes(b"glTF" + b"synthetic-preview-only" * 20)
        return self.result


class StaticPreviewExportContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "saved.blend"
        self.source.write_bytes(b"BLENDER" + b"synthetic" * 20)
        self.output = self.root / "preview.glb"

    def test_selects_real_substantial_mesh_only_and_never_saves_source(self):
        cube = FakeMesh("startup cube", 8)
        body = FakeMesh("human body", 19158)
        blender = FakeBlender([cube, body])
        unchanged = self.source.read_bytes()
        result = export_static_glb(blender, self.source, self.output)
        self.assertEqual(result["selected_vertex_count"], 19158)
        self.assertEqual(result["selected_mesh_count"], 1)
        self.assertEqual(result["blender_version"], "5.3.0")
        self.assertFalse(result["engine_import_verified"])
        self.assertEqual(self.source.read_bytes(), unchanged)
        self.assertFalse(cube.selected)
        self.assertTrue(body.selected)
        self.assertFalse(body.hidden)
        self.assertEqual(blender.calls[0][0], "open")
        options = blender.calls[-1][1]
        self.assertEqual(options["export_format"], "GLB")
        self.assertTrue(options["use_selection"])
        self.assertEqual(options["export_materials"], "NONE")
        for flag in ("export_skins", "export_animations", "export_morph",
                     "export_cameras", "export_lights", "export_texcoords"):
            self.assertFalse(options[flag])

    def test_missing_body_or_excessive_vertices_rejected_before_export(self):
        for meshes in ([FakeMesh("cube", 8)],
                       [FakeMesh("huge", 250001)]):
            with self.subTest(count=len(meshes[0].data.vertices)):
                b = FakeBlender(meshes)
                with self.assertRaisesRegex(PreviewExportError, "substantial"):
                    export_static_glb(b, self.source, self.output)
                self.assertFalse(any(call[0] == "export" for call in b.calls))

    def test_existing_output_not_overwritten(self):
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
