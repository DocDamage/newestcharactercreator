"""Synthetic GLB triangles used only for unit verification; not shipped as character art."""
from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.preview.glb_mesh import PreviewError, load_glb_preview, _node_transform, _transform


def synthetic_glb(path: Path, *, positions=None, indices=(0,1,2), transform=None,
                  corrupt_index=False, external=False, no_nodes=False, interleaved=False):
    positions = positions or [(0.,0.,0.),(1.,0.,0.),(0.,1.,0.)]
    if interleaved:
        pos = b"".join(struct.pack("<ffff", *p, 777.) for p in positions)
    else:
        pos = b"".join(struct.pack("<fff", *p) for p in positions)
    idx = list(indices)
    if corrupt_index:
        idx[1] = 777
    inds = struct.pack("<"+"H"*len(idx),*idx)
    data = pos + inds
    data += b"\0" * ((4-len(data)%4)%4)
    doc = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(data), **({"uri":"https://example.com/malicious.bin"} if external else {})}],
        "bufferViews": [
            {"buffer":0,"byteOffset":0,"byteLength":len(pos),**({"byteStride":16} if interleaved else {})},
            {"buffer":0,"byteOffset":len(pos),"byteLength":len(inds)}],
        "accessors": [
            {"bufferView":0,"componentType":5126,"count":len(positions),"type":"VEC3"},
            {"bufferView":1,"componentType":5123,"count":len(idx),"type":"SCALAR"}
        ],
        "meshes":[{"primitives":[{"attributes":{"POSITION":0},"indices":1,"mode":4}]}],
    }
    if not no_nodes:
        doc["nodes"]=[{"mesh":0,**(transform or {})}]
        doc["scenes"]=[{"nodes":[0]}]
        doc["scene"]=0
    doc_raw=json.dumps(doc,separators=(',',':')).encode('utf8')
    doc_raw+=b' ' * ((4-len(doc_raw)%4)%4)
    chunks=struct.pack('<I4s',len(doc_raw),b'JSON')+doc_raw+struct.pack('<I4s',len(data),b'BIN\x00')+data
    path.write_bytes(b'glTF'+struct.pack('<II',2,12+len(chunks))+chunks)
    return doc


class GlbMeshPreviewTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'character.glb'

    def test_reads_real_triangle_and_scene_translation(self):
        synthetic_glb(self.path,transform={"translation":[1,2,3]})
        report=load_glb_preview(self.path)
        self.assertEqual(report.source_face_count,1)
        self.assertEqual(report.sample_count,1)
        self.assertEqual(report.triangles[0][0],(1,2,3))
        self.assertEqual(report.bounds,((1.,2.,3.),(2.,3.,3.)))

    def test_interleaved_position_accessor_supported(self):
        synthetic_glb(self.path,interleaved=True)
        report=load_glb_preview(self.path)
        self.assertEqual(report.sample_count,1)
        self.assertEqual(report.triangles[0][1],(1.,0.,0.))

    def test_hierarchy_world_matrix(self):
        data=synthetic_glb(self.path,transform={"translation":[2,0,0]})
        data['nodes']=[{'translation':[0,5,0],'children':[1]},{'mesh':0,'translation':[2,0,0]}]
        doc=json.dumps(data,separators=(',',':')).encode();doc+=b' '*((4-len(doc)%4)%4)
        raw=self.path.read_bytes();offset=12+8+struct.unpack_from('<I',raw,12)[0]
        binpayload=raw[offset+8:]
        full=struct.pack('<I4s',len(doc),b'JSON')+doc+struct.pack('<I4s',len(binpayload),b'BIN\x00')+binpayload
        self.path.write_bytes(b'glTF'+struct.pack('<II',2,len(full)+12)+full)
        report=load_glb_preview(self.path)
        self.assertEqual(report.triangles[0][0],(2.,5.,0.))

    def test_rotation_and_scale_are_real_geometry_transforms(self):
        m=_node_transform({"scale":[2,1,1],"rotation":[0,0,math.sin(math.pi/4),math.cos(math.pi/4)]})
        p=_transform(m,(1,0,0))
        self.assertAlmostEqual(p[0],0,places=5)
        self.assertAlmostEqual(p[1],2,places=5)

    def test_bogus_indices_are_rejected(self):
        synthetic_glb(self.path,corrupt_index=True)
        with self.assertRaisesRegex(PreviewError,'absent vertex'):
            load_glb_preview(self.path)

    def test_nonfinite_vertices_are_rejected(self):
        synthetic_glb(self.path,positions=[(float('nan'),0,0),(1,0,0),(0,1,0)])
        with self.assertRaisesRegex(PreviewError,'nonfinite'):
            load_glb_preview(self.path)

    def test_remote_buffer_uri_is_not_fetched(self):
        synthetic_glb(self.path,external=True)
        with self.assertRaisesRegex(PreviewError,'embedded binary buffer'):
            load_glb_preview(self.path)

    def test_model_without_nodes_is_displayed_with_warning(self):
        synthetic_glb(self.path,no_nodes=True)
        report=load_glb_preview(self.path)
        self.assertEqual(report.sample_count,1)
        self.assertTrue(any('no scene nodes' in warning for warning in report.warnings))

    def test_sampling_preserves_large_face_count_but_caps_draw(self):
        synthetic_glb(self.path,indices=(0,1,2)*4200)
        report=load_glb_preview(self.path)
        self.assertEqual(report.source_face_count,4200)
        self.assertLessEqual(report.sample_count,2000)
        self.assertTrue(any('Sampled' in warning for warning in report.warnings))

    def test_large_instanced_mesh_fails_before_unbounded_triangle_processing(self):
        doc = synthetic_glb(self.path, indices=(0, 1, 2) * 5000)
        doc["nodes"] = [{"mesh": 0} for _ in range(220)]
        doc["scenes"] = [{"nodes": list(range(220))}]
        doc["scene"] = 0
        data = self.path.read_bytes()
        original_json_len = struct.unpack_from("<I", data, 12)[0]
        binary = data[20 + original_json_len + 8:]
        updated_json = json.dumps(doc, separators=(",", ":")).encode()
        updated_json += b" " * (-len(updated_json) % 4)
        chunks = (struct.pack("<I4s", len(updated_json), b"JSON") + updated_json
                  + struct.pack("<I4s", len(binary), b"BIN\0") + binary)
        self.path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
        with self.assertRaisesRegex(PreviewError, "too many aggregate triangles"):
            load_glb_preview(self.path)

    def test_refuses_non_glb_and_symlinks(self):
        self.path.write_text('not a glb')
        with self.assertRaises(PreviewError):
            load_glb_preview(self.path)
        linked=Path(self.folder.name)/'linked.glb'
        try:
            linked.symlink_to(self.path)
        except (OSError,NotImplementedError):
            self.skipTest('Symlinks not supported')
        with self.assertRaisesRegex(PreviewError,'regular'):
            load_glb_preview(linked)

    def test_rejects_invalid_glb_envelope(self):
        self.path.write_bytes(b'not glTF')
        with self.assertRaises(PreviewError):
            load_glb_preview(self.path)

    def test_bad_node_transform_is_rejected(self):
        synthetic_glb(self.path,transform={"rotation":[0,0,0,0]})
        with self.assertRaisesRegex(PreviewError,'Zero-length'):
            load_glb_preview(self.path)


if __name__=='__main__':
    unittest.main()
