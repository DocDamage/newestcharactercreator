"""Synthetic reference boundaries; actual source verification has a separate gate."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.catalog_clip import MAX_RECEIPT_BYTES
from ucc.animations.metadata import AnimationMetadataError
from ucc.core.errors import ValidationError
from ucc.jobs.catalog_clip import verify_catalog_fbx_clip
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError, LicensePolicy


class CatalogClipReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.database = self.root/'catalog.db'
        self.source = self.root/'original.fbx'; self.source.write_bytes(b'SYNTHETIC_SOURCE_NOT_FBX')
        self.source_sha = sha256(self.source.read_bytes()).hexdigest()
        self.policy = LicensePolicy('Original', 'CC0', 'local-original://fixture', reviewed=True,
                                    local_preview_allowed=True, no_ai=True)
        self.data = snapshot(); self.data['source_sha256'] = self.source_sha
        self.report = {**report(self.data, json.dumps(self.data).encode()), 'two_workers_agree': True,
                       'source_bytes_unchanged': True, 'policy': self.policy.to_dict()}
        with AnimationCatalog(self.database) as c:
            c.index_file('source', self.source, self.policy)
            c.record_fbx_intake('source', self.data, self.report, expected_entry=c.library.get('source'))
            self.original = c.get('source').to_dict()
            self.raw, = c.db.execute('SELECT receipt_json FROM animation_fbx_intakes').fetchone()
            self.clip_json, = c.db.execute('SELECT metadata_json FROM animation_clips').fetchone()
        self.calls = 0

    def kwargs(self):
        return dict(expected_source_sha256=self.source_sha, expected_policy=self.policy,
                    blender_exe=Path('unused'), worker_script=Path('unused'), jobs_root=self.root/'jobs')

    def fresh(self, *args, **kwargs):
        self.calls += 1
        with AnimationCatalog(self.database) as c:
            c.record_fbx_intake('source', self.data, self.report, expected_entry=c.library.get('source'))
            return c.get('source').to_dict()

    def invoke(self, clip_id='source#clip-0000', **overrides):
        kwargs = {**self.kwargs(), **overrides}
        with patch('ucc.jobs.catalog_clip.measure_catalog_fbx', side_effect=self.fresh):
            return verify_catalog_fbx_clip(self.database, clip_id, **kwargs)

    def write_receipt(self, raw, *, clip=None, fingerprint=None):
        with AnimationCatalog(self.database) as c:
            c.db.execute('UPDATE animation_fbx_intakes SET receipt_json=?', (raw,))
            if clip is not None: c.db.execute('UPDATE animation_clips SET metadata_json=?', (json.dumps(clip),))
            if fingerprint is not None: c.db.execute('UPDATE animation_sources SET fingerprint=?', (fingerprint,))
            c.db.commit()

    def test_exact_source_reference_requires_fresh_measurement_and_keeps_approvals_false(self):
        result = self.invoke()
        self.assertEqual(self.calls, 1)
        self.assertEqual((result.clip_id, result.source_sha256), ('source#clip-0000', self.source_sha))
        self.assertEqual((result.first_frame, result.last_frame), (1, 4))
        self.assertEqual(result.license_policy, self.policy)
        self.assertEqual(result.receipt_sha256, sha256(self.raw.encode()).hexdigest())
        self.assertFalse(result.target_preview_verified); self.assertFalse(result.engine_import_verified)
        with AnimationCatalog(self.database) as c: self.assertEqual(c.get('source').to_dict(), self.original)

    def test_unknown_raw_or_malformed_ids_never_start_measurement(self):
        with AnimationCatalog(self.database) as c: c.index_file('raw', self.source, self.policy)
        for name in ('source', 'raw#clip-0000', 'source#clip-0001', '', True, 'a'*139, 'source\n#clip-0000'):
            with self.subTest(name=name), self.assertRaises(AnimationMetadataError): self.invoke(name)
        self.assertEqual(self.calls, 0)

    def test_caller_source_hash_and_exact_policy_are_required_before_measurement(self):
        for overrides in ({'expected_source_sha256': 'b'*64},
                          {'expected_policy': replace(self.policy, no_ai=False)},
                          {'expected_policy': replace(self.policy, reviewed=False)},
                          {'expected_source_sha256': True}):
            with self.subTest(overrides=overrides), self.assertRaises((AnimationMetadataError, AssetPolicyError)):
                self.invoke(**overrides)
        self.assertEqual(self.calls, 0)

    def test_missing_receipt_is_not_repaired_from_untrusted_clip_metadata(self):
        with AnimationCatalog(self.database) as c:
            c.db.execute('DELETE FROM animation_fbx_intakes'); c.db.commit()
        with self.assertRaisesRegex(AnimationMetadataError, 'no measured'): self.invoke()
        self.assertEqual(self.calls, 0)

    def test_duplicate_nonfinite_oversized_and_boolean_schema_receipts_reject(self):
        boolean = json.loads(self.raw); boolean['schema_version'] = True
        for raw in ('{"schema_version":1,"schema_version":1}', 'NaN', '['*2000,
                    ' '*MAX_RECEIPT_BYTES+'0', json.dumps(boolean)):
            with self.subTest(raw=raw[:30]):
                self.write_receipt(raw)
                with self.assertRaises(AnimationMetadataError): self.invoke()
        self.assertEqual(self.calls, 0)

    def test_source_observation_and_clip_bounds_are_checked_before_measurement(self):
        for field, value in (('frame_count', True), ('first_frame', -100001), ('root_count', 0),
                             ('bone_count', 257), ('fps', 0), ('action', 'bad\nname')):
            receipt = json.loads(self.raw); receipt['observation'][field] = value
            self.write_receipt(json.dumps(receipt))
            with self.subTest(field=field), self.assertRaises(AnimationMetadataError): self.invoke()
        self.assertEqual(self.calls, 0)

    def test_bool_alias_in_stored_clip_metadata_is_not_accepted_as_integer_zero(self):
        clip = json.loads(self.clip_json); clip['ordinal'] = False
        self.write_receipt(self.raw, clip=clip)
        with self.assertRaises(AnimationMetadataError): self.invoke()
        self.assertEqual(self.calls, 0)

    def test_oversized_database_metadata_is_rejected_before_json_load_or_measurement(self):
        with AnimationCatalog(self.database) as c:
            c.db.execute('UPDATE animation_sources SET bone_names_json=?', (' '*MAX_RECEIPT_BYTES+'[]',))
            c.db.commit()
        with self.assertRaisesRegex(AnimationMetadataError, 'oversized'): self.invoke()
        self.assertEqual(self.calls, 0)

    def test_coherent_action_rewrite_is_rejected_by_fresh_source_without_repair(self):
        receipt = json.loads(self.raw)
        receipt['observation']['action'] = receipt['clip']['name'] = 'Coherently rewritten Action'
        raw = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
        self.write_receipt(raw, clip=receipt['clip'])
        with self.assertRaisesRegex(AnimationMetadataError, 'identity differs'): self.invoke()
        self.assertEqual(self.calls, 1)
        with AnimationCatalog(self.database) as c:
            self.assertEqual(c.db.execute('SELECT receipt_json FROM animation_fbx_intakes').fetchone()[0], raw)

    def test_coherent_skeleton_signature_rewrite_is_rejected_by_fresh_source(self):
        receipt = json.loads(self.raw); receipt['skeleton_fingerprint'] = 'b'*64
        self.write_receipt(json.dumps(receipt, sort_keys=True, separators=(',', ':')), fingerprint='b'*64)
        with self.assertRaisesRegex(AnimationMetadataError, 'identity differs'): self.invoke()
        self.assertEqual(self.calls, 1)

    def test_source_changed_before_fresh_intake_starts_no_blender(self):
        self.source.write_bytes(b'changed')
        with patch('ucc.jobs.fbx_catalog.inspect_selected_fbx') as worker:
            with self.assertRaisesRegex(ValidationError, 'source'):
                verify_catalog_fbx_clip(self.database, 'source#clip-0000', **self.kwargs())
            worker.assert_not_called()

    def test_cancellation_after_measurement_returns_no_verified_reference(self):
        cancel = Event(); fresh = self.fresh
        def cancelled(*args, **kwargs):
            result = fresh(*args, **kwargs); cancel.set(); return result
        self.fresh = cancelled
        with self.assertRaises(WorkerFailure): self.invoke(cancel=cancel)
        with AnimationCatalog(self.database) as c: self.assertEqual(c.get('source').to_dict(), self.original)


if __name__ == '__main__': unittest.main()
