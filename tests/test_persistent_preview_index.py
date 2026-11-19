"""Filesystem and authentication coverage for the private preview index."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs import persistent_preview_index as index


_KEY = 'a' * 64
_OTHER = 'b' * 64


class PersistentPreviewIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.root = self.parent / 'app' / 'preview-index'
        self.entry = self.root / (_KEY + '.json')
        self.secret = self.root / 'signing.key'

    def test_missing_read_leaves_no_directories_and_restart_round_trips(self):
        self.assertIsNone(index.read_index(self.root, _KEY))
        self.assertFalse(self.root.parent.exists())
        value = {'pinned': 'animation', 'clock': [150, 30], 'verified': True}
        index.write_index(self.root, _KEY, value)
        self.assertEqual(len(self.secret.read_bytes()), 32)
        self.assertEqual(index.read_index(Path(str(self.root)), _KEY), value)
        self.assertIsNone(index.read_index(self.root, _OTHER))

    def test_payload_edit_and_copied_record_under_other_key_are_misses(self):
        index.write_index(self.root, _KEY, {'verified': True})
        (self.root / (_OTHER + '.json')).write_bytes(self.entry.read_bytes())
        self.assertIsNone(index.read_index(self.root, _OTHER))
        record = json.loads(self.entry.read_bytes())
        record['payload']['verified'] = False
        self.entry.write_bytes(json.dumps(record, sort_keys=True, separators=(',', ':')).encode())
        self.assertIsNone(index.read_index(self.root, _KEY))
        index.write_index(self.root, _KEY, {'verified': 'fresh'})
        self.assertEqual(index.read_index(self.root, _KEY), {'verified': 'fresh'})

    def test_noncanonical_duplicate_and_overweight_records_are_misses(self):
        index.write_index(self.root, _KEY, {'value': 1})
        good = self.entry.read_bytes()
        for bad in (good + b'\n', good.replace(b'"value":1', b'"value":1,"value":1'), b'X' * (2 * 1024**2 + 257)):
            with self.subTest(size=len(bad)):
                self.entry.write_bytes(bad)
                self.assertIsNone(index.read_index(self.root, _KEY))
        self.entry.write_bytes(good)
        self.assertEqual(index.read_index(self.root, _KEY), {'value': 1})

    def test_bad_inputs_do_not_touch_disk_and_full_size_payload_round_trips(self):
        for key in ('../some-file', 'A' * 64, '0' * 65):
            with self.subTest(key=key):
                with self.assertRaises(ValidationError):
                    index.write_index(self.root, key, {})
        for value in ({'bad': float('nan')}, {'bad': {1: 2}}, {'bad': 'X' * 2**21}):
            with self.subTest(value_size=len(str(value))):
                with self.assertRaises(ValidationError):
                    index.write_index(self.root, _KEY, value)
        self.assertFalse(self.root.parent.exists())
        payload = {'value': 'X' * (2**21 - len(b'{"value":""}'))}
        index.write_index(self.root, _KEY, payload)
        self.assertEqual(index.read_index(self.root, _KEY), payload)

    def test_short_existing_secret_never_replaced(self):
        index.write_index(self.root, _KEY, {'a': 1})
        self.secret.write_bytes(b'short')
        self.assertIsNone(index.read_index(self.root, _KEY))
        with self.assertRaises(ProjectStorageError):
            index.write_index(self.root, _KEY, {'a': 2})
        self.assertEqual(self.secret.read_bytes(), b'short')

    def test_replaced_secret_cannot_verify_previous_index(self):
        index.write_index(self.root, _KEY, {'a': 1})
        self.secret.write_bytes(bytes(value ^ 0xff for value in self.secret.read_bytes()))
        self.assertIsNone(index.read_index(self.root, _KEY))

    def test_hardlinks_never_opened_for_replacement(self):
        index.write_index(self.root, _KEY, {'a': 1})
        original = self.entry.read_bytes()
        alias = self.parent / 'entry-alias'
        try:
            os.link(self.entry, alias)
        except OSError as error:
            self.skipTest(f'File links unavailable: {error}')
        self.assertIsNone(index.read_index(self.root, _KEY))
        with self.assertRaises(ProjectStorageError):
            index.write_index(self.root, _KEY, {'a': 2})
        self.assertEqual(alias.read_bytes(), original)
        alias.unlink()
        os.link(self.secret, alias)
        self.assertIsNone(index.read_index(self.root, _KEY))
        with self.assertRaises(ProjectStorageError):
            index.write_index(self.root, _KEY, {'a': 2})
        self.assertEqual(self.entry.read_bytes(), original)

    def test_redirected_parent_is_rejected_without_writing_to_its_target(self):
        outside = self.parent / 'outside'
        outside.mkdir()
        try:
            self.root.parent.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name != 'nt':
                self.skipTest(f'Directory links unavailable: {error}')
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(self.root.parent), str(outside)],
                                    capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(index.read_index(self.root, _KEY))
        with self.assertRaises(ProjectStorageError):
            index.write_index(self.root, _KEY, {'a': 1})
        self.assertEqual(list(outside.iterdir()), [])

    def test_fsync_failure_preserves_previous_record_and_removes_owned_temporary(self):
        index.write_index(self.root, _KEY, {'a': 1})
        previous = self.entry.read_bytes()
        with patch.object(index.os, 'fsync', side_effect=OSError('injected flush failure')):
            with self.assertRaisesRegex(OSError, 'flush failure'):
                index.write_index(self.root, _KEY, {'a': 2})
        self.assertEqual(self.entry.read_bytes(), previous)
        self.assertEqual(set(self.root.iterdir()), {self.entry, self.secret})

    def test_simultaneous_first_writers_share_a_complete_secret_and_entry(self):
        count = 8
        release = Barrier(count)

        def write(value):
            release.wait(timeout=5)
            index.write_index(self.root, _KEY, {'value': value})
            index.write_index(self.root, f'{value:064x}', {'value': value})

        with ThreadPoolExecutor(max_workers=count) as pool:
            self.assertEqual(len(list(pool.map(write, range(count)))), count)
        self.assertIn(index.read_index(self.root, _KEY)['value'], range(count))
        for value in range(count):
            self.assertEqual(index.read_index(self.root, f'{value:064x}'), {'value': value})
        self.assertEqual(len(list(self.root.iterdir())), count + 2)
