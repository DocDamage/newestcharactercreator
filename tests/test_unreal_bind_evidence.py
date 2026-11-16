"""Generated logical evidence only; these tests never launch an engine."""
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from hashlib import sha256
from fixtures.unreal_bind_evidence import write_inputs,write_json
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.export.unreal_bind_evidence import verify_unreal_bind
from ucc.export.unreal_contract import READINESS_FLAGS


class UnrealBindEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.args=write_inputs(self.root)

    def test_generated_finite_pair_has_only_bind_admission(self):
        result=verify_unreal_bind(**self.args)
        self.assertTrue(result.native_bind_verified);self.assertTrue(result.saved_reopened_bind_verified)
        self.assertEqual((result.source_vertices,result.native_vertices,result.triangles,result.bones,result.morphs),(6,6,8,2,1))
        self.assertTrue(all(result.to_dict()[name] is False for name in READINESS_FLAGS))
        self.assertEqual(result.max_normalized_weight_error,0)

    def test_changed_file_fails_seal_before_admission(self):
        self.args['source_normals'].write_bytes(self.args['source_normals'].read_bytes()+bytes([0]))
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_resealed_source_private_baseline_field_rejected(self):
        path=self.args['source_reference'];value=json.loads(path.read_text());value['sdk_unit_proof_sha256']='f'*64
        self.args['source_reference_sha256']=write_json(path,value)
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_reopened_readback_difference_rejected(self):
        path=self.args['reopened_native_observation'];value=json.loads(path.read_text())
        value['readback']['materials'][0]['roughness']=.6
        self.args['reopened_native_observation_sha256']=write_json(path,value)
        receipt=self.args['reopened_receipt'];record=json.loads(receipt.read_text())
        record['native_observation_sha256']=self.args['reopened_native_observation_sha256']
        self.args['reopened_receipt_sha256']=write_json(receipt,record)
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_receipt_actual_option_change_rejected(self):
        path=self.args['stage_receipt'];value=json.loads(path.read_text())
        value['actual_lod_build_settings']['use_high_precision_skin_weights']=False
        self.args['stage_receipt_sha256']=write_json(path,value)
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_receipt_toolchain_change_rejected(self):
        path=self.args['stage_receipt'];value=json.loads(path.read_text());value['toolchain_identity_sha256']='b'*64
        self.args['stage_receipt_sha256']=write_json(path,value)
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_receipt_unverified_flag_cannot_be_promoted(self):
        path=self.args['stage_receipt'];value=json.loads(path.read_text());value['runtime_gpu_verified']=True
        self.args['stage_receipt_sha256']=write_json(path,value)
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_duplicate_json_field_rejected_even_when_resealed(self):
        path=self.args['stage_receipt'];data=path.read_text().rstrip()
        path.write_text(data[:-1]+',"schema_version":1}',encoding='utf-8')
        self.args['stage_receipt_sha256']=sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)

    def test_cancel_and_expired_deadline_do_not_admit(self):
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):verify_unreal_bind(**self.args,cancel=cancel)
        with self.assertRaises(ProjectStorageError):verify_unreal_bind(**self.args,deadline=0.)

    def test_genuine_redirected_input_rejected_without_touching_target(self):
        import os
        root=self.root;target=root/'original';target.mkdir()
        original=self.args['source_reference'];moved=target/original.name;original.replace(moved)
        alias=root/'redirect'
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(target),str(alias))
        else:alias.symlink_to(target,target_is_directory=True)
        before=moved.read_bytes()
        try:
            self.args['source_reference']=alias/moved.name
            with self.assertRaises(ValidationError):verify_unreal_bind(**self.args)
            self.assertEqual(moved.read_bytes(),before)
        finally:
            if os.name=='nt':os.rmdir(alias)
            else:alias.unlink()

    def test_fixture_resolves_temporary_directory_alias_before_writing(self):
        import os
        target=self.root/'fixture-target';target.mkdir();alias=self.root/'fixture-alias'
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(target),str(alias))
        else:alias.symlink_to(target,target_is_directory=True)
        try:
            args=write_inputs(alias)
            self.assertEqual(args['source_reference'].parent,target)
            self.assertTrue(verify_unreal_bind(**args).saved_reopened_bind_verified)
        finally:
            if os.name=='nt':os.rmdir(alias)
            else:alias.unlink()


if __name__=='__main__':unittest.main()
