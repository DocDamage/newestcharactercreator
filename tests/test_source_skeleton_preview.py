"""Synthetic nonshipping source/SQLite preparation tests; no native processes."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError
from ucc.jobs.source_skeleton_preview import prepare_source_skeleton_preview
from ucc.jobs.source_skeleton_files import watch_identity
from ucc.library.provenance import LicensePolicy


class SourceSkeletonPreparationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.source = self.root/'original.fbx'
        self.source.write_bytes(b'NONSHIPPING_SYNTHETIC_NOT_FBX')
        self.source_sha = sha256(self.source.read_bytes()).hexdigest()
        self.database = self.root/'catalog.sqlite3'; self.jobs = self.root/'jobs'; self.jobs.mkdir()
        self.policy = LicensePolicy('Original test', 'Synthetic', 'test://source',
            reviewed=True, no_ai=True, local_preview_allowed=True)
        self.data = snapshot(); self.data['source_sha256'] = self.source_sha
        self.payload = json.dumps(self.data).encode()
        self.report = report(self.data, self.payload) | {'two_workers_agree': True,
            'source_bytes_unchanged': True, 'policy': self.policy.to_dict(),
            'source_path': str(self.source)}
        with AnimationCatalog(self.database) as c:
            c.index_file('source', self.source, self.policy)
            c.record_fbx_intake('source', self.data, self.report, expected_entry=c.library.get('source'))
        self.calls = 0

    def fresh(self, *_args, **kwargs):
        self.calls += 1
        folder = self.jobs/'fresh-owned-job'; folder.mkdir()
        self.snapshot = folder/'source_snapshot.json'; self.snapshot.write_bytes(self.payload)
        return self.report | {'private_snapshot': str(self.snapshot)}

    def invoke(self, **overrides):
        options = dict(expected_source_sha256=self.source_sha, expected_policy=self.policy,
            local_preview_confirmed=True, blender_exe=self.root/'unused',
            worker_script=self.root/'unused.py', jobs_root=self.jobs)
        with patch('ucc.jobs.source_skeleton_preview.inspect_selected_fbx', side_effect=self.fresh):
            return prepare_source_skeleton_preview(self.database, 'source#clip-0000', **(options|overrides))

    def test_fresh_same_buffer_cache_and_background_guard_preserve_originals(self):
        original = self.source.read_bytes(); db = self.database.read_bytes()
        loaded = self.invoke()
        self.assertEqual(self.calls, 1); self.assertEqual(loaded.cache.frame_count, 4)
        self.assertEqual(loaded.source_clock.source_first_frame, 1)
        self.assertEqual(loaded.cache.snapshot_sha256, sha256(self.payload).hexdigest())
        self.assertTrue(loaded.guard(timeout_s=5))
        self.assertEqual(self.source.read_bytes(), original); self.assertEqual(self.database.read_bytes(), db)
        self.assertTrue(set(loaded.watch_paths).issubset(loaded.watched_identities))
        for suffix in ('-wal', '-shm', '-journal'):
            self.assertIn(Path(str(self.database)+suffix), loaded.watched_identities)
        with self.assertRaises(TypeError): loaded.watched_identities[self.source] = (0,0,0,0)

    def test_missing_consent_hash_or_revoked_policy_never_launches(self):
        for kwargs in ({'local_preview_confirmed':False}, {'expected_source_sha256':'b'*64},
                       {'expected_policy':replace(self.policy, local_preview_allowed=False)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(UCCError): self.invoke(**kwargs)
        self.assertEqual(self.calls, 0)

    def test_already_cancelled_and_expired_budget_never_launch(self):
        cancel = Event(); cancel.set()
        for options in ({'cancel':cancel}, {'timeout_s':0}):
            with self.subTest(options=options), self.assertRaises(UCCError): self.invoke(**options)
        self.assertEqual(self.calls, 0)

    def test_fresh_snapshot_hash_mismatch_rejects(self):
        self.report['snapshot']['sha256'] = 'b'*64
        with self.assertRaises(UCCError): self.invoke()

    def test_noncanonical_source_path_rejects(self):
        with self.assertRaises(UCCError):
            prepare_source_skeleton_preview(self.database.parent/'x'/'..'/self.database.name,
                'source#clip-0000', expected_source_sha256=self.source_sha, expected_policy=self.policy,
                local_preview_confirmed=True, blender_exe=self.root/'unused',worker_script=self.root/'unused',jobs_root=self.jobs)

    def test_snapshot_change_and_source_same_size_change_revoke_original_authority(self):
        loaded = self.invoke(); self.snapshot.write_bytes(self.payload+b' ')
        with self.assertRaises(UCCError): loaded.guard(timeout_s=5)
        self.snapshot.write_bytes(self.payload)
        self.source.write_bytes(b'X'*self.source.stat().st_size)
        with self.assertRaises(UCCError): loaded.guard(timeout_s=5)

    def test_committed_owned_wal_policy_revocation_rejects_guard(self):
        loaded = self.invoke()
        with AnimationCatalog(self.database) as writer:
            writer.db.execute('PRAGMA journal_mode=WAL'); writer.db.execute('PRAGMA wal_autocheckpoint=0')
            policy = self.policy.to_dict(); policy['local_preview_allowed'] = False
            writer.db.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?',
                (json.dumps(policy), 'source')); writer.db.commit()
            with self.assertRaises(UCCError): loaded.guard(timeout_s=5)

    def test_missing_sidecar_appearance_is_visible_to_cheap_identity(self):
        loaded = self.invoke(); path = Path(str(self.database)+'-journal')
        self.assertEqual(loaded.watched_identities[path], (0,0,0,0))
        path.write_bytes(b'owned namespace change')
        self.assertNotEqual(watch_identity(path), loaded.watched_identities[path])
        with self.assertRaises(UCCError): loaded.guard(timeout_s=5)

    def test_cancel_during_native_preparation_never_adopts(self):
        cancel = Event(); original = self.fresh
        def cancelled(*args, **kwargs):
            value = original(*args, **kwargs); cancel.set(); return value
        self.fresh = cancelled
        with self.assertRaises(UCCError): self.invoke(cancel=cancel)

    def test_policy_change_during_native_preparation_rejects_without_catalog_publish(self):
        original = self.fresh
        def revoked(*args, **kwargs):
            value = original(*args, **kwargs)
            with AnimationCatalog(self.database) as writer:
                p = self.policy.to_dict(); p['local_preview_allowed'] = False
                writer.db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(p),))
                writer.db.commit()
            return value
        self.fresh = revoked
        with self.assertRaises(UCCError): self.invoke()
        self.assertEqual(self.calls, 1)
        with AnimationCatalog(self.database, read_only=True) as c:
            self.assertEqual(c.get('source').clips[0].frame_count, 4)
            self.assertFalse(c.library.get('source').policy.local_preview_allowed)


if __name__ == '__main__': unittest.main()
