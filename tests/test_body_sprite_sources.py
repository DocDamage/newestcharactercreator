"""Source/policy freshness on real private files with explicit native doubles."""
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fixtures.body_sprite_sources import BodySourceFixture
from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.errors import UCCError, ProjectConflict, ProjectStorageError
from ucc.jobs.body_sprite_sources import prepare_body_sprite_context, _character_sources
from ucc.jobs.target_action_context import operation_budget


class BodySpriteSourcesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.f = BodySourceFixture(self.root)
        self.addCleanup(patch.stopall)
        patch('ucc.jobs.target_action_evidence.validate_retained_target_action', return_value=object()).start()
        prefix = 'ucc.jobs.body_sprite_sources.'
        patch(prefix+'_character_sources', return_value=self.f.paths).start()
        patch(prefix+'worker_dependency_files', return_value={self.f.f.script}).start()
        patch(prefix+'host_code_snapshot', return_value={}).start()
        patch(prefix+'worker_namespace_snapshot', return_value={}).start()
        patch(prefix+'blender_helper_inventory', return_value={}).start()
        self.intake = patch(prefix+'inspect_selected_fbx', side_effect=self.f.intake).start()

    def prepare(self, request=None):
        with operation_budget(None,30) as budget:
            return prepare_body_sprite_context(self.f.store,request or self.f.request,self.f.f.database,
                                               self.f.f.executable,self.f.f.script,budget,self.f.provenance)

    def test_complete_loader_plus_two_fresh_source_records_preserve_project_and_catalog(self):
        project = self.f.store.file.read_bytes(); catalog = self.f.f.database.read_bytes()
        context = self.prepare(); context.guard()
        self.assertEqual(len(self.f.calls),2)
        self.assertEqual(context.source_admission['worker_job_ids'],[job.job_id for job in self.f.calls])
        self.assertEqual(context.snapshot.read_bytes(),(self.f.directory/'source_snapshot.json').read_bytes())
        self.assertEqual(self.f.store.file.read_bytes(),project); self.assertEqual(self.f.f.database.read_bytes(),catalog)
        self.assertEqual(self.f.store.load().animations,self.f.project.animations)

    def test_canonical_snapshot_does_not_substitute_for_actual_saved_file_hash(self):
        self.f.store.file.write_bytes(self.f.store.file.read_bytes()+b' ')
        with self.assertRaises(ProjectConflict): self.prepare()
        self.intake.assert_not_called()

    def test_coherently_changed_fresh_snapshot_cannot_reuse_old_target_binding(self):
        self.f.fault = 'coherent_snapshot'
        with self.assertRaises(UCCError): self.prepare()
        self.assertEqual(len(self.f.calls),2)

    def test_live_policy_revocation_between_intakes_prevents_second_worker(self):
        def revoke():
            connection = sqlite3.connect(self.f.f.database)
            try:
                policy = replace(self.f.f.policy,local_preview_allowed=False)
                connection.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?',
                                   (json.dumps(policy.to_dict()),self.f.f.reference.asset_id)); connection.commit()
            finally: connection.close()
        self.f.after_first = revoke
        with self.assertRaises(UCCError): self.prepare()
        self.assertEqual(len(self.f.calls),1)

    def test_postadmission_source_proof_and_code_changes_are_not_rebaselined(self):
        context = self.prepare(); original = context.snapshot.read_bytes()
        context.snapshot.write_bytes(original+b' ')
        with self.assertRaises(ProjectStorageError): context.guard()
        context.snapshot.write_bytes(original)
        # Restoring bytes is not a new identity baseline: mtime remains changed.
        with self.assertRaises(ProjectStorageError): context.guard()

    def test_changed_retained_payload_rejects_before_fresh_worker(self):
        path = self.f.directory/'body_first/review_motion.blend'; path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(UCCError): self.prepare()
        self.intake.assert_not_called()

    def test_missing_role_or_unbound_uri_alias_rejects_before_intakes(self):
        original = self.f.provenance
        for changed in (replace(original,motion_role='motion:missing'), replace(original,uri_aliases=())):
            self.f.provenance = changed
            with self.assertRaises(UCCError): self.prepare()
            self.intake.assert_not_called()

    def test_changed_original_author_bytes_reject_before_intakes(self):
        path = self.f.author_record; path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(UCCError): self.prepare()
        self.intake.assert_not_called()

    def test_coherently_pinned_thirdparty_source_uri_and_policy_cannot_claim_original_origin(self):
        from ucc.core.target_action_format import canonical_bytes
        from ucc.jobs.master_preview import _digest
        original = self.f.author_record.read_bytes()
        for fault in ('source','uri','policy','snapshot'):
            raw = json.loads(original)
            if fault == 'source':
                raw['source_bindings']['motion:unit-original'] = 'e'*64
                next(row for row in raw['permissions'] if row['asset_id']=='motion:unit-original')['source_sha256'] = 'e'*64
            elif fault == 'snapshot': raw['evidence_bindings']['source_snapshot'] = 'f'*64
            else:
                policy = next(row for row in raw['permissions'] if row['asset_id']=='motion:unit-original')['policy']
                policy['source_uri' if fault=='uri' else 'license_name'] = 'https://thirdparty.invalid/listing' if fault=='uri' else 'Different source policy'
            self.f.author_record.write_bytes(canonical_bytes(raw))
            self.f.provenance = replace(self.f.provenance,expected_sha256=_digest(self.f.author_record))
            with self.subTest(fault=fault), self.assertRaises(UCCError): self.prepare()
            self.intake.assert_not_called()


class BodySpriteCharacterSourcesTests(unittest.TestCase):
    def test_real_registered_hand_expression_readers_keep_all_animation_references(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = ReferenceMasterFixture(Path(directory).resolve())
            project = fixture.store.load(); before = fixture.store.file.read_bytes()
            from types import SimpleNamespace
            binding = SimpleNamespace(target=SimpleNamespace(master_sha256=Path(project.master_blend).stem))
            sources = _character_sources(fixture.store,project,binding,None)
            self.assertEqual(set(sources),{'master','expression_library','part:'+project.parts[0].part_asset_id})
            self.assertEqual(fixture.store.file.read_bytes(),before)
            self.assertEqual(fixture.store.load().animations,project.animations)


if __name__ == '__main__': unittest.main()
