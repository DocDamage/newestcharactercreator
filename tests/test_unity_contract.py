"""Closed identities and engine-specific per-use rights; no model/engine fixture."""
from copy import deepcopy
from dataclasses import replace
import unittest
from ucc.core.errors import ValidationError
from ucc.library.provenance import AssetPolicyError
from ucc.export.unity_contract import UnityExportRequest,MAX_REQUEST_BYTES
from ucc.export.godot_candidate_contract import canonical_bytes
from fixtures.unity_contract_logic import request


class UnityContractTests(unittest.TestCase):
    def test_closed_roundtrip_binds_editor_and_original_sources(self):
        original=request();encoded=canonical_bytes(original.to_dict())
        self.assertEqual(UnityExportRequest.from_bytes(encoded),original)
        self.assertNotEqual(replace(original,unity_executable_sha256='0'*64).sha256,original.sha256)
        self.assertNotEqual(replace(original,revision=2).sha256,original.sha256)

    def test_profile_bool_numeric_substitution_and_approval_forgery_reject(self):
        for key,value in [('schema_version',True),('revision',True),('engine_version','6000.6.4f1'),
                          ('render_pipeline','URP'),('graphics_api','VULKAN'),('profile','other'),
                          ('animation_clips',True),('engine_import_verified',True),('runtime_render_verified',True),
                          ('visual_quality_approved',True),('cloud_transmission_authorized',True),
                          ('distribution_license_review_complete',True),('extra',1)]:
            raw=deepcopy(request().to_dict());raw[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):UnityExportRequest.from_dict(raw)

    def test_unity_export_is_not_preview_unreal_only_or_source_only_permission(self):
        original=request();permission=original.permissions[0]
        for flags in ({'reviewed':False},{'ue_only':True},{'can_use_non_unreal':False,'can_use_unreal':True},
                      {'can_use_non_unreal':False,'local_preview_allowed':True},{'no_ai':False},
                      {'ai_input_allowed':True},{'redistribute_source_allowed':True}):
            bad=replace(permission,policy=replace(permission.policy,**flags))
            with self.subTest(flags=flags),self.assertRaises((ValidationError,AssetPolicyError)):
                replace(original,permissions=(bad,*original.permissions[1:]))
        with self.assertRaises(AssetPolicyError):replace(original,permissions=(replace(permission,source_only=True),*original.permissions[1:]))
        for target in ('Unity','other',None,True):
            with self.assertRaises(AssetPolicyError):permission.require_engine(target)

    def test_duplicate_missing_or_rebound_source_cannot_reuse_permission(self):
        original=request();permission=original.permissions[0]
        for changes in ({'permissions':original.permissions[:-1]},
                        {'permissions':(permission,permission,*original.permissions[2:])},
                        {'source_bindings':(original.source_bindings[0],)*4},
                        {'permissions':(replace(permission,source_sha256='0'*64),*original.permissions[1:])},
                        {'job_id':original.job_id.upper()},{'project_id':'bad\nidentity'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):replace(original,**changes)

    def test_duplicate_json_nonfinite_oversize_and_unknown_license_fields_reject(self):
        raw=request().to_dict();encoded=canonical_bytes(raw)
        for data in (b'{"job_id":"a","job_id":"b"}',b'{"revision":NaN}',b'\xff',b' '*(MAX_REQUEST_BYTES+1)):
            with self.assertRaises(ValidationError):UnityExportRequest.from_bytes(data)
        raw['permissions'][0]['policy']['extra']=True
        with self.assertRaises(ValidationError):UnityExportRequest.from_dict(raw)
        self.assertEqual(UnityExportRequest.from_bytes(encoded).sha256,request().sha256)
