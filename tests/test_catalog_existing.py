"""Explicit existing-UCC writer admission on one connection; no schema repair."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ucc.animations.catalog import AnimationCatalog
from ucc.library.provenance import AssetLibrary, AssetPolicyError, LicensePolicy


class ExistingCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_unrelated_empty_future_and_malformed_files_never_gain_schema(self):
        paths = []
        for version in (0, 1, 2):
            path = self.root/f'unrelated-{version}.db'
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE TABLE unrelated (value TEXT)')
                connection.execute('PRAGMA user_version='+str(version)); connection.commit()
            paths.append(path)
        empty = self.root/'empty.db'; empty.touch(); paths.append(empty)
        invalid = self.root/'invalid.db'; invalid.write_bytes(b'NONSHIPPING_NOT_SQLITE'); paths.append(invalid)
        for path in paths:
            before = path.read_bytes()
            for constructor in (AssetLibrary, AnimationCatalog):
                with self.subTest(path=path, constructor=constructor), self.assertRaises(AssetPolicyError):
                    constructor(path, require_existing=True)
                self.assertEqual(path.read_bytes(), before)
            # Failed admission must release the connection and its handles.
            moved = path.with_suffix('.moved'); path.rename(moved); moved.rename(path)

    def test_missing_catalog_does_not_create_parent_or_file(self):
        missing = self.root/'missing'/'catalog.db'
        for constructor in (AssetLibrary, AnimationCatalog):
            with self.assertRaises(AssetPolicyError): constructor(missing, require_existing=True)
            self.assertFalse(missing.parent.exists())

    def test_asset_only_or_extended_animation_schema_is_never_repaired(self):
        asset_only = self.root/'asset-only.db'
        with AssetLibrary(asset_only): pass
        before = asset_only.read_bytes()
        with self.assertRaises(AssetPolicyError): AnimationCatalog(asset_only, require_existing=True)
        self.assertEqual(asset_only.read_bytes(), before)
        extended = self.root/'extended.db'
        with AnimationCatalog(extended) as catalog:
            catalog.db.execute('ALTER TABLE animation_clips ADD COLUMN unexpected TEXT'); catalog.db.commit()
        before = extended.read_bytes()
        with self.assertRaises(AssetPolicyError): AnimationCatalog(extended, require_existing=True)
        self.assertEqual(extended.read_bytes(), before)

    def test_valid_existing_catalog_can_write_without_ddl_and_enforces_foreign_keys(self):
        path = self.root/'valid.db'
        with AnimationCatalog(path): pass
        source = self.root/'original'; source.write_bytes(b'NONSHIPPING source boundary')
        statements = []; connect = sqlite3.connect
        class TracedConnection(sqlite3.Connection):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs); self.set_trace_callback(statements.append)
        with patch('sqlite3.connect', side_effect=lambda *args, **kwargs: connect(*args, **kwargs, factory=TracedConnection)), \
                AnimationCatalog(path, require_existing=True) as catalog:
            catalog.library.register('original', source, LicensePolicy('Original', 'CC0', 'test://original'))
            self.assertIsNotNone(catalog.library.get('original'))
            self.assertEqual(catalog.db.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                catalog.db.execute("INSERT INTO animation_sources VALUES ('missing','fbx','METADATA_EXTRACTED',NULL,'[]','[]')")
            self.assertFalse(any(value.lstrip().upper().startswith(('CREATE ', 'ALTER ', 'DROP ')) for value in statements))

    def test_require_existing_needs_boolean_and_read_only_stays_read_only(self):
        path = self.root/'valid.db'
        with AnimationCatalog(path): pass
        for value in (1, None, 'yes'):
            with self.assertRaises(AssetPolicyError): AnimationCatalog(path, require_existing=value)
        with AnimationCatalog(path, require_existing=True, read_only=True) as catalog:
            with self.assertRaises(sqlite3.OperationalError): catalog.db.execute('CREATE TABLE forbidden (value TEXT)')


if __name__ == '__main__': unittest.main()
