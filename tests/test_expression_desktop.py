"""Desktop metadata and dispatch contracts; no fabricated geometry acceptance."""
import os
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from test_expression_contracts import source_project, prepared
from ucc.core.errors import ValidationError
from ucc.core.storage import ProjectStore
from ucc.desktop.controller import DesktopController


class ExpressionControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        guard = patch.object(ProjectStore, '_check_master')  # Metadata contracts only; no mesh fixture.
        guard.start(); self.addCleanup(guard.stop)
        self.store = ProjectStore(Path(self.tmp.name)/'metadata-only')
        self.store.save(replace(prepared(source_project(hand=True), hand=True), revision=0))
        self.controller = DesktopController(); self.controller.open(self.store.root)

    def test_strengths_save_reopen_reset_history_preserve_master_and_hand(self):
        original = self.controller.require_project()
        self.controller.set_expression_parameter('mouth_open', .375)
        self.assertTrue(self.controller.dirty)
        self.controller.save()
        self.controller.open(self.store.root)
        self.assertEqual(dict(self.controller.view().expression_parameters)['mouth_open'], .375)
        self.controller.reset_expression(); self.assertTrue(self.controller.require_project().expression.neutral)
        self.controller.undo()
        self.assertEqual(dict(self.controller.view().expression_parameters)['mouth_open'], .375)
        self.controller.redo(); self.controller.save()
        self.assertEqual(self.store.load().parts, original.parts)
        self.assertEqual(self.store.load().master_blend, original.master_blend)

    def test_noop_strength_does_not_dirty_and_invalid_value_is_rejected(self):
        self.controller.set_expression_parameter('mouth_open', 0.)
        self.assertFalse(self.controller.dirty)
        with self.assertRaises(ValidationError): self.controller.set_expression_parameter('mouth_open', .501)
        self.assertFalse(self.controller.dirty)

    def test_preparation_adoption_is_one_complete_history_step(self):
        self.store = ProjectStore(Path(self.tmp.name)/'adoption-only')
        old = self.store.save(source_project(hand=True))
        self.controller.open(self.store.root)
        new = self.store.save(prepared(old, hand=True), expected_revision=old.revision)
        self.controller.accept_saved_expression_master(new, library_sha256=new.expression.library_sha256)
        self.assertFalse(self.controller.dirty)
        self.controller.undo()
        self.assertEqual(self.controller.require_project().parts, old.parts)
        self.assertIsNone(self.controller.require_project().expression)
        self.controller.redo()
        self.assertEqual(self.controller.require_project().parts, new.parts)
        self.assertEqual(self.controller.require_project().expression, new.expression)


try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.window import MainWindow
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional Qt not installed')
class ExpressionQtTests(ExpressionControllerTests):
    @classmethod
    def setUpClass(cls):
        if QApplication is None: raise RuntimeError('Required Qt is unavailable')
        cls.app = QApplication.instance() or QApplication(['expression-contract-tests'])

    def setUp(self):
        super().setUp()
        self.window = MainWindow(self.controller); self.addCleanup(self.window.deleteLater)

    def test_saved_strength_edit_disables_preview_until_save_and_reset_is_reversible(self):
        controls = self.window.character.expressions
        self.assertFalse(controls.prepare.isEnabled()); self.assertTrue(controls.preview.isEnabled())
        controls.values['mouth_open'].setValue(.4); controls.values['mouth_open'].editingFinished.emit()
        self.assertFalse(controls.preview.isEnabled()); self.assertTrue(self.controller.dirty)
        self.window.save_project(); self.assertTrue(controls.preview.isEnabled())
        controls.reset.click(); self.assertTrue(self.controller.require_project().expression.neutral)
        self.window.undo(); self.assertEqual(controls.values['mouth_open'].value(), .4)

    def test_preview_dispatch_and_cancel_enabled_while_character_is_frozen(self):
        executable = Path(self.tmp.name)/'contract-only-executable'; executable.write_text('not executed')
        self.window._blender_executable = executable
        with patch.object(self.window, '_submit', side_effect=lambda *a, **kw: self.window._busy_changed(True)) as submit:
            self.window.character.expressions.preview.click()
        self.assertEqual(submit.call_args.args[0], 'expression_preview')
        self.assertIsNotNone(submit.call_args.kwargs['cancel'])
        self.assertFalse(self.window.undo_action.isEnabled())
        self.window._work_kind = 'expression_preview'; self.window._busy_changed(True)
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertFalse(self.window.character.isEnabled())
        self.window._busy_changed(False)

    def test_dirty_preview_does_not_dispatch_and_shows_actionable_error(self):
        from ucc.desktop.expression_workflow import start_expression
        self.controller.set_expression_parameter('eye_left_closure', .2)
        with patch.object(self.window, '_error') as error, patch.object(self.window, '_submit') as submit:
            start_expression(self.window)
        submit.assert_not_called(); self.assertIn('Save all settings', error.call_args.args[0])
