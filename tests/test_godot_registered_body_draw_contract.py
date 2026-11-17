"""Private draw admission faults; no synthetic result is native evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from ucc.core.errors import ValidationError, ProjectStorageError
from ucc.export.godot_registered_body_draw import RegisteredBodyDrawSelection
from ucc.export.godot_registered_body_runtime import FALSE_FLAGS
from ucc.jobs.godot_registered_body_draw_inputs import _source_reference, admit_draw_inputs
from ucc.jobs.target_action_context import Budget
import struct


class DrawSelectionTests(unittest.TestCase):
    def selection(self):
        return RegisteredBodyDrawSelection(str(uuid4()), 'a'*64, 'b'*64, 'c'*64,
                                          'Private debug draw, no appearance approval', True)

    def test_per_use_confirmation_cannot_be_truthy_non_boolean(self):
        for value in (False, 1, 'yes', None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                replace(self.selection(), private_local_draw_confirmed=value)

    def test_readiness_never_follows_from_draw_selection(self):
        value = self.selection()
        self.assertTrue(all(value.to_dict()[name] is False for name in FALSE_FLAGS))
        self.assertNotEqual(value.sha256, replace(value, purpose='A different private use').sha256)

    def test_untyped_locators_reject_before_any_current_loader(self):
        with patch('ucc.jobs.godot_registered_body_draw_inputs.admit_body_inputs') as loader:
            with self.assertRaises(ValidationError):
                admit_draw_inputs(None, selection=None, retention_id='', expected_manifest_sha256='',
                    database_path=Path('unused'), permissions=(), preparation=None,
                    expected_production_receipt_sha256='', execution=None,
                    diagnostic=None, draw=self.selection(), godot_exe=Path('unused'),
                    godot_main_exe=Path('unused'), budget=Budget(None, 10))
            loader.assert_not_called()


class SourceReferenceFaultTests(unittest.TestCase):
    def test_coherent_rehash_of_wrong_reference_cannot_substitute_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); source = root/'source.bin'; target = root/'converted.bin'
            source.write_bytes(struct.pack('<3f', 1, 2, 3))
            target.write_bytes(struct.pack('<4f', 1, 2, 4, 1))
            with patch('ucc.jobs.godot_registered_body_draw_inputs.FRAMES', 1), \
                 patch('ucc.jobs.godot_registered_body_draw_inputs.VERTICES', 1):
                with self.assertRaisesRegex(ValidationError, 'actual producer'):
                    _source_reference(source, target, False, Budget(None, 10), frames=1,vertices=1,
                        source_sha256=sha256(source.read_bytes()).hexdigest(),
                        converted_sha256=sha256(target.read_bytes()).hexdigest())

    def test_original_reference_expansion_and_trailing_data(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); source = root/'source.bin'; target = root/'converted.bin'
            source.write_bytes(struct.pack('<3f', 0, 0, 1))
            target.write_bytes(struct.pack('<4f', 0, 0, 1, 0))
            with patch('ucc.jobs.godot_registered_body_draw_inputs.FRAMES', 1), \
                 patch('ucc.jobs.godot_registered_body_draw_inputs.VERTICES', 1):
                _source_reference(source, target, True, Budget(None, 10), frames=1,vertices=1,
                        source_sha256=sha256(source.read_bytes()).hexdigest(),
                        converted_sha256=sha256(target.read_bytes()).hexdigest())
                target.write_bytes(target.read_bytes()+b'x')
                with self.assertRaisesRegex(ProjectStorageError, 'length'):
                    _source_reference(source, target, True, Budget(None, 10), frames=1,vertices=1,
                        source_sha256=sha256(source.read_bytes()).hexdigest(),
                        converted_sha256=sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
