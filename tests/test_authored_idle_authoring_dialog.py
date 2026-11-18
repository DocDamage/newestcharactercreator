"""Qt consent and destination controls with invented local policy records."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.authored_idle import CLEAR_IDLE_PROFILE, PROFILE
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle_policy import FLAGS, POLICY
from ucc.jobs.authored_idle_sources import IdleAuthoringSource

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog
    from ucc.desktop.authored_idle_authoring_dialog import AuthoredIdleAuthoringDialog
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 not installed')
class AuthoredIdleAuthoringDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Authored idle dialog tests require PySide6')
        cls.app = QApplication.instance() or QApplication(['authored-idle-authoring-dialog-tests'])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        hand_id = 'part:ucc-hand-v1-' + '5'*64 + '-longer'
        self.sources = (IdleAuthoringSource('expression_library', '1'*64, '2'*64),
                        IdleAuthoringSource('master_and_derived_rig', '3'*64, '4'*64),
                        IdleAuthoringSource(hand_id, '5'*64, '6'*64))
        self.policies = tuple(self.policy(source, f'policy{i}.json') for i, source in enumerate(self.sources))
        self.dialog = AuthoredIdleAuthoringDialog(self.sources)
        self.addCleanup(self.dialog.deleteLater)

    def policy(self, source, name):
        path = self.root/name
        path.write_bytes(canonical_bytes({'schema_version': 1, 'policy': POLICY, 'asset_id': source.asset_id,
            'source_sha256': source.sha256, 'provenance_sha256': source.provenance_sha256,
            'review_note': 'NONSHIPPING invented authorization for test', **FLAGS}))
        return path

    def choose_policy(self, index, path):
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path) if path else '', '')):
            self.dialog.rows[index].choose.click()

    def choose_output(self):
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=str(self.root)):
            self.dialog.choose_parent.click()
        self.dialog.candidate_name.setText('authored candidate')

    def make_ready(self):
        dialog = self.dialog
        for i, path in enumerate(self.policies):
            self.choose_policy(i, path)
            dialog.rows[i].confirm.click()
            dialog.rows[i].note.setText(f'Individually confirm use {i}')
        dialog.purpose.setText('Review this local idle')
        dialog.recipe.click()
        dialog.preview.click()
        self.choose_output()

    def test_requires_all_sources_and_separate_consents(self):
        dialog = self.dialog
        self.assertEqual([row.source for row in dialog.rows], list(self.sources))
        checks = [dialog.recipe, dialog.preview, dialog.write_proof, *(row.confirm for row in dialog.rows)]
        for check in checks:
            self.assertFalse(check.isChecked())
        self.assertFalse(dialog.create_button.isEnabled())
        self.make_ready()
        for check in (dialog.recipe, dialog.preview, *(row.confirm for row in dialog.rows)):
            check.click()
            self.assertFalse(dialog.create_button.isEnabled())
            check.click()
            self.assertTrue(dialog.create_button.isEnabled())
        dialog.create_button.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        choice = dialog.choice
        self.assertEqual([row.path for row in choice.source_policy_records], list(self.policies))
        self.assertEqual([row.asset_id for row in choice.permissions], [source.asset_id for source in self.sources])
        self.assertEqual([row.note for row in choice.permissions], [f'Individually confirm use {i}' for i in range(3)])
        self.assertEqual([row.source_policy_sha256 for row in choice.permissions],
                         [row.sha256 for row in choice.source_policy_records])
        self.assertEqual(choice.candidate_destination, self.root/'authored candidate')
        self.assertIsNone(choice.proof_destination)
        self.assertEqual(choice.profile, CLEAR_IDLE_PROFILE)

    def test_switching_movement_requires_consent_for_the_selected_recipe(self):
        self.make_ready()
        dialog = self.dialog
        dialog.profile.setCurrentIndex(dialog.profile.findData(PROFILE))
        self.assertFalse(dialog.recipe.isChecked())
        self.assertTrue(dialog.preview.isChecked())
        self.assertFalse(dialog.create_button.isEnabled())
        dialog.recipe.click()
        dialog.create_button.click()
        self.assertEqual(dialog.choice.profile, PROFILE)

    def test_cancelled_picker_preserves_choice_and_wrong_role_revokes_it(self):
        dialog = self.dialog
        self.make_ready()
        self.choose_policy(0, None)
        self.assertTrue(dialog.create_button.isEnabled())
        self.choose_policy(0, self.policies[1])
        self.assertFalse(dialog.create_button.isEnabled())
        self.assertFalse(dialog.rows[0].confirm.isChecked())
        self.assertFalse(dialog.rows[0].note.text())
        self.assertTrue(dialog.rows[1].confirm.isChecked())
        self.choose_policy(0, self.policies[0])
        self.assertFalse(dialog.create_button.isEnabled())

    def test_rechecks_policy_bytes_on_accept(self):
        self.make_ready()
        path = self.policies[2]
        path.write_bytes(path.read_bytes() + b' ')
        self.dialog.create_button.click()
        self.assertIsNone(self.dialog.choice)
        self.assertIn('changed', self.dialog.status.text())

    def test_proof_needs_explicit_distinct_new_sibling(self):
        self.make_ready()
        dialog = self.dialog
        dialog.write_proof.click()
        self.assertFalse(dialog.create_button.isEnabled())
        for rejected in ('../elsewhere', 'AUTHORED CANDIDATE', self.policies[0].name):
            dialog.proof_name.setText(rejected)
            self.assertFalse(dialog.create_button.isEnabled())
        dialog.proof_name.setText('separate proof')
        self.assertTrue(dialog.create_button.isEnabled())
        dialog.create_button.click()
        self.assertEqual(dialog.choice.proof_destination, self.root/'separate proof')
        self.assertFalse(dialog.choice.proof_destination.exists())

    def test_walk_requires_source_notes_recipe_and_preview_with_no_idle_controls(self):
        self.dialog = AuthoredIdleAuthoringDialog(self.sources[:2], walk=True)
        self.addCleanup(self.dialog.deleteLater)
        self.policies = self.policies[:2]
        self.assertEqual(self.dialog.windowTitle(), 'Create private original walk')
        self.assertIsNone(self.dialog.profile)
        self.assertIsNone(self.dialog.write_proof)
        self.assertIsNone(self.dialog.proof_name)
        self.assertIn('walk', self.dialog.recipe.text())
        self.make_ready()
        self.dialog.purpose.setText('Review this local walk')
        for control in (self.dialog.recipe, self.dialog.preview, *(row.confirm for row in self.dialog.rows)):
            control.setChecked(False)
            self.assertFalse(self.dialog.create_button.isEnabled())
            control.setChecked(True)
        self.dialog.create_button.click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIsNone(self.dialog.choice.proof_destination)
        self.assertEqual(self.dialog.choice.profile, PROFILE)
        self.assertEqual(self.dialog.choice.purpose, 'Review this local walk')

    def test_walk_cannot_review_an_installed_part(self):
        with self.assertRaisesRegex(ValidationError, 'no installed parts'):
            AuthoredIdleAuthoringDialog(self.sources, walk=True)
