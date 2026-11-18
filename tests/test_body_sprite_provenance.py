"""Closed original-origin declarations, retaining the historical harness failure."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest

from fixtures.body_sprite_sources import BodySourceFixture
from ucc.core.errors import UCCError
from ucc.core.target_action_format import canonical_bytes, document_sha256
from ucc.jobs.body_sprite_provenance import OriginalMotionProvenance, AUDIT_STATUS, review_original_motion_record
from ucc.jobs.master_preview import _digest
from ucc.jobs.target_action_context import operation_budget


class QualifiedOriginalOriginTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.f=BodySourceFixture(self.root)
        self.policy=replace(self.f.f.policy,source_uri='ucc-original-diagnostic://unit/original300')
        source=replace(self.f.binding.source,catalog_policy_sha256=document_sha256(self.policy.to_dict()))
        self.request=replace(self.f.request,target_binding=replace(self.f.binding,source=source))
        self.raw={'Blender_work_reexecuted_for_audit':False,
            'all300_source_pose_skin_root_palm_observations_rechecked':True,
            'animation_visual_quality_verified':False,'engine_import_verified':False,
            'independent_target_workers':list(self.f.binding.producer.body_worker_job_ids),'mapped_joints':59,
            'mapping_sha256':self.f.binding.mapping_sha256,'master_sha256':self.f.binding.target.master_sha256,
            'next_task':'UNIT_ONLY no native execution','original_script63_exit_success':False,
            'preserved_originals':{'UNIT_SOURCE_PATH':source.source_sha256},'private_views_independently_decoded':15,
            'recorded_at':'2026-11-17T00:00:00Z','recovered_preview_sha256':'a'*64,'retargeting_verified':False,
            'saved_reopen_job_id':self.f.binding.producer.body_reopen_job_id,'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1',
            'snapshot_sha256':source.snapshot_sha256,'source_bones':71,'source_first_frame':2,'source_fps':30.,
            'source_frames':300,'source_permission':self.policy.to_dict(),'source_sha256':source.source_sha256,
            'status':AUDIT_STATUS,'timeline_sha256':'b'*64}
        self.path=self.root/'UNIT_QUALIFIED_ORIGIN_AUDIT.json'

    def read(self,**kwargs):
        self.path.write_bytes(canonical_bytes(self.raw))
        provenance=OriginalMotionProvenance(self.path,_digest(self.path),kwargs.get('role','source_permission'),kwargs.get('aliases',()))
        with operation_budget(None,30) as budget:return provenance.read(self.request,self.policy,budget)

    def test_qualified_origin_preserves_failed_original_script_and_infers_no_sprite_rights(self):
        result=self.read()
        self.assertIs(result['original_script_exit_success'],False)
        self.assertEqual(result['record_status'],AUDIT_STATUS)
        self.assertIs(result['origin_declaration_only'],True)
        self.assertIs(result['sprite_rights_inferred'],False)

    def test_relabelled_original_success_or_partial_independent_recheck_rejects(self):
        for key,value in (('original_script63_exit_success',True),
                          ('all300_source_pose_skin_root_palm_observations_rechecked',False),
                          ('source_frames',299),('source_first_frame',1),('source_fps',24)):
            old=self.raw[key];self.raw[key]=value
            with self.subTest(field=key),self.assertRaises(UCCError):self.read()
            self.raw[key]=old

    def test_unknown_fields_role_alias_and_policy_changes_cannot_relax_the_qualified_record(self):
        with self.assertRaises(UCCError):self.read(role='motion:missing')
        with self.assertRaises(UCCError):self.read(aliases=((self.policy.source_uri,self.policy.source_uri),))
        self.raw['source_permission']['can_use_non_unreal']=True
        with self.assertRaises(UCCError):self.read()
        self.raw['source_permission']=self.policy.to_dict();self.raw['extra']='UNREVIEWED'
        with self.assertRaises(UCCError):self.read()

    def test_binding_only_metadata_review_pins_qualified_failed_record_without_request_or_permissions(self):
        self.path.write_bytes(canonical_bytes(self.raw))
        with operation_budget(None,30) as budget:
            origin,metadata=review_original_motion_record(self.path,self.request.target_binding,self.policy,budget)
            self.assertEqual(origin.motion_role,'source_permission')
            self.assertEqual(origin.expected_sha256,_digest(self.path))
            self.assertIs(metadata['sprite_rights_inferred'],False)
            self.assertIs(metadata['original_script_exit_success'],False)
            self.path.write_bytes(canonical_bytes(self.raw)+b' ')
            with self.assertRaises(UCCError):origin.read_binding(self.request.target_binding,self.policy,budget)

    def test_metadata_review_rejects_malformed_unrelated_and_uri_or_policy_changes(self):
        for payload in (b'{',b'{}',b'[]',b'0',b'x'*(256*1024+1)):
            self.path.write_bytes(payload)
            with self.subTest(payload_bytes=len(payload)),operation_budget(None,30) as budget,self.assertRaises(UCCError):
                review_original_motion_record(self.path,self.request.target_binding,self.policy,budget)
        self.path.write_bytes(canonical_bytes(self.raw))
        for policy in (replace(self.policy,source_uri='ucc-original-diagnostic://unit/OTHER'),
                       replace(self.policy,provider='DIFFERENT_DECLARATION')):
            with operation_budget(None,30) as budget,self.assertRaises(UCCError):
                review_original_motion_record(self.path,self.request.target_binding,policy,budget)

    def test_legacy_unique_motion_role_is_inferred_and_ambiguous_or_other_source_is_rejected(self):
        raw=json.loads(self.f.author_record.read_bytes())
        selected=next(row for row in raw['permissions'] if row['asset_id']==raw['motion_asset_id'])
        from ucc.library.provenance import LicensePolicy
        policy=LicensePolicy.from_dict(selected['policy'])
        binding=replace(self.f.binding,source=replace(self.f.binding.source,
            catalog_policy_sha256=document_sha256(policy.to_dict())))
        self.path.write_bytes(canonical_bytes(raw))
        with operation_budget(None,30) as budget:
            origin,_=review_original_motion_record(self.path,binding,policy,budget)
        self.assertEqual(origin.motion_role,raw['motion_asset_id'])
        second={**selected,'asset_id':'motion:UNIT_AMBIGUOUS'}
        raw['permissions'].append(second)
        raw['source_bindings'][second['asset_id']]=selected['source_sha256']
        self.path.write_bytes(canonical_bytes(raw))
        with operation_budget(None,30) as budget,self.assertRaises(UCCError):
            review_original_motion_record(self.path,binding,policy,budget)
        raw=json.loads(self.f.author_record.read_bytes())
        raw['source_bindings'][raw['motion_asset_id']]='e'*64
        self.path.write_bytes(canonical_bytes(raw))
        with operation_budget(None,30) as budget,self.assertRaises(UCCError):
            review_original_motion_record(self.path,binding,policy,budget)


if __name__=='__main__':unittest.main()
