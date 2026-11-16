"""Bounded filesystem traversal; synthetic private-temp markers, no engine claim."""
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch
from ucc.core.errors import ProjectStorageError
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.master_preview import _digest
from ucc.jobs.unity_export import _source_snapshot
from ucc.jobs.unity_export_payload import snapshot


class UnityExportTraversalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = SimpleNamespace(root=self.root)
        (self.root/'master').mkdir()

    def test_already_cancelled_source_does_not_open_any_directory(self):
        cancel = Event(); cancel.set()
        with patch('ucc.jobs.unity_export_payload.os.scandir') as scan:
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled'):
                _source_snapshot(self.store, cancel)
        scan.assert_not_called()

    def test_already_cancelled_payload_does_not_open_any_directory(self):
        cancel = Event(); cancel.set()
        with patch('ucc.jobs.unity_export_payload.os.scandir') as scan:
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled'):
                snapshot(self.root, cancel)
        scan.assert_not_called()

    @staticmethod
    def endless_entries(counter):
        class Entries:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __next__(self):
                counter[0] += 1
                if counter[0] > 8192:
                    raise AssertionError('Unbounded enumeration reached the sentinel')
                return SimpleNamespace(name='UNIT_MISSING_ENTRY_'+str(counter[0]))
        return Entries()

    def test_source_limit_stops_consuming_before_8192_child_entries(self):
        counter = [0]
        with patch('ucc.jobs.unity_export_payload.os.scandir', return_value=self.endless_entries(counter)):
            with self.assertRaisesRegex(ProjectStorageError, 'entry limit'):
                _source_snapshot(self.store, Event())
        self.assertEqual(counter[0], 8191)

    def test_payload_total_entry_limit_stops_before_unbounded_enumeration(self):
        counter = [0]
        with patch('ucc.jobs.unity_export_payload.os.scandir', return_value=self.endless_entries(counter)):
            with self.assertRaisesRegex(ProjectStorageError, 'entry limit'):
                snapshot(self.root)
        self.assertEqual(counter[0], 1023)

    def test_payload_file_limit_rejects_before_hashing_the_513th_file(self):
        payload = self.root/'UNIT_PAYLOAD'; payload.mkdir()
        for index in range(513):
            (payload/('UNIT_FILE_'+str(index))).write_bytes(b'UNIT_NOT_ENGINE_DATA')
        with patch('ucc.jobs.unity_export_payload._digest', wraps=_digest) as digest:
            with self.assertRaisesRegex(ProjectStorageError, 'file inventory'):
                snapshot(payload)
        self.assertEqual(digest.call_count, 512)

    def test_cancellation_triggered_by_entry_is_checked_before_hash_or_descent(self):
        cancel = Event(); marker = self.root/'master/UNIT_SOURCE'
        marker.write_bytes(b'UNIT_NOT_REAL_MASTER')
        class Entries:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __next__(self):
                cancel.set()
                return SimpleNamespace(name=marker.name)
        with patch('ucc.jobs.unity_export_payload.os.scandir', return_value=Entries()), \
                patch('ucc.jobs.unity_export._digest') as digest:
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled'):
                _source_snapshot(self.store, cancel)
        digest.assert_not_called()

    def test_unknown_payload_directory_is_rejected_before_child_open(self):
        library = self.root/'Library'; library.mkdir()
        actual = os.scandir; opened = []
        def scan(path):
            opened.append(Path(path)); return actual(path)
        with patch('ucc.jobs.unity_export_payload.os.scandir', side_effect=scan):
            with self.assertRaisesRegex(ProjectStorageError, 'unlisted directory'):
                snapshot(self.root)
        self.assertNotIn(library, opened)

    def test_genuine_redirected_source_directory_is_not_descended(self):
        target = self.root/'UNIT_TARGET'; target.mkdir()
        (target/'UNIT_NOT_AUTHORIZED').write_bytes(b'UNIT_TARGET_UNCHANGED')
        link = self.root/'master/UNIT_REDIRECT'
        self.assertTrue(link.is_relative_to(self.root) and target.is_relative_to(self.root))
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)
        actual = os.scandir; opened = []
        def scan(path):
            opened.append(Path(path)); return actual(path)
        try:
            with patch('ucc.jobs.unity_export_payload.os.scandir', side_effect=scan):
                with self.assertRaisesRegex(ProjectStorageError, 'redirected'):
                    _source_snapshot(self.store, Event())
            self.assertNotIn(link, opened); self.assertNotIn(target, opened)
            self.assertEqual((target/'UNIT_NOT_AUTHORIZED').read_bytes(), b'UNIT_TARGET_UNCHANGED')
        finally:
            if os.name == 'nt': os.rmdir(link)
            else: link.unlink()

    def test_ordinary_source_seal_retains_the_previous_complete_inventory(self):
        for name in ('master/versions/UNIT.blend', 'expressions/proofs/UNIT.json', 'history/UNIT.json'):
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'UNIT_NONSHIPPING_SOURCE_MARKER')
        (self.root/'parts').mkdir()
        expected = {}
        # Deliberately tiny known fixture: legacy traversal is comparison only.
        for name in ('master', 'expressions', 'parts', 'materials', 'history'):
            root = self.root/name
            for path in [root, *root.rglob('*')] if root.exists() else [root]:
                value = None if not path.exists() else (identity(path), _digest(path)) if path.is_file() else identity(path)
                expected[path.relative_to(self.root).as_posix()] = value
        self.assertEqual(_source_snapshot(self.store, Event()), expected)


if __name__ == '__main__':
    unittest.main()
