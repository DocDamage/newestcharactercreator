"""Actual Qt review controls with invented metadata; no native or rights proof."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAccessible
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLabel
except ImportError:
    QApplication = None

from fixtures.body_sprite_ui import ui_request, ui_origin
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import canonical_bytes


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 unavailable')
class BodySpriteDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop.body_sprite_dialog import BodySpriteDialog
        temporary = tempfile.TemporaryDirectory(prefix='ucc-unit-body-dialog-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.review = ui_request()
        self.token = object()
        self.dialog = BodySpriteDialog(self.review.project_snapshot_json, self.review.target_binding,
                                       context_token=self.token)
        self.addCleanup(self.dialog.close)

    def choose(self, path=None):
        path = path or self.root/'UNIT_ONLY_ORIGIN.json'
        with patch('ucc.desktop.body_sprite_dialog.QFileDialog.getOpenFileName', return_value=(str(path), '')):
            self.dialog.browse_origin()
        return ui_origin(path)

    def grant(self):
        for check in self.dialog.checks: check.setChecked(True)
        self.dialog.origin_declaration.setChecked(True)
        self.dialog.matte_consent.setChecked(True)
        self.dialog.note.setText('UNIT_ONLY explicit source permissions, not actual asset authorization')
        self.dialog.destination.setText(str(self.root/'UNIT_OUTPUT'))

    def ready(self):
        origin = self.choose()
        self.assertTrue(self.dialog.set_origin_review(origin, 'UNIT qualified origin declaration', context_token=self.token))
        self.grant()
        self.assertTrue(self.dialog.render_button.isEnabled())
        return origin

    def test_defaults_never_create_permissions_or_select_origin(self):
        d = self.dialog
        self.assertFalse(d.render_button.isEnabled())
        self.assertEqual(len(d.checks), 4)
        self.assertTrue(all(not check.isChecked() for check in d.checks))
        self.assertFalse(d.origin_declaration.isChecked()); self.assertFalse(d.matte_consent.isChecked())
        self.assertEqual((d.first_frame.value(), d.frame_count.value(), d.resolution.currentData()), (1, 8, 256))
        self.assertIn('source 2–9', d.window_summary.text())
        for method in (d.request, d.origin_review, d.destination_path):
            with self.assertRaises(ValidationError): method()

    def test_every_source_grant_is_named_in_the_dialog_accessibility_tree(self):
        self.dialog.show(); self.app.processEvents()
        root = QAccessible.queryAccessibleInterface(self.dialog)
        self.assertIsNotNone(root)
        pending = [(root, 0)]; names = set(); checkbox_objects = set(); interfaces = []
        while pending:
            interface, depth = pending.pop(); interfaces.append(interface)
            self.assertLess(depth, 32); self.assertLess(len(interfaces), 1000)
            if interface.role() == QAccessible.Role.CheckBox:
                names.add(interface.text(QAccessible.Text.Name))
                checkbox_objects.add(interface.object())
            for index in range(interface.childCount()):
                child = interface.child(index)
                if child is not None: pending.append((child, depth + 1))
        expected = {'Authorize private sprite rendering: ' + label for label in
                    ('Saved character', 'Expression library', 'Registered hand', 'Selected motion')}
        self.assertTrue(expected <= names, 'Every source grant must be exposed from the dialog root: ' + str(expected - names))
        self.assertTrue(set(self.dialog.checks) <= checkbox_objects)
        self.assertEqual([label.text() for label in self.dialog.source_hash_labels],
                         ['SHA-256: ' + digest for _, digest in self.review.source_bindings])
        self.assertTrue(all(not check.isChecked() for check in self.dialog.checks))

    def test_tab_reaches_every_source_grant_and_space_checks_only_the_focused_source(self):
        self.dialog.show(); self.dialog.activateWindow(); self.app.processEvents()
        self.dialog.set_busy(True); self.dialog.set_busy(False)
        self.dialog.origin_declaration.setFocus(); self.app.processEvents()
        visited = set()
        for _ in range(64):
            focus = self.app.focusWidget() or self.dialog
            QTest.keyClick(focus, Qt.Key.Key_Tab); self.app.processEvents()
            focus = self.app.focusWidget()
            if focus in self.dialog.checks and focus not in visited:
                self.assertFalse(focus.visibleRegion().isEmpty(), 'Tab focus must scroll the grant into view')
                self.assertFalse(focus.isChecked())
                QTest.keyClick(focus, Qt.Key.Key_Space); self.app.processEvents()
                self.assertTrue(focus.isChecked()); visited.add(focus)
            if len(visited) == len(self.dialog.checks): break
        self.assertEqual(visited, set(self.dialog.checks))
        self.assertFalse(self.dialog.origin_declaration.isChecked())
        self.assertFalse(self.dialog.matte_consent.isChecked())
        self.assertFalse(self.dialog.render_button.isEnabled())

    def test_all_actual_grants_declaration_note_and_matte_are_separately_required(self):
        self.ready(); d = self.dialog
        for check in (*d.checks, d.origin_declaration, d.matte_consent):
            check.setChecked(False)
            self.assertFalse(d.render_button.isEnabled())
            with self.assertRaises(ValidationError): d.request()
            check.setChecked(True)
        d.note.clear()
        self.assertFalse(d.render_button.isEnabled())
        with self.assertRaises(ValidationError): d.request()

    def test_request_keeps_full_snapshot_binding_clock_and_fixed_copy_material(self):
        origin = self.ready(); d = self.dialog
        d.first_frame.setValue(147); d.frame_count.setValue(8); d.resolution.setCurrentIndex(0)
        request = d.request()
        self.assertEqual(request.project_snapshot_json, self.review.project_snapshot_json)
        self.assertEqual(request.target_binding, self.review.target_binding)
        self.assertEqual(request.project.animations, self.review.project.animations)
        self.assertEqual(request.window.target_frames, tuple(range(147, 155)))
        self.assertEqual(request.window.source_frames, tuple(range(148, 156)))
        self.assertEqual(request.settings.to_dict(), {'resolution':128, 'directions':4, 'yaw_deg':0., 'pitch_deg':0.})
        self.assertEqual(request.temporary_matte.base_color_srgb, (.55, .35, .25))
        self.assertEqual(request.temporary_matte.roughness, 1.)
        self.assertEqual(request.image_count, 32)
        self.assertEqual(request.source_bindings, self.review.source_bindings)
        self.assertTrue(all(p.no_ai and not p.ue_only and not p.redistribute_source_allowed for p in request.permissions))
        self.assertFalse(request.to_dict()['project_metadata_changed'])
        self.assertEqual(request.temporary_matte.to_dict()['alpha'], 1.)
        self.assertIs(d.origin_review(), origin)
        self.assertEqual(d.destination_path(), self.root/'UNIT_OUTPUT')

    def test_request_UUID_is_stable_while_settings_change_the_request_hash(self):
        self.ready(); first = self.dialog.request(); second = self.dialog.request()
        self.assertEqual(first, second)
        self.dialog.frame_count.setValue(9); changed = self.dialog.request()
        self.assertEqual(first.job_id, changed.job_id)
        self.assertNotEqual(first.sha256, changed.sha256)

    def test_origin_selection_is_path_only_and_does_not_grant_any_rights(self):
        received = []; self.dialog.origin_selected.connect(received.append)
        self.choose()
        self.assertEqual(received, [str(self.root/'UNIT_ONLY_ORIGIN.json')])
        self.assertFalse(self.dialog.render_button.isEnabled())
        self.assertTrue(all(not check.isChecked() for check in self.dialog.checks))
        self.assertFalse(hasattr(self.dialog, 'origin_role'))

    def test_new_origin_clears_all_consents_and_pending_review_cannot_render(self):
        self.ready(); self.choose(self.root/'UNIT_OTHER_ORIGIN.json')
        self.assertTrue(all(not check.isChecked() for check in self.dialog.checks))
        self.assertFalse(self.dialog.origin_declaration.isChecked())
        self.assertFalse(self.dialog.matte_consent.isChecked())
        self.assertFalse(self.dialog.render_button.isEnabled())
        with self.assertRaises(ValidationError): self.dialog.request()

    def test_stale_context_or_old_path_result_cannot_restore_origin(self):
        origin = self.choose()
        self.assertFalse(self.dialog.set_origin_review(origin, 'stale', context_token=object()))
        self.choose(self.root/'UNIT_NEW_ORIGIN.json')
        self.assertFalse(self.dialog.set_origin_review(origin, 'old path', context_token=self.token))
        self.grant()
        self.assertFalse(self.dialog.render_button.isEnabled())

    def test_origin_error_and_invalidated_context_cannot_be_reenabled(self):
        origin = self.ready()
        self.dialog.set_origin_error('UNIT origin mismatch', context_token=self.token)
        self.assertFalse(self.dialog.render_button.isEnabled())
        self.dialog.invalidate('UNIT saved project changed'); self.dialog.set_busy(False)
        self.assertFalse(self.dialog.set_origin_review(origin, 'late', context_token=self.token))
        self.grant()
        self.assertFalse(self.dialog.render_button.isEnabled())
        with self.assertRaises(ValidationError): self.dialog.request()

    def test_busy_blocks_review_changes_and_render_until_task_finishes(self):
        self.ready(); self.dialog.set_busy(True)
        self.assertFalse(self.dialog.choose_origin.isEnabled())
        self.assertFalse(self.dialog.first_frame.isEnabled())
        self.assertFalse(self.dialog.render_button.isEnabled())
        with self.assertRaises(ValidationError): self.dialog.request()
        self.dialog.set_busy(False)
        self.assertTrue(self.dialog.render_button.isEnabled())

    def test_window_cannot_run_beyond_300_and_single_final_frame_keeps_source_offset(self):
        self.ready(); self.dialog.first_frame.setValue(300); self.dialog.frame_count.setValue(2)
        self.assertFalse(self.dialog.render_button.isEnabled())
        self.assertIn('ending at or before frame 300', self.dialog.window_summary.text())
        with self.assertRaises(ValidationError): self.dialog.request()
        self.dialog.frame_count.setValue(1); request = self.dialog.request()
        self.assertEqual(request.window.source_frames, (301,))
        self.assertEqual(request.window.to_dict()['sample_span_s'], 0.)
        self.assertEqual(request.window.to_dict()['nominal_coverage_s'], 1/30)

    def test_no_selected_resolution_cannot_render(self):
        self.ready(); self.dialog.resolution.setCurrentIndex(-1)
        self.assertFalse(self.dialog.render_button.isEnabled())
        with self.assertRaises(ValidationError): self.dialog.request()

    def test_missing_hand_has_only_its_actual_three_source_grants(self):
        from ucc.desktop.body_sprite_dialog import BodySpriteDialog
        review = ui_request(hand=False)
        dialog = BodySpriteDialog(review.project_snapshot_json, review.target_binding, context_token=object())
        self.addCleanup(dialog.close)
        self.assertEqual(len(dialog.checks), 3)
        self.assertNotIn('Registered hand', dialog.source_labels)

    def test_cancelled_pickers_keep_current_review_and_output_draft(self):
        origin = self.ready()
        with patch('ucc.desktop.body_sprite_dialog.QFileDialog.getOpenFileName', return_value=('', '')):
            self.dialog.browse_origin()
        with patch('ucc.desktop.body_sprite_dialog.QFileDialog.getExistingDirectory', return_value=''):
            self.dialog.browse_destination()
        self.assertIs(self.dialog.origin_review(), origin)
        self.assertEqual(self.dialog.destination_path(), self.root/'UNIT_OUTPUT')

    def test_relative_output_and_programmatic_incomplete_accept_are_rejected(self):
        accepted = []; self.dialog.accepted.connect(lambda:accepted.append(True))
        self.dialog._accept(); self.assertFalse(accepted)
        self.ready(); self.dialog.destination.setText('relative-output')
        self.assertFalse(self.dialog.render_button.isEnabled())
        with self.assertRaises(ValidationError): self.dialog.request()
        self.dialog.destination.setText(str(self.root/'UNIT_OUTPUT')); self.dialog._accept()
        self.assertEqual(accepted, [True]); self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    def test_origin_summary_is_plain_text_without_an_image_or_role_control(self):
        origin = self.choose()
        self.dialog.set_origin_review(origin, '<b>UNIT declaration, not authorship proof</b>', context_token=self.token)
        self.assertEqual(self.dialog.origin_summary.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn('<b>UNIT', self.dialog.origin_summary.text())
        self.assertTrue(all(label.pixmap() is None or label.pixmap().isNull()
                            for label in self.dialog.findChildren(QLabel)))

    def test_noncanonical_or_material_adopted_snapshot_is_rejected(self):
        from ucc.desktop.body_sprite_dialog import BodySpriteDialog
        with self.assertRaises(ValidationError):
            BodySpriteDialog(self.review.project_snapshot_json+b'\n', self.review.target_binding, context_token=object())
        project = replace(self.review.project, appearance=(('ucc.body_material.v1', '9'*64),))
        with self.assertRaises(ValidationError):
            BodySpriteDialog(canonical_bytes(project.to_dict()), self.review.target_binding, context_token=object())
