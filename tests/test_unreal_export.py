"""Independent publication faults; mocked native calls NEVER prove Unreal quality."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
import json
import os
from fixtures.unreal_export_logic import UnrealExportFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.export_destination import rename_new
from ucc.jobs.skin_material_preparation import _BudgetCancel
import ucc.jobs.unreal_export as backend


class UnrealExportFaultTests(TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.f=UnrealExportFixture(Path(temporary.name).resolve())
        self.mocks={}
        for name,active in self.f.patches().items():
            self.mocks[name]=active.start();self.addCleanup(active.stop)

    def invoke(self,**options):
        return backend.export_unreal(self.f.store,**(self.f.options|options))

    def journal(self,f=None):
        f=f or self.f
        path=f.store.root/'.ucc-jobs'/('unreal-export-'+f.request.job_id)/'job_status.json'
        return json.loads(path.read_bytes())

    def assert_withdrawn(self):
        self.assertEqual(self.f.store.load(),self.f.project)
        self.assertFalse(self.f.destination.path.exists())
        record=self.journal()
        self.assertEqual(record['state'],'FAILED');self.assertFalse(record['export_published'])
        for stage in self.f.root.glob('.ucc-export-*'):
            receipt=stage/'export_receipt.json'
            if receipt.exists():
                body=json.loads(receipt.read_bytes())
                self.assertFalse(body['export_published']);self.assertFalse(body['final_payload_verified'])

    def test_success_binds_published_project_and_keeps_originals_private(self):
        before=self.f.store.file.read_bytes();phases=[]
        result=self.invoke(toolchain=None,progress=phases.append)
        receipt=backend.verify_unreal_export_result(result)
        self.assertTrue(receipt['export_published']);self.assertTrue(receipt['final_payload_verified'])
        self.assertTrue(receipt['private_static_native_verified'])
        self.assertFalse(receipt['runtime_gpu_verified']);self.assertFalse(receipt['visual_quality_approved'])
        self.assertEqual(phases[-1],'COMPLETE');self.assertEqual(self.f.store.file.read_bytes(),before)
        self.mocks['preflight'].assert_called_once();self.mocks['final_native'].assert_called_once()
        for name in ('source_reference.json','source_corner_normals.bin','candidate.blend','Plugins','Saved','Binaries'):
            self.assertFalse((result.destination/name).exists())
        actual={p.relative_to(result.destination).as_posix() for p in result.destination.rglob('*') if p.is_file()}
        self.assertEqual(len(actual),11)

    def test_stale_review_and_revision_cannot_start_source_worker(self):
        with self.assertRaises(ProjectConflict):self.invoke(request=replace(self.f.request,project_sha256='0'*64))
        self.mocks['sources'].side_effect=ProjectConflict('UNIT_STALE_REVISION')
        with self.assertRaises(ProjectConflict):self.invoke(request=replace(self.f.request,revision=self.f.request.revision+1))
        self.mocks['source_stage'].assert_not_called();self.assertFalse(self.f.destination.path.exists())

    def test_selected_engine_build_and_toolchain_hashes_must_match_before_workers(self):
        for field in ('unreal_executable_sha256','unreal_build_version_sha256','toolchain_sha256'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.invoke(request=replace(self.f.request,**{field:'0'*64}))
        self.mocks['source_stage'].assert_not_called()

    def test_source_proof_executable_resource_and_compiler_mutation_stop_engine(self):
        for kind in ('proof','source','executable','resource','compiler'):
            with self.subTest(kind=kind), TemporaryDirectory() as temp, ExitStack() as stack:
                f=UnrealExportFixture(Path(temp).resolve());m={k:stack.enter_context(p) for k,p in f.patches().items()}
                target={'proof':f.proofs/('b'*64+'.json'),'source':f.sources['expression_library'],
                        'executable':f.editor,'resource':f.resource,'compiler':f.toolchain.compiler}[kind]
                def mutate(*args,**options):
                    target.write_bytes(target.read_bytes()+b'UNIT_MUTATION');return f.prepared
                m['source_stage'].side_effect=mutate
                with self.assertRaises((ProjectStorageError,ProjectConflict)):
                    backend.export_unreal(f.store,**f.options)
                m['engine_stage'].assert_not_called();self.assertFalse(f.destination.path.exists())

    def test_same_byte_ancestral_proof_replacement_is_rejected(self):
        proof=self.f.store.root/'expressions/inspections/UNIT_ANCESTRAL.json'
        proof.parent.mkdir(parents=True,exist_ok=True);proof.write_bytes(b'UNIT_NOT_REAL_PROOF')
        def replace_proof(*args,**options):
            replacement=proof.with_name('UNIT_REPLACEMENT.json');replacement.write_bytes(proof.read_bytes())
            os.replace(replacement,proof);return self.f.prepared
        self.mocks['source_stage'].side_effect=replace_proof
        with self.assertRaises((ProjectStorageError,ProjectConflict)):self.invoke()
        self.mocks['engine_stage'].assert_not_called();self.assertEqual(proof.read_bytes(),b'UNIT_NOT_REAL_PROOF')

    def test_cancel_and_parent_deadline_stop_at_next_stage_without_reset(self):
        for mode in ('cancel','deadline'):
            with self.subTest(mode=mode), TemporaryDirectory() as temp, ExitStack() as stack:
                f=UnrealExportFixture(Path(temp).resolve());m={k:stack.enter_context(p) for k,p in f.patches().items()}
                clock=[0.];user=Event();outer=_BudgetCancel(user,1.)
                def stop(*args,**options):
                    self.assertLessEqual(options['timeout_s'],1.)
                    if mode=='deadline':clock[0]=2.
                    else:user.set()
                    return f.prepared
                m['source_stage'].side_effect=stop
                stack.enter_context(patch.object(backend.time,'monotonic',side_effect=lambda:clock[0]))
                with self.assertRaisesRegex(ProjectStorageError,'deadline' if mode=='deadline' else 'cancelled'):
                    backend.export_unreal(f.store,**f.options,cancel=outer,timeout_s=60.)
                m['source_stage'].assert_called_once();m['engine_stage'].assert_not_called()
                self.assertEqual(self.journal(f)['failure_reason'],'total_deadline' if mode=='deadline' else 'user_cancel')

    def test_cancel_inside_initial_hash_is_classified_and_never_launches(self):
        cancel=Event()
        def stop(*args,**options):
            cancel.set();raise ProjectStorageError('UNIT_RAW_HASH_CANCEL')
        with patch.object(backend,'_digest',side_effect=stop):
            with self.assertRaisesRegex(ProjectStorageError,'cancelled') as raised:self.invoke(cancel=cancel)
        self.assertIn('UNIT_RAW_HASH_CANCEL',str(raised.exception.__cause__))
        self.mocks['source_stage'].assert_not_called()

    def test_raced_in_destination_is_not_replaced_or_adopted(self):
        marker=self.f.destination.path/'UNIT_UNRELATED'
        def race(source,destination):
            if destination==self.f.destination.path:
                destination.mkdir();marker.write_bytes(b'UNIT_PRESERVE')
            rename_new(source,destination)
        with patch.object(backend,'rename_new',side_effect=race):
            with self.assertRaises(OSError):self.invoke()
        self.assertEqual(marker.read_bytes(),b'UNIT_PRESERVE')
        self.assertEqual(self.f.store.load(),self.f.project);self.mocks['final_native'].assert_not_called()

    def test_changed_or_extra_staged_payload_never_reaches_rename(self):
        for kind in ('changed','extra','empty_cache'):
            with self.subTest(kind=kind), TemporaryDirectory() as temp, ExitStack() as stack:
                f=UnrealExportFixture(Path(temp).resolve());m={k:stack.enter_context(p) for k,p in f.patches().items()}
                real_stage=backend.stage_payload
                def corrupt(engine,destination,request,cancel=None):
                    sealed=real_stage(engine,destination,request,cancel)
                    if kind=='changed':(destination/'Content/UCC/Character.uasset').write_bytes(b'UNIT_CORRUPTED_COPY')
                    elif kind=='extra':(destination/'UNIT_UNLISTED_PRIVATE_SOURCE.blend').write_bytes(b'UNIT_PRIVATE')
                    else:(destination/'Saved').mkdir()
                    return sealed
                stack.enter_context(patch.object(backend,'stage_payload',side_effect=corrupt))
                rename=stack.enter_context(patch.object(backend,'rename_new',wraps=rename_new))
                with self.assertRaises(ProjectStorageError):backend.export_unreal(f.store,**f.options)
                rename.assert_not_called();m['final_native'].assert_not_called();self.assertFalse(f.destination.path.exists())

    def test_corruption_immediately_after_publication_rolls_own_folder_back(self):
        def corrupt(source,destination):
            rename_new(source,destination)
            if destination==self.f.destination.path:
                (destination/'Content/UCC/Character.uasset').write_bytes(b'UNIT_POST_RENAME_CORRUPTION')
        with patch.object(backend,'rename_new',side_effect=corrupt):
            with self.assertRaises(ProjectStorageError):self.invoke()
        self.assert_withdrawn();self.mocks['final_native'].assert_not_called()

    def test_actual_published_verification_failure_rolls_back_without_success_receipt(self):
        self.mocks['final_native'].side_effect=ProjectStorageError('UNIT_FINAL_NATIVE_REJECTED')
        with self.assertRaisesRegex(ProjectStorageError,'UNIT_FINAL_NATIVE_REJECTED'):self.invoke()
        self.assert_withdrawn();self.assertTrue(self.journal()['rolled_back'])

    def test_payload_changed_during_final_native_call_is_rejected(self):
        def corrupt(directory,**options):
            admitted=self.f.verify_final(directory,**options)
            (directory/'Content/UCC/SkinMaterial.uasset').write_bytes(b'UNIT_MODIFIED_DURING_NATIVE_READ')
            return admitted
        self.mocks['final_native'].side_effect=corrupt
        with self.assertRaises(ProjectStorageError):self.invoke()
        self.assert_withdrawn()

    def test_rollback_never_touches_external_destination_replacement(self):
        moved=self.f.root/'UNIT_EXTERNALLY_MOVED_OWNED_FOLDER';marker=self.f.destination.path/'UNIT_EXTERNAL'
        def replace_destination(*args,**options):
            rename_new(self.f.destination.path,moved);self.f.destination.path.mkdir()
            marker.write_bytes(b'UNIT_PRESERVE_EXTERNAL');raise ProjectStorageError('UNIT_EXTERNAL_REPLACEMENT')
        self.mocks['final_native'].side_effect=replace_destination
        with self.assertRaisesRegex(ProjectStorageError,'UNIT_EXTERNAL_REPLACEMENT'):self.invoke()
        self.assertEqual(marker.read_bytes(),b'UNIT_PRESERVE_EXTERNAL');self.assertTrue(moved.is_dir())
        self.assertFalse(self.journal()['rolled_back']);self.assertEqual(self.f.store.load(),self.f.project)

    def test_cancel_after_publication_rolls_back_before_native_call(self):
        cancel=Event()
        def progress(state):
            if self.f.destination.path.exists():cancel.set()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled'):self.invoke(cancel=cancel,progress=progress)
        self.assert_withdrawn();self.mocks['final_native'].assert_not_called()
        self.assertEqual(self.journal()['failure_reason'],'user_cancel')

    def test_deadline_during_postpublication_guard_is_normalized_and_rolled_back(self):
        clock=[0.];actual=backend._digest
        def expire(path,cancel=None):
            if self.f.destination.path.exists() and Path(path)==self.f.editor:clock[0]=2.
            return actual(path,cancel)
        with patch.object(backend.time,'monotonic',side_effect=lambda:clock[0]),patch.object(backend,'_digest',side_effect=expire):
            with self.assertRaisesRegex(ProjectStorageError,'deadline'):self.invoke(timeout_s=1.)
        self.assert_withdrawn();self.assertEqual(self.journal()['failure_reason'],'total_deadline')
        self.assertFalse(self.journal()['cancelled'])

    def test_late_complete_callback_failure_withdraws_success_receipt_truthfully(self):
        def progress(state):
            if state=='COMPLETE':raise RuntimeError('UNIT_LATE_COMPLETE_CALLBACK_FAILURE')
        with self.assertRaisesRegex(RuntimeError,'UNIT_LATE_COMPLETE_CALLBACK_FAILURE'):self.invoke(progress=progress)
        self.assert_withdrawn();self.assertTrue(self.journal()['rolled_back'])

    def test_final_journal_failure_cleans_own_temp_and_withdraws_success(self):
        actual=os.replace
        def fail_complete(source,destination):
            if Path(source).name=='job_status.tmp' and json.loads(Path(source).read_bytes())['state']=='COMPLETE':
                raise OSError('UNIT_COMPLETE_JOURNAL_FAILURE')
            return actual(source,destination)
        with patch.object(backend.os,'replace',side_effect=fail_complete):
            with self.assertRaisesRegex(OSError,'UNIT_COMPLETE_JOURNAL_FAILURE'):self.invoke()
        self.assert_withdrawn()
        work=self.f.store.root/'.ucc-jobs'/('unreal-export-'+self.f.request.job_id)
        self.assertFalse((work/'job_status.tmp').exists())

    def test_final_result_checker_rejects_added_private_file(self):
        result=self.invoke();(result.destination/'UNIT_PRIVATE_SOURCE.blend').write_bytes(b'UNIT_PRIVATE')
        with self.assertRaises(ProjectStorageError):backend.verify_unreal_export_result(result)

    def test_unlisted_engine_delivery_file_never_publishes(self):
        (self.f.engine.project_directory/'source_reference.json').write_bytes(b'UNIT_PRIVATE_REFERENCE')
        with self.assertRaises(ProjectStorageError):self.invoke()
        self.assertFalse(self.f.destination.path.exists());self.mocks['final_native'].assert_not_called()

    def test_copy_function_corruption_is_detected_before_publication(self):
        import ucc.jobs.unreal_export_payload as payload
        actual=payload.shutil.copyfileobj
        def corrupt(source,target,length=0):
            actual(source,target,length)
            if Path(target.name).name=='Character.uasset':target.write(b'UNIT_COPY_FUNCTION_CORRUPTION')
        with patch.object(payload.shutil,'copyfileobj',side_effect=corrupt):
            with self.assertRaisesRegex(ProjectStorageError,'changed|copy|sealed'):self.invoke()
        self.assertFalse(self.f.destination.path.exists());self.mocks['final_native'].assert_not_called()

    def test_failure_before_first_receipt_hash_never_retains_success_claim(self):
        for mode in ('fsync_failure','receipt_digest_deadline'):
            with self.subTest(mode=mode), TemporaryDirectory() as temp, ExitStack() as stack:
                f=UnrealExportFixture(Path(temp).resolve())
                for active in f.patches().values():stack.enter_context(active)
                receipt=f.destination.path/'export_receipt.json';clock=[0.];fired=[False]
                real_digest=backend._digest;real_fsync=os.fsync
                if mode=='fsync_failure':
                    def fail_flush(descriptor):
                        if receipt.exists() and not fired[0]:
                            fired[0]=True;raise OSError('UNIT_OWN_RECEIPT_FSYNC_FAILURE')
                        return real_fsync(descriptor)
                    stack.enter_context(patch.object(backend.os,'fsync',side_effect=fail_flush))
                else:
                    def expire_first_receipt(path,cancel=None):
                        if Path(path)==receipt and not fired[0]:clock[0]=2.;fired[0]=True
                        return real_digest(path,cancel)
                    stack.enter_context(patch.object(backend.time,'monotonic',side_effect=lambda:clock[0]))
                    stack.enter_context(patch.object(backend,'_digest',side_effect=expire_first_receipt))
                with self.assertRaises(OSError if mode=='fsync_failure' else ProjectStorageError):
                    backend.export_unreal(f.store,**f.options,timeout_s=1. if mode!='fsync_failure' else 3600.)
                self.assertTrue(fired[0]);self.assertFalse(f.destination.path.exists())
                self.assertTrue(self.journal(f)['rolled_back'])
                for stage in f.root.glob('.ucc-export-*'):
                    retained=stage/'export_receipt.json'
                    if retained.exists():
                        record=json.loads(retained.read_bytes())
                        self.assertFalse(record['export_published'])
                        self.assertFalse(record['final_payload_verified'])

    def test_partial_receipt_repair_write_cannot_restore_old_success_json(self):
        from ucc.jobs.export_guards import invalidate_owned_receipt
        from ucc.export.godot_candidate_contract import canonical_bytes
        path=self.f.root/'UNIT_NOT_REAL_RECEIPT.json'
        expected=canonical_bytes({'export_published':True,'final_payload_verified':True,
                                  'private_static_native_verified':True})
        path.write_bytes(expected);info=path.stat();real_open=Path.open
        class PartialWriter:
            def __init__(self,stream):self.stream=stream;self.calls=0
            def __enter__(self):return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def __getattr__(self,name):return getattr(self.stream,name)
            def write(self,data):
                self.calls+=1
                if self.calls==2:
                    self.stream.write(data[:1]);raise OSError('UNIT_PARTIAL_REPAIR_TAIL_FAILURE')
                return self.stream.write(data)
        def opened(selected,*args,**options):return PartialWriter(real_open(selected,*args,**options))
        with patch.object(Path,'open',opened):
            with self.assertRaisesRegex(OSError,'UNIT_PARTIAL_REPAIR_TAIL_FAILURE'):
                invalidate_owned_receipt(path,expected,(info.st_dev,info.st_ino))
        self.assertTrue(path.read_bytes().startswith(b'\0'))
        with self.assertRaises((ValueError,UnicodeError)):json.loads(path.read_bytes())

    def test_journal_fsync_failure_preserves_raw_error_and_writes_failed_state(self):
        work=self.f.store.root/'.ucc-jobs'/('unreal-export-'+self.f.request.job_id)
        temporary=work/'job_status.tmp';fired=[False];actual=os.fsync
        def fail_journal(descriptor):
            if temporary.is_file() and not fired[0]:
                fired[0]=True;raise OSError('UNIT_ORIGINAL_JOURNAL_FSYNC_FAILURE')
            return actual(descriptor)
        with patch.object(backend.os,'fsync',side_effect=fail_journal):
            with self.assertRaisesRegex(OSError,'UNIT_ORIGINAL_JOURNAL_FSYNC_FAILURE'):
                self.invoke()
        self.assertTrue(fired[0]);self.assertFalse(temporary.exists())
        record=self.journal()
        self.assertEqual(record['state'],'FAILED')
        self.assertEqual(record['raw_error_type'],'OSError')
        self.assertIn('UNIT_ORIGINAL_JOURNAL_FSYNC_FAILURE',record['raw_error'])
        self.assertFalse(record['export_published'])
        self.mocks['source_stage'].assert_not_called()
        self.assertEqual(self.f.store.load(),self.f.project)
