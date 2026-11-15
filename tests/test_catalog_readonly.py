"""Real SQLite read-only/WAL behavior with non-shipping source metadata fixtures."""
from dataclasses import replace
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fixtures.project_reference_contract import ReferenceFixture
from ucc.animations.catalog import AnimationCatalog
from ucc.jobs.catalog_clip import _saved_reference
from ucc.jobs.animation_reference_storage import publish_source_binding, check_registered_source
from ucc.library.provenance import AssetLibrary, AssetPolicyError


class ReadOnlyCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.f = ReferenceFixture(self.root)
        publish_source_binding(self.f.store, self.f.project.project_id, self.f.reference)
        with closing(sqlite3.connect(self.f.database)) as db: db.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def snapshot(self):
        p = self.f.database; info = p.stat()
        return sha256(p.read_bytes()).hexdigest(), info.st_size, info.st_mtime_ns, info.st_ino

    def lookup(self):
        return _saved_reference(self.f.database, self.f.clip_id, self.f.source_sha, self.f.policy)

    def test_repeated_lookup_preserves_main_database_bytes_and_timestamp(self):
        before = self.snapshot()
        for _ in range(3):
            entry, indexed, receipt, _ = self.lookup()
            self.assertEqual(entry.sha256, self.f.source_sha)
            self.assertEqual(indexed.clips[0].ordinal, 0)
            check_registered_source(self.f.store, self.f.database, self.f.project.project_id, self.f.clip_id)
        self.assertEqual(self.snapshot(), before)

    def test_read_only_sql_and_registration_cannot_write(self):
        before = self.snapshot()
        with AssetLibrary(self.f.database, read_only=True) as library:
            self.assertEqual(library.get(self.f.reference.asset_id).policy, self.f.policy)
            with self.assertRaises(sqlite3.OperationalError):
                library.db.execute('UPDATE asset_sources SET indexed_utc=?', ('changed',))
            with self.assertRaises(AssetPolicyError):
                library.register('new', self.f.source, self.f.policy)
        with AnimationCatalog(self.f.database, read_only=True) as catalog:
            with self.assertRaises(sqlite3.OperationalError):
                catalog.db.execute('CREATE TABLE unwanted (id INTEGER)')
        self.assertEqual(self.snapshot(), before)

    def test_missing_database_does_not_create_directory_or_file(self):
        path = self.root/'does-not-exist'/'catalog.sqlite3'
        for constructor in (AssetLibrary, AnimationCatalog):
            with self.assertRaises(AssetPolicyError): constructor(path, read_only=True)
            self.assertFalse(path.parent.exists())

    def test_empty_future_and_malformed_databases_are_never_migrated(self):
        paths = []
        for version in (0, 2):
            path = self.root/('version-'+str(version)+'.sqlite3')
            with closing(sqlite3.connect(path)) as db: db.execute('PRAGMA user_version='+str(version))
            paths.append(path)
        invalid = self.root/'malformed.sqlite3'; invalid.write_bytes(b'NOT_A_DATABASE'); paths.append(invalid)
        for path in paths:
            before = path.read_bytes()
            with self.assertRaises(AssetPolicyError): AnimationCatalog(path, read_only=True)
            self.assertEqual(path.read_bytes(), before)
            # Failed constructors released their connection and file handles.
            moved = path.with_suffix('.verified'); path.rename(moved); moved.rename(path)

    def test_incomplete_or_extended_schema_is_not_silently_repaired(self):
        asset_only = self.root/'asset-only.sqlite3'
        with AssetLibrary(asset_only): pass
        before = asset_only.read_bytes()
        with self.assertRaises(AssetPolicyError): AnimationCatalog(asset_only, read_only=True)
        self.assertEqual(asset_only.read_bytes(), before)
        with closing(sqlite3.connect(self.f.database)) as db:
            db.execute('ALTER TABLE animation_clips ADD COLUMN unexpected TEXT')
        before = self.snapshot()
        with self.assertRaises(AssetPolicyError): self.lookup()
        self.assertEqual(self.snapshot(), before)

    def test_default_writer_still_initializes_indexes_and_preserves_policy(self):
        path = self.root/'writer-new'/'catalog.sqlite3'
        with AnimationCatalog(path) as catalog:
            catalog.library.register('owned', self.f.source, self.f.policy)
            self.assertEqual(catalog.library.get('owned').policy, self.f.policy)
            self.assertEqual(catalog.db.execute('PRAGMA user_version').fetchone()[0], 1)
        with AnimationCatalog(path, read_only=True) as catalog:
            self.assertEqual(catalog.library.get('owned').policy, self.f.policy)

    def test_committed_policy_write_in_live_WAL_is_visible_and_NoAI_change_rejects(self):
        # Keep the writer open so committed data stays in WAL rather than relying
        # on a later checkpoint into the main file. immutable=1 would miss this.
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL'); writer.execute('PRAGMA wal_autocheckpoint=0')
        self.lookup(); original = self.snapshot()
        altered = replace(self.f.policy, no_ai=False)
        writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?',
            (json.dumps(altered.to_dict(), sort_keys=True), self.f.reference.asset_id))
        writer.commit()
        self.assertTrue(Path(str(self.f.database)+'-wal').is_file())
        self.assertEqual(self.snapshot(), original)
        with AssetLibrary(self.f.database, read_only=True) as reader:
            self.assertFalse(reader.get(self.f.reference.asset_id).policy.no_ai)
        with self.assertRaises(AssetPolicyError): self.lookup()
        with self.assertRaises(AssetPolicyError):
            check_registered_source(self.f.store, self.f.database, self.f.project.project_id, self.f.clip_id)

    def test_existing_reader_observes_later_commits_without_immutable_or_stale_transaction(self):
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA wal_autocheckpoint=0')
        with AssetLibrary(self.f.database, read_only=True) as reader:
            self.assertTrue(reader.get(self.f.reference.asset_id).policy.no_ai)
            altered = replace(self.f.policy, no_ai=False)
            writer.execute('UPDATE asset_sources SET license_json=? WHERE asset_id=?',
                (json.dumps(altered.to_dict()), self.f.reference.asset_id)); writer.commit()
            self.assertFalse(reader.get(self.f.reference.asset_id).policy.no_ai)

    def test_read_only_flag_requires_an_explicit_boolean(self):
        for value in (1, 'yes', None):
            with self.assertRaises(AssetPolicyError): AssetLibrary(self.f.database, read_only=value)


if __name__ == '__main__': unittest.main()
