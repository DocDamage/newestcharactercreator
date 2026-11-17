"""No asset fixtures: reject unsupported derivatives before IO or native jobs."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ucc.core.errors import ValidationError
from ucc.jobs.contact_fit_context import contact_context
from ucc.jobs.fitted_playback import prepare_fitted_comparison, prepare_fitted_playback
from ucc.jobs.native_fit import fit_native_preview
from ucc.jobs.native_registered_limits import require_manual_native_source


class NativeRegisteredLimitsTests(unittest.TestCase):
    def setUp(self):
        self.registered = SimpleNamespace(source_authority=object())
        self.manual = SimpleNamespace(source_authority=None)
        self.store = Mock()
        self.store.load.side_effect = AssertionError('No project read is authorized')
        self.options = dict(source_fbx=Path('unused.fbx'), permission=None,
                            blender_exe=Path('unused'), worker_script=Path('unused'))

    def test_manual_and_legacy_results_do_not_gain_restrictions(self):
        require_manual_native_source(None, self.manual, SimpleNamespace())

    def test_fit_rejects_registered_preview_before_io(self):
        with self.assertRaisesRegex(ValidationError, 'Registered-source'):
            fit_native_preview(self.store, self.registered, fit_policy=Path('unused'), **self.options)
        self.store.load.assert_not_called()

    def test_fit_rejects_registered_base_before_io(self):
        base = SimpleNamespace(original_preview=self.registered)
        with self.assertRaisesRegex(ValidationError, 'Registered-source'):
            fit_native_preview(self.store, self.manual, fit_policy=Path('unused'), base_preview=base,
                               **self.options)
        self.store.load.assert_not_called()

    def test_contact_context_rejects_either_registered_input(self):
        for preview, playback in ((self.registered, self.manual), (self.manual, self.registered)):
            with self.subTest(preview=preview), self.assertRaisesRegex(ValidationError, 'Registered-source'):
                contact_context(self.store, preview, playback, source_fbx=Path('unused.fbx'))
        self.store.load.assert_not_called()

    def test_fitted_cache_and_comparison_reject_before_any_preparation(self):
        fitted = SimpleNamespace(original_preview=self.registered)
        with patch('ucc.jobs.fitted_playback.prepare_native_playback') as prepare:
            for operation in (prepare_fitted_playback, prepare_fitted_comparison):
                with self.subTest(operation=operation), self.assertRaisesRegex(ValidationError, 'Registered-source'):
                    operation(self.store, fitted, **self.options)
            prepare.assert_not_called()
        self.store.load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
