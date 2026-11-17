"""Synthetic captured-stream race faults; no actual model/engine proof."""
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.jobs.godot_registered_body_draw_evidence import read_frame_stream
from ucc.jobs.godot_registered_body_draw_inputs import _source_reference
from ucc.jobs.target_action_context import Budget


class InjectedRead:
    """Expose transient captured bytes with stable fd/path metadata (ABA model)."""
    def __init__(self, stream, replace):self.stream=stream;self.replace=replace;self.calls=0
    def __enter__(self):self.stream.__enter__();return self
    def __exit__(self,*args):return self.stream.__exit__(*args)
    def fileno(self):return self.stream.fileno()
    def read(self,size=-1):
        raw=self.stream.read(size);self.calls+=1
        return self.replace(raw,self.calls)


class DrawCapturedStreamTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.path=self.root/'synthetic-vec4.bin';self.raw=struct.pack('<4f',1,2,3,1)*6;self.path.write_bytes(self.raw)
    def read(self,**kwargs):return read_frame_stream(self.path,sha256(self.raw).hexdigest(),Budget(None,60),frames=3,vertices=2,selected=(1,3),**kwargs)
    def test_single_pass_retains_exact_selected_frames_only(self):
        result=self.read();self.assertEqual(set(result),{1,3});self.assertEqual(result[1],self.raw[:32]);self.assertEqual(result[3],self.raw[-32:])
    def test_transient_unselected_frame_bytes_rejected_despite_stable_path_and_fd(self):
        real=Path.open
        def opened(path,*args,**kwargs):
            stream=real(path,*args,**kwargs)
            if path!=self.path:return stream
            def replace(raw,call):
                if call==2:return struct.pack('<f',99.)+raw[4:]
                return raw
            return InjectedRead(stream,replace)
        with patch.object(Path,'open',opened),self.assertRaisesRegex(ProjectStorageError,'selected SHA/identity'):self.read()
        self.assertEqual(self.path.read_bytes(),self.raw)
    def test_pre_cancel_does_not_capture(self):
        event=Event();event.set()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled by caller'):
            read_frame_stream(self.path,sha256(self.raw).hexdigest(),Budget(event,60),frames=3,vertices=2,selected=(1,3))
    def test_truncated_and_trailing_stream_rejected(self):
        for raw in (self.raw[:-1],self.raw+b'x'):
            self.path.write_bytes(raw)
            with self.subTest(size=len(raw)),self.assertRaises(ProjectStorageError):self.read()
    def test_cancellation_callback_is_polled_while_streaming(self):
        class CancelAfterStart:
            calls=0
            def check(inner):
                inner.calls+=1
                if inner.calls==3:raise ProjectStorageError('synthetic caller cancel inside loop')
        budget=CancelAfterStart()
        with self.assertRaisesRegex(ProjectStorageError,'inside loop'):
            read_frame_stream(self.path,sha256(self.raw).hexdigest(),budget,frames=3,vertices=2,selected=(1,3))


class DrawCapturedReferenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.source=self.root/'synthetic-source.bin';self.converted=self.root/'synthetic-expanded.bin'
        self.a=struct.pack('<3f',1,2,3)*6;self.b=struct.pack('<3f',11,2,3)*6
        self.expanded_a=struct.pack('<4f',1,2,3,1)*6;self.expanded_b=struct.pack('<4f',11,2,3,1)*6
        self.source.write_bytes(self.a);self.converted.write_bytes(self.expanded_a)
    def compare(self,source_sha=None,converted_sha=None):
        _source_reference(self.source,self.converted,False,Budget(None,60),frames=3,vertices=2,
            source_sha256=source_sha or sha256(self.a).hexdigest(),converted_sha256=converted_sha or sha256(self.expanded_a).hexdigest())
    def test_exact_complete_source_expansion_passes(self):self.compare()
    def test_mutually_matching_transient_source_bytes_not_selected_source_rejected(self):
        self.converted.write_bytes(self.expanded_b);real=Path.open
        def opened(path,*args,**kwargs):
            stream=real(path,*args,**kwargs)
            return InjectedRead(stream,lambda raw,call:self.b[:len(raw)] if raw else raw) if path==self.source else stream
        with patch.object(Path,'open',opened),self.assertRaisesRegex(ProjectStorageError,'selected SHA/identity'):
            self.compare(converted_sha=sha256(self.expanded_b).hexdigest())
        self.assertEqual(self.source.read_bytes(),self.a)
    def test_mutually_matching_transient_expanded_bytes_not_selected_expansion_rejected(self):
        self.converted.write_bytes(self.expanded_b);real=Path.open
        def opened(path,*args,**kwargs):
            stream=real(path,*args,**kwargs)
            return InjectedRead(stream,lambda raw,call:self.expanded_a[:len(raw)] if raw else raw) if path==self.converted else stream
        with patch.object(Path,'open',opened),self.assertRaisesRegex(ProjectStorageError,'selected SHA/identity'):
            self.compare(converted_sha=sha256(self.expanded_b).hexdigest())
        self.assertEqual(self.converted.read_bytes(),self.expanded_b)
    def test_wrong_homogeneous_expansion_rejected(self):
        self.converted.write_bytes(struct.pack('<4f',1,2,3,0)*6)
        with self.assertRaises(ValidationError):
            self.compare()
