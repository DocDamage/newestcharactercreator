"""Session catalog paths and launch forwarding; no source assets or native work."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ucc.core.errors import ValidationError
from ucc.desktop.catalog_location import existing_catalog_path
from ucc.desktop.__main__ import main


class SessionCatalogLocationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.database = self.root/'existing catalog.sqlite3'
        self.database.write_bytes(b'NONSHIPPING location-only fixture; not a database')

    def test_location_admission_never_opens_sql_or_reads_file_contents(self):
        with patch('sqlite3.connect', side_effect=AssertionError('SQL forbidden')), \
                patch.object(Path, 'open', side_effect=AssertionError('Content reads forbidden')):
            self.assertEqual(existing_catalog_path(self.database), self.database)

    def test_relative_missing_empty_directory_and_noncanonical_paths_reject(self):
        empty = self.root/'empty'; empty.touch()
        directory = self.root/'nested'; directory.mkdir()
        paths = [Path('relative.sqlite3'), self.root/'missing', empty, directory,
                 directory/'..'/self.database.name]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(ValidationError):
                existing_catalog_path(path)
        self.assertFalse((self.root/'missing').exists())

    def test_hardlinked_catalog_rejects_without_modifying_either_name(self):
        linked = self.root/'linked.sqlite3'; os.link(self.database, linked)
        before = self.database.read_bytes()
        for path in (self.database, linked):
            with self.assertRaises(ValidationError): existing_catalog_path(path)
        self.assertEqual(linked.read_bytes(), before)

    def test_redirected_parent_rejects_on_actual_filesystem(self):
        parent = self.root/'redirected'
        if os.name == 'nt':
            quote = lambda p: "'"+str(p).replace("'", "''")+"'"
            command = 'New-Item -ItemType Junction -Path '+quote(parent)+' -Target '+quote(self.root)+' -ErrorAction Stop | Out-Null'
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                           capture_output=True, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
            self.addCleanup(os.rmdir, parent)
        else:
            parent.symlink_to(self.root, target_is_directory=True)
            self.addCleanup(parent.unlink)
        with self.assertRaises(ValidationError): existing_catalog_path(parent/self.database.name)

    @unittest.skipUnless(os.name == 'nt', 'Windows namespace rules')
    def test_windows_remote_and_device_names_reject_before_filesystem_lookup(self):
        with patch.object(Path, 'stat', side_effect=AssertionError('Remote filesystem access forbidden')):
            for value in ('\\\\server\\share\\library.db', '\\\\?\\C:\\library.db', '\\\\.\\C:\\library.db'):
                with self.subTest(path=value), self.assertRaises(ValidationError): existing_catalog_path(Path(value))

    @unittest.skipUnless(os.name == 'nt', 'Windows alternate data streams')
    def test_actual_ntfs_alternate_stream_rejects_before_filesystem_lookup(self):
        stream = Path(str(self.database)+':catalog'); stream.write_bytes(b'NONSHIPPING alternate stream')
        self.assertTrue(stream.is_file())
        with patch.object(Path, 'stat', side_effect=AssertionError('Stream lookup forbidden')), self.assertRaises(ValidationError):
            existing_catalog_path(stream)


class SessionCatalogCliTests(unittest.TestCase):
    def test_standalone_entrypoint_forwards_catalog_without_a_package_context(self):
        from ucc.animations.catalog import AnimationCatalog
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory).resolve()/'existing catalog.db'
            with AnimationCatalog(selected): pass
            entrypoint = Path(__file__).resolve().parents[1]/'src/ucc/desktop/__main__.py'
            app = Mock(); app.exec.return_value = 17
            application = Mock(); application.instance.return_value = app
            window = Mock()
            modules = {'PySide6.QtWidgets': SimpleNamespace(QApplication=application),
                       'ucc.desktop.window': SimpleNamespace(MainWindow=window)}
            with patch.dict(sys.modules, modules), \
                    patch.object(sys, 'argv', [str(entrypoint), '--catalog', str(selected)]), \
                    patch('sqlite3.connect', side_effect=AssertionError('Startup SQL forbidden')), \
                    self.assertRaises(SystemExit) as result:
                runpy.run_path(str(entrypoint), run_name='__main__')
            self.assertEqual(result.exception.code, 17)
            window.assert_called_once_with(catalog_path=selected)
            window.return_value.show.assert_called_once_with()
            app.exec.assert_called_once_with()

    def test_invalid_options_exit_before_launch_or_self_test(self):
        with patch('ucc.desktop.__main__._self_test', side_effect=AssertionError('Self-test must not run')), \
                patch('ucc.desktop.catalog_location.existing_catalog_path', side_effect=AssertionError('Path must not be inspected')), \
                contextlib.redirect_stderr(io.StringIO()):
            for args in (['--catalog'], ['--catalog', 'ignored', '--self-test'],
                         ['--catalog', 'ignored', '--self-test-report', 'ignored']):
                with self.subTest(args=args), self.assertRaises(SystemExit) as failure: main(args)
                self.assertEqual(failure.exception.code, 2)

    def test_missing_catalog_fails_without_creating_default_or_selected_file(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory).resolve()/'missing.db'
            with patch('sqlite3.connect', side_effect=AssertionError('SQL forbidden')), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                main(['--catalog', str(missing)])
            self.assertEqual(failure.exception.code, 2); self.assertFalse(missing.exists())

    def test_selected_path_reaches_window_and_default_launch_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory).resolve()/'catalog with spaces.db'; selected.write_bytes(b'location fixture')
            app = Mock(); app.exec.return_value = 17
            application = Mock(); application.instance.return_value = app
            window = Mock()
            modules = {'PySide6.QtWidgets': SimpleNamespace(QApplication=application),
                       'ucc.desktop.window': SimpleNamespace(MainWindow=window)}
            with patch.dict(sys.modules, modules):
                self.assertEqual(main(['--catalog', str(selected)]), 17)
                window.assert_called_once_with(catalog_path=selected)
                window.reset_mock()
                self.assertEqual(main([]), 17); window.assert_called_once_with()

    def test_location_disappearance_during_window_construction_is_a_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory).resolve()/'catalog.db'; selected.write_bytes(b'location fixture')
            application = Mock(); application.instance.return_value = Mock()
            window = Mock(side_effect=ValidationError('Catalog disappeared'))
            modules = {'PySide6.QtWidgets': SimpleNamespace(QApplication=application),
                       'ucc.desktop.window': SimpleNamespace(MainWindow=window)}
            with patch.dict(sys.modules, modules), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as failure:
                main(['--catalog', str(selected)])
            self.assertEqual(failure.exception.code, 2)


if __name__ == '__main__': unittest.main()
