"""Real Qt dispatch boundaries using nonshipping reports, never a real Action."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
import unittest
from unittest.mock import patch, sentinel

try:
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.window import MainWindow
    from ucc.desktop import target_action_workflow as actions
    from ucc.desktop import target_action_diagnostic_workflow as diagnostics
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class TargetDiagnosticIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Diagnostic integration tests require Qt')
        cls.app = QApplication.instance() or QApplication(['diagnostic-integration-tests'])

    def test_diagnostic_success_routes_before_target_action_publication(self):
        window = SimpleNamespace(_work_kind='target_action_diagnostic')
        with patch.object(diagnostics, 'finish_target_action_diagnostic') as finish, \
                patch.object(actions, 'publish_target_action') as publish:
            actions.finish_target_action(window, sentinel.report)
        finish.assert_called_once_with(window, sentinel.report)
        publish.assert_not_called()

    def test_diagnostic_failure_routes_without_saved_action_publication(self):
        window = SimpleNamespace(_work_kind='target_action_diagnostic')
        with patch.object(diagnostics, 'target_action_diagnostic_error') as failed:
            actions.target_action_error(window, 'Synthetic caller cancellation')
        failed.assert_called_once_with(window, 'Synthetic caller cancellation')

    def test_busy_diagnostic_has_status_and_actual_cancel_control(self):
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window._clear_preview)
        window._work_kind = 'target_action_diagnostic'
        window._busy_changed(True)
        self.assertTrue(window.cancel_generation_action.isEnabled())
        self.assertIn('diagnostic', window.statusBar().currentMessage().lower())
        window._busy_changed(False)
        self.assertFalse(window.cancel_generation_action.isEnabled())


if __name__ == '__main__':
    unittest.main()
