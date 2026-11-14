"""CI corruption must reach the physical comparison within worker size bounds."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.complete_surface_forgery import _write_bounded_forgery


class CompleteSurfaceForgeryEncodingTests(unittest.TestCase):
    def test_paired_style_repeated_indices_fit_only_with_compact_encoding(self):
        data={'original':{'frames':[list(range(100))]},'fitted':{'frames':[list(range(100))]}}
        compact=json.dumps(data,separators=(',',':')).encode('utf-8')
        self.assertGreater(len(json.dumps(data).encode('utf-8')),len(compact))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'forged.json'
            with patch('ci.complete_surface_forgery.MAX_REPORT_BYTES',len(compact)):
                _write_bounded_forgery(path,data)
            self.assertEqual(path.read_bytes(),compact)
            self.assertEqual(json.loads(path.read_bytes()),data)

    def test_oversized_fixture_leaves_no_partial_report(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'forged.json'
            with patch('ci.complete_surface_forgery.MAX_REPORT_BYTES',8):
                with self.assertRaisesRegex(RuntimeError,'worker input bound'):
                    _write_bounded_forgery(path,{'frames':list(range(20))})
            self.assertFalse(path.exists())

    def test_existing_report_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'forged.json';path.write_bytes(b'original')
            with self.assertRaises(FileExistsError):_write_bounded_forgery(path,{'frames':[]})
            self.assertEqual(path.read_bytes(),b'original')
