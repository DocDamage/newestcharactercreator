"""Synthetic boundary tests; genuine FBX/Blender acceptance is separate."""
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.metadata import AnimationMetadataError
from ucc.core.errors import ValidationError
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import LicensePolicy, AssetPolicyError


class MeasuredFbxCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.db = self.root/'catalog.db'
        self.source = self.root/'source.fbx'; self.source.write_bytes(b'SYNTHETIC_NOT_ACTUAL_FBX')
        self.original = self.source.read_bytes(); self.jobs = self.root/'private-jobs'
        self.policy = LicensePolicy('Original', 'CC0', 'local-original://fixture',
                                    reviewed=True, local_preview_allowed=True, no_ai=True)
        self.fault = None
        with AnimationCatalog(self.db) as catalog:
            catalog.index_file('original', self.source, self.policy)

    def intake(self, source, **kwargs):
        data = snapshot(); data['source_sha256'] = sha256(self.original).hexdigest()
        if self.fault == 'different_action': data['action'] = 'Another measured Action'
        folder = self.jobs/'first'; folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data).encode(); path = folder/'source_snapshot.json'; path.write_bytes(payload)
        result = {**report(data, payload), 'source_path': str(source.resolve()),
                  'private_snapshot': str(path), 'policy': self.policy.to_dict(),
                  'two_workers_agree': True, 'source_bytes_unchanged': True}
        if self.fault == 'report': result['fps'] = 31.
        if self.fault == 'agreement': result['two_workers_agree'] = False
        if self.fault == 'source': source.write_bytes(b'changed')
        if self.fault == 'snapshot': path.write_bytes(payload+b'changed')
        if self.fault == 'escape':
            other = self.root/'outside'; other.mkdir(); (other/path.name).write_bytes(payload)
            result['private_snapshot'] = str(other/path.name)
        if self.fault == 'cancel': kwargs['cancel'].set()
        if self.fault == 'policy':
            with AnimationCatalog(self.db) as catalog:
                catalog.db.execute("UPDATE asset_sources SET license_json=? WHERE asset_id='original'",
                                   (json.dumps(LicensePolicy('Changed', 'unknown', 'local://changed').to_dict()),))
                catalog.db.commit()
        return result

    def invoke(self, **kwargs):
        with patch('ucc.jobs.fbx_catalog.inspect_selected_fbx', side_effect=self.intake):
            return measure_catalog_fbx(self.db, 'original', blender_exe=Path('unused'),
                worker_script=Path('unused'), jobs_root=self.jobs, **kwargs)

    def assert_unmeasured(self):
        with AnimationCatalog(self.db) as catalog:
            indexed = catalog.get('original')
            self.assertEqual(indexed.status, 'REQUIRES_CONVERSION')
            self.assertEqual(indexed.clips, ())
            self.assertEqual(catalog.db.execute('SELECT COUNT(*) FROM animation_fbx_intakes').fetchone()[0], 0)

    def test_actual_sampled_object_track_metadata_stable_id_and_reopen(self):
        result = self.invoke()
        self.assertEqual(result['status'], 'METADATA_EXTRACTED')
        clip, = result['clips']
        self.assertEqual(clip['clip_id'], 'original#clip-0000')
        self.assertEqual((clip['frame_count'], clip['fps'], clip['track_count']), (4, 30., 1))
        self.assertEqual(clip['animated_bones'], [])  # Object motion is not fabricated bone motion.
        self.assertAlmostEqual(clip['duration_seconds'], .1)
        self.assertFalse(result['preview_verified']); self.assertFalse(result['retarget_verified'])
        self.assertFalse(result['engine_validated'])
        self.assertIn('BLOCKED', result['permissions']['ai_input'])
        self.assertIn('BLOCKED', result['permissions']['godot'])
        self.assertEqual(self.source.read_bytes(), self.original)
        with AnimationCatalog(self.db) as catalog:
            receipt = catalog.db.execute('SELECT receipt_json FROM animation_fbx_intakes').fetchone()[0]
            self.assertNotIn('poses', receipt); self.assertNotIn(str(self.root), receipt)
            before = list(catalog.db.iterdump())
            self.assertEqual(catalog.get('original').to_dict(), result)
        self.assertEqual(self.invoke(), result)
        with AnimationCatalog(self.db) as catalog: self.assertEqual(list(catalog.db.iterdump()), before)

    def test_source_hash_change_prevents_worker_and_publication(self):
        self.source.write_bytes(b'changed')
        with patch('ucc.jobs.fbx_catalog.inspect_selected_fbx') as worker:
            with self.assertRaisesRegex(ValidationError, 'source'): self.invoke_without_patch()
            worker.assert_not_called()
        self.assert_unmeasured()

    def invoke_without_patch(self):
        return measure_catalog_fbx(self.db, 'original', blender_exe=Path('unused'),
            worker_script=Path('unused'), jobs_root=self.jobs)

    def test_unreviewed_and_ue_only_policies_never_start_worker(self):
        for policy in (LicensePolicy('Original', 'CC0', 'local://fixture'),
                       LicensePolicy('Original', 'CC0', 'local://fixture', reviewed=True,
                                     local_preview_allowed=True, ue_only=True)):
            with AnimationCatalog(self.db) as catalog:
                catalog.db.execute('UPDATE asset_sources SET license_json=?', (json.dumps(policy.to_dict()),))
                catalog.db.commit()
            with patch('ucc.jobs.fbx_catalog.inspect_selected_fbx') as worker:
                with self.assertRaises(AssetPolicyError): self.invoke_without_patch()
                worker.assert_not_called()
            self.assert_unmeasured()

    def test_malformed_report_disagreement_changed_inputs_and_escape_leave_no_clip(self):
        for fault in ('report', 'agreement', 'source', 'snapshot', 'escape'):
            with self.subTest(fault=fault):
                self.fault = fault
                with self.assertRaises((ValidationError, AssetPolicyError)): self.invoke()
                self.assert_unmeasured(); self.source.write_bytes(self.original)

    def test_cancellation_after_real_intake_boundary_leaves_no_clip(self):
        self.fault = 'cancel'
        with self.assertRaises(WorkerFailure): self.invoke(cancel=Event())
        self.assert_unmeasured()

    def test_changed_database_policy_is_not_overwritten_by_completed_job(self):
        self.fault = 'policy'
        with self.assertRaisesRegex(AssetPolicyError, 'permissions changed'): self.invoke()
        self.assert_unmeasured()
        with AnimationCatalog(self.db) as catalog:
            self.assertFalse(catalog.library.get('original').policy.reviewed)

    def test_database_failure_rolls_back_status_clip_and_receipt_together(self):
        with AnimationCatalog(self.db) as catalog:
            catalog.db.execute('''CREATE TRIGGER reject_receipt BEFORE INSERT ON animation_fbx_intakes
                                  BEGIN SELECT RAISE(ABORT, 'injected receipt failure'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected receipt failure'): self.invoke()
        self.assert_unmeasured()
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_coherent_different_action_cannot_replace_registered_identity(self):
        original = self.invoke(); self.fault = 'different_action'
        with self.assertRaisesRegex(AnimationMetadataError, 'identity differs'): self.invoke()
        with AnimationCatalog(self.db) as catalog: self.assertEqual(catalog.get('original').to_dict(), original)


if __name__ == '__main__': unittest.main()
