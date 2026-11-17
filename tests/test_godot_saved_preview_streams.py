"""Synthetic C hash/dehomogenization/normal faults, not geometry or app proof."""
from hashlib import sha256
from pathlib import Path
import math
import struct
import tempfile
import unittest
from unittest.mock import patch
from fixtures.godot_registered_body_draw_logic import png
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.jobs.godot_saved_preview_streams import capture_body_streams,NAMES
from ucc.jobs.godot_saved_preview_files import ProofReads
from ucc.jobs.target_action_context import Budget


class InjectedStream:
    def __init__(self,stream,transform):self.stream=stream;self.transform=transform
    def __enter__(self):self.stream.__enter__();return self
    def __exit__(self,*args):return self.stream.__exit__(*args)
    def fileno(self):return self.stream.fileno()
    def read(self,size=-1):return self.transform(self.stream.read(size))


class SavedCapturedStreamTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.raw={NAMES[0]:struct.pack('<4f',-0.,2,3,1)*6,NAMES[1]:struct.pack('<4f',-0.,2,3,1)*6,
                  NAMES[2]:struct.pack('<4f',0,0,1,0)*6,NAMES[3]:struct.pack('<4f',0,0,1,0)*6}
        self.refs={'native_positions.bin':{'sha256':sha256(struct.pack('<3f',-0.,2,3)*6).hexdigest(),'bytes':72},
                   'native_normals.bin':{'sha256':sha256(struct.pack('<3f',0,0,1)*6).hexdigest(),'bytes':72}}
        self.write()
    def write(self):
        for name,raw in self.raw.items():(self.root/name).write_bytes(raw)
    def capture(self,budget=None):
        return capture_body_streams(self.root,{n:sha256(raw).hexdigest() for n,raw in self.raw.items()},self.refs,budget or Budget(None,60),frames=3,vertices=2,selected=(1,3))
    def test_exact_same_buffer_source_hash_signed_zero_and_selected_frames(self):
        captured,metrics=self.capture();self.assertEqual(set(captured[NAMES[0]]),{1,3})
        self.assertEqual(captured[NAMES[0]][1],self.raw[NAMES[0]][:32]);self.assertEqual(metrics['maximum_position_error_m'],0.)
    def test_coherent_C_reference_and_actual_cannot_override_retained_original_hash(self):
        for name in (NAMES[0],NAMES[1]):self.raw[name]=struct.pack('<4f',1,2,3,1)*6
        self.write()
        with self.assertRaisesRegex(ValidationError,'retained original producer'):self.capture()
    def test_wrong_w_even_with_coherent_input_hash_rejected(self):
        self.raw[NAMES[1]]=struct.pack('<4f',-0.,2,3,0)*6;self.write()
        with self.assertRaisesRegex(ValidationError,'homogeneous'):self.capture()
    def test_unit_normal_and_angular_limit_are_independent(self):
        angle=math.radians(.11);self.raw[NAMES[2]]=struct.pack('<4f',math.sin(angle),0,math.cos(angle),0)*6;self.write()
        with self.assertRaisesRegex(ValidationError,'C limits'):self.capture()
    def test_nonunit_normal_rejected_with_valid_file_hash(self):
        self.raw[NAMES[2]]=struct.pack('<4f',0,0,2,0)*6;self.write()
        with self.assertRaisesRegex(ValidationError,'Nonunit'):self.capture()
    def test_position_limit_rejects_hash_consistent_corrupted_actual(self):
        self.raw[NAMES[0]]=struct.pack('<4f',.0001,2,3,1)*6;self.write()
        with self.assertRaisesRegex(ValidationError,'C limits'):self.capture()
    def test_mutually_coherent_transient_reads_fail_full_captured_SHA(self):
        real=Path.open
        def opened(path,*args,**kwargs):
            stream=real(path,*args,**kwargs)
            if path.name not in NAMES[:2]:return stream
            def transient(raw):
                if not raw:return raw
                value=bytearray(raw)
                for index in range(0,len(value),16):struct.pack_into('<f',value,index,12.)
                return bytes(value)
            return InjectedStream(stream,transient)
        with patch.object(Path,'open',opened),self.assertRaisesRegex(ProjectStorageError,'Captured saved body bytes'):self.capture()
    def test_cancel_is_polled_during_vertex_comparison(self):
        class Stops:
            calls=0
            def check(inner):
                inner.calls+=1
                if inner.calls==3:raise ProjectStorageError('synthetic cancel during source hash')
        with self.assertRaisesRegex(ProjectStorageError,'cancel during'):self.capture(Stops())


class SavedProofReadTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve();self.path=self.root/'record.json'
    def test_selected_SHA_and_parsed_meaning_share_buffer(self):
        self.path.write_bytes(b'{"value":1}');reads=ProofReads(Budget(None,60))
        self.assertEqual(reads.metadata(self.path,128,sha256(self.path.read_bytes()).hexdigest()),{'value':1});reads.check()
    def test_duplicate_nonfinite_and_overflow_json_reject(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}'):
            self.path.write_bytes(raw)
            with self.subTest(raw=raw),self.assertRaises(ValidationError):ProofReads(Budget(None,60)).metadata(self.path,128)
    def test_hardlink_and_same_byte_replacement_reject(self):
        import os
        self.path.write_bytes(b'{}');reads=ProofReads(Budget(None,60));reads.metadata(self.path,128)
        other=self.root/'replacement.json';other.write_bytes(b'{}');other.replace(self.path)
        with self.assertRaises(ProjectStorageError):reads.check()
        os.link(self.path,self.root/'other-link.json')
        with self.assertRaisesRegex(ProjectStorageError,'single-link'):ProofReads(Budget(None,60)).metadata(self.path,128)
    def test_read_bound_prevents_oversized_metadata(self):
        self.path.write_bytes(b'x'*129)
        with self.assertRaises(ProjectStorageError):ProofReads(Budget(None,60)).metadata(self.path,128)
