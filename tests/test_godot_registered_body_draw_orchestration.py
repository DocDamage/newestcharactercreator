"""Synthetic orchestration ownership faults; all admission/engine work mocked."""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from ucc.core.errors import ProjectStorageError
from ucc.export.godot_registered_body_draw import RegisteredBodyDrawSelection
from ucc.jobs import godot_registered_body_draw as draw_job


class AfterFlush:
    def __init__(self,stream,hook):self.stream=stream;self.hook=hook;self.done=False
    def __enter__(self):self.stream.__enter__();return self
    def __exit__(self,*args):return self.stream.__exit__(*args)
    def fileno(self):return self.stream.fileno()
    def write(self,raw):return self.stream.write(raw)
    def flush(self):
        self.stream.flush()
        if not self.done:self.done=True;self.hook()


class DrawOrchestrationOwnershipTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.jobs=self.root/'.ucc-jobs';self.jobs.mkdir();self.source=self.root/'SYNTHETIC_INPUTS';self.source.mkdir()
        self.draw=RegisteredBodyDrawSelection(str(uuid4()),'a'*64,'b'*64,'c'*64,'Synthetic nonshipping ownership logic test',True)
        self.work=self.jobs/('registered-body-draw-'+self.draw.draw_id);self.engine=self.work/'engine'
        self.adapter=self.root/'SYNTHETIC_ADAPTER';self.adapter.mkdir()
        for name in ('project.godot','validate.gd'):(self.adapter/name).write_bytes(b'SYNTHETIC NEVER EXECUTED')
        self.records={}
        for name in ('imported_uv.f32','imported_uv_source_ids.u32','imported_uv_triangles.u32','actual_corrected_world.f32','actual_normals_vec4.f32'):
            raw=b'SYNTHETIC';(self.source/name).write_bytes(raw);self.records[name]={'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}
        self.guard_hook=lambda:None
    def replace_same_bytes(self,target):
        replacement=self.root/'replacement.bin';replacement.write_bytes(target.read_bytes());replacement.replace(target)
    def call(self,flush_target=None,flush_hook=None):
        inputs=SimpleNamespace(directory=self.source,records=self.records,guard=lambda:self.guard_hook())
        def observed(folder,*args):
            raw=b'SYNTHETIC ENGINE OUTPUT';(folder/'synthetic-observed.bin').write_bytes(raw);(folder/'measurement.json').write_bytes(b'{}')
            return {'measurement_sha256':sha256(b'{}').hexdigest(),'files':{'synthetic-observed.bin':{'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}}}
        with ExitStack() as stack:
            stack.enter_context(patch.object(draw_job,'admit_draw_inputs',return_value=inputs))
            stack.enter_context(patch.object(draw_job,'safe_directory',return_value=self.jobs))
            stack.enter_context(patch.object(draw_job,'_adapter_paths',return_value={n:self.adapter/n for n in ('project.godot','validate.gd')}))
            stack.enter_context(patch.object(draw_job,'read_frame_stream',return_value={1:b'x',150:b'y',300:b'z'}))
            mapper=stack.enter_context(patch.object(draw_job,'map_frame',return_value={'positions':b'POSITIONS','normals':b'NORMALS'}))
            runner=stack.enter_context(patch.object(draw_job,'run_process',return_value=SimpleNamespace(return_code=0,cancelled=False,timed_out=False,elapsed_seconds=.1)))
            stack.enter_context(patch.object(draw_job,'verify_draw_outputs',side_effect=observed))
            if flush_target:
                real=Path.open
                def opened(path,*args,**kwargs):
                    stream=real(path,*args,**kwargs)
                    return AfterFlush(stream,flush_hook) if path.name==flush_target and args and args[0]=='xb' else stream
                stack.enter_context(patch.object(Path,'open',opened))
            try:
                result=draw_job.draw_registered_native_body(object(),selection=None,retention_id='',expected_manifest_sha256='',database_path=self.root/'unused',permissions=(),preparation=None,expected_production_receipt_sha256='',execution=None,diagnostic=None,draw=self.draw,godot_exe=self.root/'SYNTHETIC_CONSOLE.exe',godot_main_exe=self.root/'SYNTHETIC_MAIN.exe')
                self.assertTrue(all(call.kwargs.get('check') is not None for call in mapper.call_args_list))
                return result
            finally:self.runner_calls=runner.call_count
    def test_mocked_success_retains_owned_receipt(self):
        result=self.call();self.assertEqual(result.directory,self.work);self.assertTrue((self.work/'diagnostic_draw_receipt.json').is_file());self.assertEqual(self.runner_calls,1)
    def test_earlier_same_byte_stage_replacement_rejects_before_engine(self):
        with self.assertRaisesRegex(ProjectStorageError,'staged input identity'):
            self.call('frame150_positions.f32',lambda:self.replace_same_bytes(self.engine/'frame001_positions.f32'))
        self.assertEqual(self.runner_calls,0)
    def test_hardlinked_pending_receipt_rejects_before_commit(self):
        with self.assertRaisesRegex(ProjectStorageError,'replaced or linked'):
            self.call('receipt.pending.json',lambda:os.link(self.work/'receipt.pending.json',self.root/'FOREIGN_LINK.json'))
        self.assertFalse((self.work/'diagnostic_draw_receipt.json').exists())
    def test_replaced_pending_receipt_rejects_and_foreign_bytes_survive(self):
        changed=False
        def replace():
            nonlocal changed
            pending=self.work/'receipt.pending.json'
            if pending.exists() and not changed:
                changed=True
                value=self.root/'FOREIGN_RECEIPT.json';value.write_bytes(b'FOREIGN');value.replace(pending)
        # Windows disallows replacing a normally opened writer. Exercise the
        # real after-close/before-commit window instead of skipping this fault.
        self.guard_hook=replace
        with self.assertRaisesRegex(ProjectStorageError,'ownership changed before commit'):self.call()
        self.assertEqual((self.work/'receipt.pending.json').read_bytes(),b'FOREIGN');self.assertFalse((self.work/'diagnostic_draw_receipt.json').exists())
    def test_output_replacement_during_postcommit_source_guard_rejects(self):
        changed=False
        def mutate():
            nonlocal changed
            if (self.work/'diagnostic_draw_receipt.json').exists() and not changed:
                changed=True;self.replace_same_bytes(self.engine/'synthetic-observed.bin')
        self.guard_hook=mutate
        with self.assertRaisesRegex(ProjectStorageError,'evidence changed'):self.call()
        self.assertTrue(changed)
