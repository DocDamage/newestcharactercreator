"""These are synthetic GLB *structural fixtures*, not actual Blender exports."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.export.inspect_glb import inspect_glb, GLBInspectionError


def encode_glb(doc, binchunk=None):
    content = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    content += b" " * ((4 - len(content) % 4) % 4)
    body = struct.pack("<I4s", len(content), b"JSON") + content
    if binchunk is not None:
        binchunk += b"\0" * ((4 - len(binchunk) % 4) % 4)
        body += struct.pack("<I4s", len(binchunk), b"BIN\0") + binchunk
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


def structure():
    # Not an artist-created 3D model, and not a complete glTF conformance fixture.
    return {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 12}],
            "nodes": [{"mesh": 0, "skin": 0}, {"name": "root-joint"}],
            "accessors": [{"count": 3}, {"count": 3}, {"count": 3}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "JOINTS_0": 1,
                                                        "WEIGHTS_0": 2}, "targets": [{"POSITION": 0}]}]}],
            "skins": [{"joints": [1]}],
            "animations": [{"samplers": [{"input": 0, "output": 2}],
                            "channels": [{"sampler": 0, "target": {"node": 0, "path": "rotation"}}]}]}


class GLBInspectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "subject.glb"

    def write(self, doc=None, binary=b"0" * 12):
        self.file.write_bytes(encode_glb(doc or structure(), binary))

    def test_skinned_character_report_is_offline_only(self):
        self.write()
        report = inspect_glb(self.file).to_dict()
        self.assertEqual(report["status"], "OFFLINE_STRUCTURE_CHECKED")
        self.assertFalse(report["engine_validated"])
        self.assertEqual(report["mesh_count"], 1)
        self.assertEqual(report["skin_count"], 1)
        self.assertEqual(report["joint_count"], 1)
        self.assertEqual(report["animation_count"], 1)
        self.assertEqual(report["morph_target_count"], 1)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(len(report["sha256"]), 64)

    def test_reject_bad_magic_or_length(self):
        self.write()
        self.file.write_bytes(b"FAIL" + self.file.read_bytes()[4:])
        with self.assertRaises(GLBInspectionError):
            inspect_glb(self.file)
        self.write()
        self.file.write_bytes(self.file.read_bytes()[:-4])
        with self.assertRaises(GLBInspectionError):
            inspect_glb(self.file)

    def test_reject_invalid_skin_joint_index(self):
        doc = structure()
        doc["skins"][0]["joints"] = [20]
        self.write(doc)
        with self.assertRaisesRegex(GLBInspectionError, "joint"):
            inspect_glb(self.file)

    def test_reject_invalid_primitive_accessor(self):
        doc = structure()
        doc["meshes"][0]["primitives"][0]["attributes"]["POSITION"] = 500
        self.write(doc)
        with self.assertRaisesRegex(GLBInspectionError, "attribute"):
            inspect_glb(self.file)

    def test_reject_binary_shorter_than_declared_buffer(self):
        self.write(binary=b"0" * 4)
        with self.assertRaisesRegex(GLBInspectionError, "too small"):
            inspect_glb(self.file)

    def test_reject_node_graph_cycle(self):
        doc = structure()
        doc["nodes"][0]["children"] = [1]
        doc["nodes"][1]["children"] = [0]
        self.write(doc)
        with self.assertRaisesRegex(GLBInspectionError, "Cycle"):
            inspect_glb(self.file)

    def test_warns_on_nonembedded_images(self):
        doc = structure()
        doc["images"] = [{"uri": "file:///somewhere/secret.png"}]
        self.write(doc)
        report = inspect_glb(self.file).to_dict()
        self.assertTrue(any("external images" in x for x in report["warnings"]))

    def test_missing_rig_animation_and_morphs_stays_structural(self):
        doc = structure()
        doc["skins"] = []
        doc["nodes"] = [{"mesh": 0}]
        doc["animations"] = []
        doc["meshes"][0]["primitives"][0]["targets"] = []
        self.write(doc)
        report = inspect_glb(self.file).to_dict()
        self.assertTrue(any("No complete skinned" in x for x in report["warnings"]))
        self.assertTrue(any("No animations" in x for x in report["warnings"]))
        self.assertTrue(any("No mesh morph" in x for x in report["warnings"]))
