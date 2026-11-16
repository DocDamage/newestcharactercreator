"""Generated proof-graph faults; actual native target admission is a separate gate."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import os

from fixtures.target_action_evidence import ProofFiles
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs.target_action_evidence import _json, _neutral, _request_binding, _worker, validate_retained_target_action


class TargetActionEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.proofs = ProofFiles(self.root)

    def test_preparation_lineage_matches_all_authority_fields(self):
        p = self.proofs; _request_binding(p.request, p.binding)
        variants = [replace(p.binding, mapping_sha256='1'*64),
                    replace(p.binding, root_motion_policy='SOURCE_HIP_MIDPOINT_V1'),
                    replace(p.binding, target=replace(p.binding.target, revision=5)),
                    replace(p.binding, target=replace(p.binding.target, master_sha256='1'*64)),
                    replace(p.binding, source=replace(p.binding.source, catalog_record_sha256='1'*64)),
                    replace(p.binding, producer=replace(p.binding.producer, worker_resources_sha256='1'*64)),
                    replace(p.binding, producer=replace(p.binding.producer, blender_executable_sha256='1'*64))]
        for value in variants:
            with self.subTest(value=value.sha256), self.assertRaises(ValidationError):
                _request_binding(p.request, value)

    def test_two_neutral_workers_bind_exact_state_and_rest(self):
        p = self.proofs; p.neutral_pair()
        self.assertEqual(_neutral(self.root, p.binding, lambda: None), p.neutral())

    def test_resealed_neutral_state_rest_master_and_approval_faults(self):
        for key, value in (('state_sha256','1'*64),('rest_sha256','1'*64),
                           ('master_sha256','1'*64),('source_provenance_verified',True),
                           ('expression_key_count',3),('expression_key_count',False),('action_count',1)):
            p = self.proofs; p.neutral_pair(); name='neutral/second_result.json'
            raw=json.loads((self.root/name).read_text()); raw['details'][key]=value; p.write(name,raw)
            with self.subTest(key=key), self.assertRaises(ValidationError):_neutral(self.root,p.binding,lambda:None)

    def test_resealed_worker_wrong_job_operation_options_and_result_error_reject(self):
        p=self.proofs; job=p.binding.producer.source_intake_worker_job_ids[0]
        options={'source_sha256':p.binding.source.source_sha256}
        for side,key,value in (('request','job_id',p.binding.producer.source_intake_worker_job_ids[1]),
                               ('result','job_id',p.binding.producer.source_intake_worker_job_ids[1]),
                               ('result','operation','inspect_environment'),('result','error','unexpected failure'),
                               ('result','protocol_version',True),('request','options',{'source_sha256':'f'*64})):
            request,result=p.worker('source_intake_first',job,'inspect_fbx_animation',options,{},input_project=None)
            raw=request if side=='request' else result; raw[key]=value
            p.write('source_intake_first/'+side+'.json',raw)
            with self.subTest(side=side,key=key),self.assertRaises(ValidationError):
                _worker(self.root,'source_intake_first',job,'inspect_fbx_animation',options,p.binding,lambda:None,input_project=None)

    def test_retained_intake_request_uses_no_character_input(self):
        p=self.proofs; job=p.binding.producer.source_intake_worker_job_ids[0];options={'source_sha256':p.binding.source.source_sha256}
        p.worker('source_intake_first',job,'inspect_fbx_animation',options,{'generated_metadata_only':True},input_project=None)
        self.assertEqual(_worker(self.root,'source_intake_first',job,'inspect_fbx_animation',options,p.binding,lambda:None,input_project=None),{'generated_metadata_only':True})

    def test_body_render_flag_preserves_boolean_type_and_first_second_roles(self):
        p=self.proofs;job=p.binding.producer.body_worker_job_ids[0]
        options={'source_sha256':p.binding.source.source_sha256,
                 'snapshot_sha256':p.binding.source.snapshot_sha256,
                 'mapping_sha256':p.binding.mapping_sha256,'master_sha256':p.binding.target.master_sha256,
                 'render_private_frames':True}
        for value in (False,1):
            request,result=p.worker('body_first',job,'verify_native_fbx_body',options,{})
            request['options']['render_private_frames']=value;p.write('body_first/request.json',request)
            with self.subTest(value=value),self.assertRaises(ValidationError):
                _worker(self.root,'body_first',job,'verify_native_fbx_body',options,p.binding,lambda:None)

    def test_reopen_cannot_swap_a_different_saved_action_even_when_resealed(self):
        p=self.proofs;job=p.binding.producer.body_reopen_job_id
        options={'source_sha256':p.binding.source.source_sha256,
                 'snapshot_sha256':p.binding.source.snapshot_sha256,
                 'mapping_sha256':p.binding.mapping_sha256,'master_sha256':p.binding.target.master_sha256,
                 'review_sha256':'a'*64,'timeline_sha256':'b'*64}
        request,result=p.worker('body_reopen',job,'reopen_native_fbx_body',options,{})
        request['options']['review_sha256']='f'*64;p.write('body_reopen/request.json',request)
        with self.assertRaises(ValidationError):
            _worker(self.root,'body_reopen',job,'reopen_native_fbx_body',options,p.binding,lambda:None)

    def test_changed_proof_and_resealed_duplicate_or_nonfinite_json_reject(self):
        p=self.proofs;name='neutral/first_result.json'
        for data in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"unused":{"overflow":1e999}}',b'[]',b'\xff'):
            p.bytes(name,data)
            with self.subTest(data=data),self.assertRaises(ValidationError):_json(self.root,name,p.binding,lambda:None)
        p.write(name,{'a':1});(self.root/name).write_text('{"a":2}')
        with self.assertRaises(ValidationError):_json(self.root,name,p.binding,lambda:None)

    def test_opened_file_identity_must_match_path_even_with_identical_bytes(self):
        p=self.proofs;name='neutral/first_result.json';path=p.write(name,{'generated':True})
        replacement=self.root/'byte-identical-other.json';replacement.write_bytes(path.read_bytes())
        original_open=Path.open
        def other_stream(selected,*args,**kwargs):
            return original_open(replacement if selected==path else selected,*args,**kwargs)
        with patch.object(Path,'open',other_stream):
            with self.assertRaises(ValidationError):_json(self.root,name,p.binding,lambda:None)
        self.assertEqual(path.read_bytes(),replacement.read_bytes())

    def test_actual_byte_identical_replacement_during_open_is_rejected(self):
        p=self.proofs;name='neutral/first_result.json';path=p.write(name,{'generated':True})
        replacement=self.root/'replacement.json';replacement.write_bytes(path.read_bytes())
        retained=self.root/'original.json';original_open=Path.open
        def replace_at_open(selected,*args,**kwargs):
            if selected==path:
                path.replace(retained);replacement.replace(path)
            return original_open(selected,*args,**kwargs)
        with patch.object(Path,'open',replace_at_open):
            with self.assertRaises(ValidationError):_json(self.root,name,p.binding,lambda:None)
        self.assertEqual(path.read_bytes(),retained.read_bytes())

    def test_fd_metadata_changes_during_read_are_rejected(self):
        p=self.proofs;name='neutral/first_result.json';p.write(name,{'generated':True})
        original=os.fstat
        for field in ('st_ino','st_mtime_ns','st_ctime_ns'):
            calls=0
            def changed(fd):
                nonlocal calls
                calls+=1;s=original(fd)
                values={k:getattr(s,k)for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')}
                if calls==2:values[field]+=1
                return SimpleNamespace(**values)
            with self.subTest(field=field),patch('ucc.jobs.target_action_evidence.os.fstat',changed):
                with self.assertRaises(ValidationError):_json(self.root,name,p.binding,lambda:None)

    def test_stable_distinct_path_and_fd_ctime_semantics_preserve_identity_checks(self):
        p=self.proofs;name='neutral/first_result.json';p.write(name,{'generated':True})
        original=os.fstat
        def stable_fd_ctime(fd):
            s=original(fd)
            return SimpleNamespace(**{k:getattr(s,k)for k in ('st_dev','st_ino','st_size','st_mtime_ns')},
                                   st_ctime_ns=s.st_ctime_ns+1000)
        with patch('ucc.jobs.target_action_evidence.os.fstat',stable_fd_ctime):
            self.assertEqual(_json(self.root,name,p.binding,lambda:None),{'generated':True})

    def test_json_byte_limit_checked_before_opening_payload(self):
        p=self.proofs;p.bytes('neutral/first_result.json',b'x'*100)
        with patch.object(Path,'open',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValidationError):_json(self.root,'neutral/first_result.json',p.binding,lambda:None,10)

    def test_pre_cancel_stops_before_any_retained_file_read(self):
        def cancelled():raise ProjectStorageError('synthetic cancel')
        with patch.object(Path,'open',side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ProjectStorageError,'synthetic cancel'):
                validate_retained_target_action(self.root,self.proofs.binding,cancel_check=cancelled)

    def test_genuine_redirected_proof_rejected_and_original_bytes_preserved(self):
        import os
        p=self.proofs;p.neutral_pair();alias=self.root/'neutral';actual=self.root/'original-neutral'
        alias.replace(actual)
        if os.name=='nt':
            import _winapi
            _winapi.CreateJunction(str(actual),str(alias))
        else:alias.symlink_to(actual,target_is_directory=True)
        before=(actual/'first_result.json').read_bytes()
        try:
            with self.assertRaises(ValidationError):
                _json(self.root,'neutral/first_result.json',p.binding,lambda:None)
        finally:
            if os.name=='nt':os.rmdir(alias)
            else:alias.unlink()
        self.assertEqual((actual/'first_result.json').read_bytes(),before)


if __name__=='__main__':unittest.main()
