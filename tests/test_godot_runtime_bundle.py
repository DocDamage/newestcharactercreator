"""Contract, topology and transaction negatives; synthetic bytes are not engine proof."""
from contextlib import ExitStack
from dataclasses import replace
import json
from hashlib import sha256
from pathlib import Path
import struct
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

from fixtures.godot_runtime_logic import quad_data, RuntimeTransactionFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import NativeRuntimeRequest
from ucc.export.godot_runtime_data import validate_topology, validate_triangles, validate_clock
from ucc.jobs.godot_runtime_bundle import retain_private_native_runtime_inputs
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=RuntimeTransactionFixture(Path(temp.name).resolve())

    def doubles(self, callback=None):
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('ucc.jobs.godot_runtime_bundle.project_sources',return_value={'master':self.f.master}))
        def validate(folder, request, check):
            check()
            if callback:callback(folder)
            return {'UNIT_DOUBLE_NOT_REAL_RUNTIME':True,'runtime_execution_verified':False}
        stack.enter_context(patch('ucc.jobs.godot_runtime_bundle.validate_runtime_files',side_effect=validate))

    def retain(self, **kwargs):
        return retain_private_native_runtime_inputs(self.f.store,self.f.request,**self.f.kwargs(),**kwargs)

    def preserved(self):
        self.assertEqual(self.f.store.file.read_bytes(),self.f.original_metadata)
        self.assertEqual(self.f.master.read_bytes(),self.f.original_master)
        self.assertEqual((self.f.prior/'unit-marker').read_bytes(),b'PREVIOUS_UNIT_CANDIDATE_NO_ENGINE_CLAIM')
        self.assertFalse((self.f.store.root/'.ucc-candidates/godot-runtime-inputs'/self.f.request.job_id).exists())

    def test_roundtrip_never_promotes_byte_validation_to_execution_or_license(self):
        raw=self.f.request.to_dict();loaded=NativeRuntimeRequest.from_bytes(canonical_bytes(raw))
        self.assertEqual(loaded,self.f.request)
        self.assertEqual(loaded.sha256,self.f.request.sha256)
        for field in ['runtime_execution_verified','native_lineage_verified','engine_import_verified',
                      'distribution_license_review_complete','source_redistribution_authorized','cloud_transmission_authorized']:
            self.assertIs(raw[field],False)

    def test_closed_json_flags_profile_capability_and_clock_cannot_be_upgraded(self):
        for field,value in [('schema_version',True),('unknown',0),('runtime_execution_verified',True),
            ('native_lineage_verified',True),('distribution_license_review_complete',True),
            ('requested_capability','gl_compatibility'),('profile','arbitrary'),('implementation_sha256','a'*64),
            ('revision',True),('import_profile',{'fps':24})]:
            with self.subTest(field=field):
                raw=self.f.request.to_dict();raw[field]=value
                with self.assertRaises(ValidationError):NativeRuntimeRequest.from_bytes(canonical_bytes(raw))

    def test_duplicate_nonfinite_missing_and_oversized_json_reject(self):
        for data in [b'{"x":0,"x":1}',b'{"x":NaN}',b'[]',b'{}',b' '*300000]:
            with self.assertRaises(ValidationError):NativeRuntimeRequest.from_bytes(data)
        with self.assertRaises(ValidationError):replace(self.f.request,files=self.f.request.files[:-1])
        with self.assertRaises(ValidationError):replace(self.f.request,source_bindings=self.f.request.source_bindings*2)

    def test_source_only_preview_only_ue_only_and_wrong_content_reject(self):
        permission=self.f.request.permissions[0]
        for changed in [replace(permission,source_only=True),
            replace(permission,policy=replace(permission.policy,can_use_non_unreal=False)),
            replace(permission,policy=replace(permission.policy,ue_only=True)),
            replace(permission,source_sha256='0'*64)]:
            with self.assertRaises((ValidationError,AssetPolicyError)):
                replace(self.f.request,permissions=(changed,*self.f.request.permissions[1:]))

    def test_topology_cross_checks_all_corner_face_and_neighbor_data(self):
        validate_topology(quad_data(),vertices=4,faces=1,corners=4,check=lambda:None)
        edits={'corners.u32':(0,'<I',1),'face_ids.u32':(0,'<I',1),'face_ranges.u32':(0,'<I',1),
            'face_vertices.u32':(0,'<I',4),'neighbor_ranges.u32':(0,'<I',1),
            'neighbors.u32':(0,'<I',2),'corner_indices.u32':(0,'<I',1),
            'offsets_vec4.f32':(0,'<f',float('nan'))}
        for name,(offset,fmt,value) in edits.items():
            with self.subTest(name=name):
                data=quad_data();changed=bytearray(data[name]);struct.pack_into(fmt,changed,offset,value);data[name]=bytes(changed)
                with self.assertRaises(ValidationError):validate_topology(data,vertices=4,faces=1,corners=4,check=lambda:None)

    def test_triangle_diagonals_allowed_but_winding_duplicates_and_crossings_reject(self):
        for triangles in [[(0,1,2),(0,2,3)],[(0,1,3),(1,2,3)]]:
            validate_triangles([(0,1,2,3)],triangles,lambda:None)
        for triangles in [[(0,1,2)],[(0,1,2),(0,1,2)],[(0,2,1),(0,3,2)],[(0,1,2),(0,2,4)]]:
            with self.assertRaises(ValidationError):validate_triangles([(0,1,2,3)],triangles,lambda:None)

    def test_step_tracks_require_exactly_identical_native_endpoints(self):
        end=struct.unpack('<f',struct.pack('<f',299/30))[0]
        self.assertFalse(validate_clock([0.,end],'STEP',[(0.,0.,1.),(0.,0.,1.)]))
        for times,mode,values in [([0.,end],'STEP',[(0.,),(0.000001,)]),
            ([0.,end],'CUBICSPLINE',[(0.,),(0.,)]),([0.,1.],'LINEAR',[(0.,),(0.,)])]:
            with self.assertRaises(ValidationError):validate_clock(times,mode,values)

    def test_atomic_retention_is_explicitly_unexecuted_and_does_not_run_code(self):
        self.doubles();result=self.retain()
        self.assertFalse(result.runtime_execution_verified)
        self.assertTrue((result.directory/'.gdignore').is_file())
        self.assertEqual(json.loads((result.directory/'request.json').read_text()),self.f.request.to_dict())
        self.assertEqual(self.f.store.file.read_bytes(),self.f.original_metadata)
        self.assertEqual(self.f.master.read_bytes(),self.f.original_master)

    def test_precancel_stale_revision_and_escaped_evidence_preserve_originals(self):
        self.doubles();cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.retain(cancel=cancel)
        with self.assertRaises(ProjectConflict):
            retain_private_native_runtime_inputs(self.f.store,replace(self.f.request,revision=4),**self.f.kwargs())
        outside=self.f.root/'outside';outside.write_bytes(self.f.review.read_bytes())
        kwargs=self.f.kwargs();kwargs['native_evidence']['native_review']=outside
        with self.assertRaises(ProjectStorageError):retain_private_native_runtime_inputs(self.f.store,self.f.request,**kwargs)
        self.preserved()

    def test_midflight_source_mutation_cancellation_and_deadline_stop_retention(self):
        for mode in ['source','cancel','timeout']:
            with self.subTest(mode=mode):
                # Each case gets an isolated fixture/job and real filesystem copies.
                self.setUp();cancel=Event()
                def callback(folder):
                    if folder.name=='inputs':
                        if mode=='source':self.f.motion.write_bytes(b'UNIT_CHANGED')
                        if mode=='cancel':cancel.set()
                        if mode=='timeout':time.sleep(.07)
                self.doubles(callback)
                with self.assertRaises((ProjectStorageError,WorkerFailure)):
                    self.retain(cancel=cancel,timeout_s=.05 if mode=='timeout' else 120)
                self.preserved()

    def test_final_journal_failure_rolls_new_candidate_back_to_staging(self):
        self.doubles();real_replace=__import__('os').replace
        def replace_status(source,destination):
            if b'PRIVATE_INPUTS_RETAINED_NOT_EXECUTED' in Path(source).read_bytes():raise OSError('unit final-journal failure')
            return real_replace(source,destination)
        with patch('ucc.jobs.godot_runtime_bundle.os.replace',side_effect=replace_status):
            with self.assertRaisesRegex(OSError,'unit final-journal failure'):self.retain()
        self.preserved()
        work=self.f.store.root/'.ucc-jobs'/('native-runtime-'+self.f.request.job_id)
        self.assertTrue((work/'inputs/request.json').is_file())

    def test_existing_job_evidence_never_overwritten(self):
        self.doubles();self.retain()
        with self.assertRaisesRegex(ProjectStorageError,'already exists'):self.retain()

    def test_registered_library_noai_cannot_be_removed_by_per_use_permission(self):
        library=self.f.store.root/'unit-library.json';library.write_text('{"rights":{"no_ai":true}}')
        digest=sha256(library.read_bytes()).hexdigest();old=self.f.request
        permission=replace(old.permissions[0],asset_id='expression_library',source_sha256=digest,
            policy=replace(self.f.policy,no_ai=False,ai_input_allowed=True))
        self.f.request=replace(old,source_bindings=(*old.source_bindings,('expression_library',digest)),
            permissions=(*old.permissions,permission))
        with patch('ucc.jobs.godot_runtime_bundle.project_sources',return_value={'master':self.f.master,'expression_library':library}):
            with self.assertRaisesRegex(ValidationError,'NoAI'):self.retain()
        self.preserved()

    def test_busy_project_lock_respects_total_deadline_and_preserves_lock(self):
        self.doubles();lock=self.f.store.root/'.project.ucc.lock';lock.write_text('UNIT_OTHER_EDITOR_LOCK')
        with self.assertRaises((ProjectConflict,WorkerFailure)):self.retain(timeout_s=.06)
        self.assertEqual(lock.read_text(),'UNIT_OTHER_EDITOR_LOCK');self.preserved()

    def test_cancellation_after_atomic_rename_rolls_new_inputs_back(self):
        self.doubles();cancel=Event();real_rename=__import__('os').rename
        def rename(source,destination):
            real_rename(source,destination);cancel.set()
        with patch('ucc.jobs.godot_runtime_bundle.os.rename',side_effect=rename):
            with self.assertRaises(ProjectStorageError):self.retain(cancel=cancel)
        self.preserved()


if __name__=='__main__':unittest.main()
