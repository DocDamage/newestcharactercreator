"""Required-Qt captured-byte widget checks using isolated NONSHIPPING synthetic PNGs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from ucc.desktop.godot_saved_preview_widget import SavedGodotPreviewDialog
except ImportError as error:
    QApplication=None
    IMPORT_ERROR=str(error)
from fixtures.godot_saved_preview_widget_logic import synthetic_loaded
from ucc.core.errors import ValidationError


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 unavailable')
class SavedPreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:raise RuntimeError('Required Qt unavailable: '+IMPORT_ERROR)
        cls.app=QApplication.instance() or QApplication(['synthetic-saved-preview-widget-tests'])

    def dialog(self, loaded=None):
        dialog=SavedGodotPreviewDialog(loaded or synthetic_loaded())
        self.addCleanup(dialog.deleteLater)
        return dialog

    def assert_cleared(self, dialog):
        self.assertIsNone(dialog._loaded)
        self.assertEqual(dialog._frames,{})
        self.assertEqual(dialog._images,{})
        self.assertIsNone(dialog.current_frame)
        self.assertTrue(dialog.image_label.pixmap().isNull())
        self.assertEqual(dialog.facts.text(),'')
        self.assertEqual(dialog.proofs.text(),'')
        self.assertTrue(all(not b.isEnabled() and not b.isChecked() for b in dialog.frame_buttons.values()))

    def test_fixed_frames_switch_exact_captured_pixels_without_file_or_guard_IO(self):
        loaded=synthetic_loaded()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No file reads')),patch.object(Path,'open',side_effect=AssertionError('No file IO')):
            dialog=self.dialog(loaded)
            self.assertEqual(set(dialog.frame_buttons),{1,150,300})
            for frame in loaded.frames:
                dialog.frame_buttons[frame.frame].click()
                image=dialog.image_label.pixmap().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                self.assertEqual(sha256(bytes(image.constBits())).hexdigest(),frame.rgba_sha256)
                self.assertEqual(dialog.current_frame,frame.frame)
                self.assertEqual([n for n,b in dialog.frame_buttons.items() if b.isChecked()],[frame.frame])

    def test_hash_mismatch_clears_all_images_and_references(self):
        loaded=synthetic_loaded();bad=replace(loaded.frames[0],rgba_sha256='0'*64)
        dialog=self.dialog(replace(loaded,frames=(bad,*loaded.frames[1:])))
        self.assert_cleared(dialog)
        self.assertIn('pixel hash',dialog.status.text())

    def test_corrupt_later_png_cannot_leave_earlier_valid_image_visible(self):
        loaded=synthetic_loaded();bad=replace(loaded.frames[2],png_bytes=loaded.frames[2].png_bytes[:33])
        dialog=self.dialog(replace(loaded,frames=(*loaded.frames[:2],bad)))
        self.assert_cleared(dialog)
        self.assertIn('decoded',dialog.status.text())

    def test_wrong_dimensions_reject_before_decoder(self):
        loaded=synthetic_loaded();raw=loaded.frames[0].png_bytes
        bad=replace(loaded.frames[0],png_bytes=raw[:16]+struct.pack('>II',513,512)+raw[24:])
        dialog=self.dialog(replace(loaded,frames=(bad,*loaded.frames[1:])))
        self.assert_cleared(dialog)
        self.assertIn('512',dialog.status.text())

    def test_explicit_clear_is_terminal_and_plain_text(self):
        dialog=self.dialog();dialog.clear_preview('<b>Source changed</b>')
        self.assert_cleared(dialog);dialog.select_frame(150)
        self.assert_cleared(dialog)
        self.assertEqual(dialog.status.text(),'<b>Source changed</b>')
        self.assertEqual(dialog.status.textFormat(),Qt.TextFormat.PlainText)

    def test_close_and_reject_emit_once_after_images_and_references_cleared(self):
        for action in ('close','reject','accept'):
            dialog=self.dialog();events=[]
            dialog.closed.connect(lambda:events.append(dialog._loaded))
            getattr(dialog,action)();dialog.reject()
            self.assert_cleared(dialog)
            self.assertEqual(events,[None])

    def test_plain_text_metadata_never_promotes_approval(self):
        loaded=replace(synthetic_loaded(),draw_id='<img src="file:///must-not-read">')
        dialog=self.dialog(loaded)
        self.assertIn(loaded.draw_id,dialog.status.text())
        for label in (dialog.status,dialog.facts,dialog.proofs,dialog.scope):
            self.assertEqual(label.textFormat(),Qt.TextFormat.PlainText)
        self.assertIn('All broader approval flags remain false',dialog.scope.text())

    def test_duplicate_boolean_frame_and_nonfinite_fact_reject(self):
        loaded=synthetic_loaded()
        for frames in ((loaded.frames[0],loaded.frames[0],loaded.frames[2]),
                       (replace(loaded.frames[0],frame=True),*loaded.frames[1:]),
                       (replace(loaded.frames[0],max_normal_vector_error=float('nan')),*loaded.frames[1:])):
            with self.subTest(frames=tuple(f.frame for f in frames)):
                self.assert_cleared(self.dialog(replace(loaded,frames=frames)))

    def test_untyped_loaded_record_rejects_without_image_or_guard_access(self):
        for value in (None,{},object()):
            with self.subTest(value=type(value).__name__),self.assertRaises(ValidationError):
                SavedGodotPreviewDialog(value)

    def test_proof_labels_show_selected_clip_and_hashes_without_paths(self):
        loaded=synthetic_loaded();dialog=self.dialog(loaded)
        self.assertIn(loaded.selection.clip_id,dialog.proofs.text())
        self.assertIn(loaded.draw_receipt.sha256,dialog.proofs.text())
        self.assertNotIn(str(loaded.draw_receipt.path),dialog.proofs.text())

    def test_untyped_frame_rejects_without_reading_its_attributes(self):
        class ForeignFrame:
            @property
            def frame(self):
                raise AssertionError('Foreign frame attributes must not be accessed')
        loaded=synthetic_loaded()
        self.assert_cleared(self.dialog(replace(loaded,frames=(ForeignFrame(),*loaded.frames[1:]))))
