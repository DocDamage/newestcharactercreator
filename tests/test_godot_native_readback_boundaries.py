"""Nonshipping numeric stream faults after initial filesystem size admission."""
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from ucc.core.errors import ValidationError
from ucc.jobs.godot_native_target_evidence import compare_outputs,verify_uv_readback
from ucc.export.godot_surface_uv import read_glb_uvs


class CapturedStream:
    def __init__(self,stream,mode):self.stream=stream;self.mode=mode;self.closed=False
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True;return self.stream.__exit__(*args)
    def read(self,size):
        if self.mode=='short' and size==16:return self.stream.read(0)
        if self.mode=='trailing' and size==1:return b'X'
        return self.stream.read(size)


class NativeReadbackBoundariesTests(unittest.TestCase):
    def test_transient_short_read_after_stat_cannot_silently_zip_zero_vertices(self):
        self._fault('short')

    def test_terminal_eof_is_required_even_when_initial_size_was_exact(self):
        self._fault('trailing')

    def _fault(self,mode):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            for name,normal in (('actual_corrected_world.f32',False),('expected_vec4.f32',False),
                    ('actual_normals_vec4.f32',True),('expected_normals_vec4.f32',True)):
                (root/name).write_bytes(struct.pack('<4f',0.,0.,1. if normal else 0.,0. if normal else 1.))
            original={p.name:p.read_bytes() for p in root.iterdir()};real=Path.open;wrappers=[]
            def opened(path,*args,**kwargs):
                stream=real(path,*args,**kwargs)
                if path==root/'actual_corrected_world.f32':
                    wrapper=CapturedStream(stream,mode);wrappers.append(wrapper);return wrapper
                return stream
            with patch.object(Path,'open',new=opened):
                with self.assertRaises(ValidationError):compare_outputs(root,samples=1,vertices=1,check=lambda:None)
            self.assertTrue(wrappers[0].closed)
            self.assertEqual(original,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_optional_source_uv_binding_never_silently_disables_missing_glb_sha(self):
        for inputs in ({},{'bind_positions.bin':'a'*64,'face_vertices.u32':'a'*64,'face_ranges.u32':'a'*64},
                dict(bind_positions='invalid')):
            with self.assertRaisesRegex(ValidationError,'all four'):
                verify_uv_readback(Path('UNUSED'),{},lambda:None,input_hashes=inputs)

    def test_uv_digest_is_of_the_same_captured_buffer_that_would_be_parsed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();size=14517*8
            original=b'\0'*size;changed=b'X'*size
            (root/'imported_uv.f32').write_bytes(changed)
            hashes={'imported_uv.f32':sha256(original).hexdigest(),'imported_uv_source_ids.u32':'a'*64,'imported_uv_triangles.u32':'b'*64}
            # A separate hash call can observe old bytes while parse sees new
            # bytes. The consumer must hash its captured parse buffer instead.
            with patch('ucc.jobs.godot_native_target_evidence._digest',return_value=hashes['imported_uv.f32']):
                with self.assertRaisesRegex(ValidationError,'UV readback changed'):
                    verify_uv_readback(root,hashes,lambda:None)

    def test_glb_uv_parser_checks_its_exact_parsed_raw_buffer(self):
        with patch('ucc.export.godot_surface_uv._DenseSkin',return_value=SimpleNamespace(raw=b'NONSHIPPING_DIFFERENT_BUFFER')):
            with self.assertRaisesRegex(ValidationError,'parser buffer'):
                read_glb_uvs(Path('UNUSED'),[],expected_sha256='a'*64)
