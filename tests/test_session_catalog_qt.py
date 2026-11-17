"""Real Qt session selection and existing catalog dispatch; no native work."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import ValidationError
from ucc.library.provenance import AssetPolicyError
try:
    from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication = None; QT_IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt unavailable')
class SessionCatalogQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None: raise RuntimeError(QT_IMPORT_ERROR)
        cls.app = QApplication.instance() or QApplication(['session-catalog-test'])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.first = self.root/'first.db'; self.second = self.root/'second.db'
        for path in (self.first, self.second):
            with AnimationCatalog(path): pass
        self.windows = []
        self.addCleanup(self.close_windows)

    def close_windows(self):
        for window in self.windows:
            window.close(); window.deleteLater()
        self.app.processEvents()

    def window(self, **kwargs):
        window = MainWindow(**kwargs); self.windows.append(window); return window

    def test_constructor_does_not_open_sql_and_two_windows_keep_separate_choices(self):
        with patch('sqlite3.connect', side_effect=AssertionError('Startup SQL forbidden')), \
                patch('ucc.desktop.window.QStandardPaths.writableLocation', side_effect=AssertionError('Default lookup forbidden')):
            first = self.window(catalog_path=self.first); second = self.window(catalog_path=self.second)
            self.assertEqual(first._catalog_path(), self.first)
            self.assertEqual(second._catalog_path(), self.second)

    def test_existing_refresh_opens_only_selected_catalog(self):
        window = self.window(catalog_path=self.first); opened = []; outcomes = []
        original = sqlite3.connect
        def connect(path, *args, **kwargs):
            self.assertEqual(str(path), self.first.as_uri()+'?mode=ro'); opened.append(self.first)
            return original(path, *args, **kwargs)
        with patch('sqlite3.connect', side_effect=connect), \
                patch.object(window, '_submit', side_effect=lambda kind, job: outcomes.append((kind, job()))), \
                patch('ucc.desktop.window.QStandardPaths.writableLocation', side_effect=AssertionError('Default lookup forbidden')):
            window.refresh_catalog()
        self.assertEqual(opened, [self.first]); self.assertEqual(outcomes, [('catalog', [])])

    def test_default_location_behavior_is_preserved(self):
        window = self.window()
        with patch('ucc.desktop.window.QStandardPaths.writableLocation', return_value=str(self.root)):
            self.assertEqual(window._catalog_path(), self.root/'animation_library.db')
        self.assertFalse((self.root/'animation_library.db').exists())

    def test_removed_or_hardlinked_selection_rejects_without_default_fallback(self):
        window = self.window(catalog_path=self.first)
        self.first.unlink()
        with patch('ucc.desktop.window.QStandardPaths.writableLocation', side_effect=AssertionError('Fallback forbidden')):
            with self.assertRaises(ValidationError): window._catalog_path()
            os.link(self.second, self.first)
            with self.assertRaises(ValidationError): window._catalog_path()

    def test_removed_selection_uses_normal_index_error_without_submitting_work(self):
        window = self.window(catalog_path=self.first); self.first.unlink()
        with patch.object(window, '_submit') as submit, patch.object(window, '_error') as error:
            window.index_animation(str(self.root/'unused.bvh'), 'original', 'Original', 'CC0', 'test://original')
        error.assert_called_once(); submit.assert_not_called()

    def test_unrelated_sqlite_refresh_and_index_reject_without_schema_or_byte_changes(self):
        unrelated = self.root/'unrelated.db'
        connection = sqlite3.connect(unrelated)
        try:
            connection.execute('CREATE TABLE unrelated (value TEXT)'); connection.commit()
        finally:
            connection.close()
        before = unrelated.read_bytes(); window = self.window(catalog_path=unrelated); queued = []
        with patch.object(window, '_submit', side_effect=lambda kind, job, **kw: queued.append(job)):
            window.refresh_catalog()
            window.index_animation(str(self.root/'unused.bvh'), 'original', 'Original', 'CC0', 'test://original')
        self.assertEqual(len(queued), 2)
        for job in queued:
            with self.assertRaises(AssetPolicyError): job()
            self.assertEqual(unrelated.read_bytes(), before)

    def test_explicit_metadata_and_measured_index_propagate_existing_schema_mode(self):
        from fixtures.project_reference_contract import ReferenceFixture
        folder = self.root/'reference'; folder.mkdir(); fixture = ReferenceFixture(folder)
        window = self.window(catalog_path=fixture.database); window.controller.open(fixture.store.root)
        window._blender_executable = fixture.executable
        with AnimationCatalog(fixture.database, read_only=True) as catalog:
            expected = catalog.get('fixture-source').to_dict()
        options = []; queued = []
        def catalog(path, **kwargs):
            self.assertEqual(path, fixture.database); options.append(kwargs)
            return AnimationCatalog(path, **kwargs)
        with patch('ucc.desktop.animation_catalog.AnimationCatalog', side_effect=catalog), \
                patch('ucc.desktop.animation_catalog.measure_catalog_fbx', return_value=expected) as measure, \
                patch.object(window, '_submit', side_effect=lambda kind, job, **kw: queued.append(job)):
            window.index_animation(str(fixture.source), 'unreviewed', fixture.policy.provider,
                                   fixture.policy.license_name, fixture.policy.source_uri)
            queued.pop()(); self.assertEqual(options, [{'require_existing': True}])
            options.clear(); window.animations.local_preview_review.setChecked(True)
            window.index_animation(str(fixture.source), 'fixture-source', fixture.policy.provider,
                                   fixture.policy.license_name, fixture.policy.source_uri)
            queued.pop()()
        self.assertEqual(options, [{'require_existing': True}, {'read_only': True}])
        self.assertIs(measure.call_args.kwargs['require_existing'], True)

    def test_removed_selection_uses_normal_source_preview_error_without_work(self):
        window = self.window(catalog_path=self.first)
        window.controller.create(self.root/'project', 'NONSHIPPING catalog selection boundary')
        executable = self.root/'not-a-real-executable.exe'; executable.write_bytes(b'NONSHIPPING_NOT_EXECUTABLE')
        window._blender_executable = executable
        table = window.animations.catalog; table.setRowCount(1)
        table.setItem(0, 0, QTableWidgetItem('source')); table.setCurrentCell(0, 0)
        self.first.unlink()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
                patch.object(window, '_submit') as submit, patch.object(window, '_error') as error:
            window.source_skeleton_action.trigger()
        error.assert_called_once(); submit.assert_not_called()


if __name__ == '__main__': unittest.main()
