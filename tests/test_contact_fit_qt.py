"""Actual Qt action wiring with mocked fitting; no runtime/asset success claim."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import test_desktop_qt as desktop_fixture
try:
    from ucc.desktop.contact_fit import start_contact_fit
except ImportError:
    start_contact_fit=None


@unittest.skipIf(desktop_fixture.QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 not installed')
class ContactFitQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):desktop_fixture.DesktopQtSmoke.setUpClass()

    def setUp(self):
        self.f=desktop_fixture.DesktopQtSmoke();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.w=self.f.window;self.root=Path(self.f.tmp.name)
        self.source=self.root/'unit.fbx';self.source.write_bytes(b'unit-only-not-animation')
        self.executable=self.root/'unit-blender';self.executable.write_bytes(b'unit-only-not-program')
        pane=self.w.animations;pane.selected.setText(str(self.source));pane.provider.setText('Original unit fixture')
        pane.license.setText('CC0');pane.uri.setText('original-unit://contact-fit');pane.local_preview_review.setChecked(True)
        self.w._blender_executable=self.executable;self.preview=SimpleNamespace(unit_only=True);self.playback=SimpleNamespace(unit_only=True)
        self.w._native_review=self.preview;self.w._native_playback=self.playback

    def test_defined_action_dispatches_guarded_api_with_current_source_rights_and_cancel_event(self):
        with (patch.object(self.w,'_submit') as submit,patch('ucc.desktop.contact_fit.bundled_worker_path',return_value=self.root/'unit.py'),
              patch('ucc.desktop.contact_fit.fit_measured_contacts',return_value='unit-only') as fit):
            start_contact_fit(self.w);submit.assert_called_once()
            args,kwargs=submit.call_args;self.assertEqual(args[0],'fitted_comparison')
            self.assertEqual(args[1](),'unit-only');fargs,fkw=fit.call_args
            self.assertIs(fargs[1],self.preview);self.assertIs(fargs[2],self.playback)
            self.assertEqual(fkw['source_fbx'],self.source);self.assertEqual(fkw['blender_exe'],self.executable)
            self.assertIs(fkw['cancel'],kwargs['cancel']);self.assertTrue(fkw['permission'].allow('local_preview')[0])
            self.assertIn('several minutes',self.w.log.toPlainText())

    def test_missing_preview_or_revoked_review_does_not_dispatch(self):
        with patch.object(self.w,'_submit') as submit,patch.object(self.w,'_error') as error:
            self.w._native_playback=None;start_contact_fit(self.w);self.assertTrue(error.called);submit.assert_not_called()
            self.w._native_playback=self.playback;self.w.animations.local_preview_review.setChecked(False)
            start_contact_fit(self.w);submit.assert_not_called()

    def test_busy_action_does_not_touch_inputs_or_start_another_task(self):
        error=Mock();window=SimpleNamespace(jobs=SimpleNamespace(busy=True),_error=error)
        start_contact_fit(window);error.assert_called_once_with('Another local task is still running')

    def test_rejection_dialog_has_plain_reason_and_preserves_full_local_details(self):
        from ucc.desktop.contact_fit import fit_error_message
        error='worker traceback: MULTIPLE_CONTACTING_HANDS_UNSUPPORTED\nprivate diagnostic detail'
        message=fit_error_message(error);self.assertIn('Both hands',message);self.assertNotIn('traceback',message)
        self.w._work_kind='fitted_comparison'
        with patch('PySide6.QtWidgets.QMessageBox') as dialog:
            self.w._job_error(error)
            dialog.return_value.setText.assert_called_once_with(message)
            dialog.return_value.setDetailedText.assert_called_once_with(error)
            dialog.return_value.exec.assert_called_once()
        self.assertIn(error,self.w.log.toPlainText())
        self.assertIn('cancelled',fit_error_message('Contact fitting cancelled; original retained'))
        self.assertIn('Reload',fit_error_message('unrecognized verification failure'))


if __name__=='__main__':unittest.main()
