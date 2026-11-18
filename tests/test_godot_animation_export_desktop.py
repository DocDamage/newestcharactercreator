"""Real Qt dispatch and completion checks with nonshipping native fixture bytes."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fixtures.godot_registered_retention_logic import RetentionFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class GodotAnimationExportDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Required PySide6 is unavailable')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop import godot_animation_export_workflow as workflow
        from ucc.desktop.controller import DesktopController
        from ucc.desktop.window import MainWindow

        self.flow = workflow
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture = RetentionFixture(self.root)
        self.controller = DesktopController()
        self.controller.open(self.fixture.store.root)
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.deleteLater)
        self.action = self.window.godot_animation_export_action
        self.window._error = Mock()
        self.catalog = self.root/'catalog'
        self.catalog.mkdir()
        self.database = self.marker(self.catalog/'catalog.sqlite')
        self.export_parent = self.root/'exports'
        self.export_parent.mkdir()
        self.destination = self.export_parent/'PRIVATE_UNIT'
        self.authorization = self.root/'authorization.json'
        self.write_authorization()
        self.blender = self.marker(self.root/'unit-blender.exe')
        self.worker = self.marker(self.root/'unit-worker.py')
        self.godot = self.marker(self.root/'unit-console.exe')
        self.godot_main = self.marker(self.root/'unit-main.exe')
        self.pending = []
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(self.window, '_catalog_path', return_value=self.database))
        stack.enter_context(patch.object(self.window.jobs, 'submit', side_effect=self.queue))
        stack.enter_context(patch.object(workflow, 'bundled_worker_path', return_value=self.worker))
        self.prepared = SimpleNamespace(diagnostic=SimpleNamespace(receipt_sha256='a'*64),
                                        provenance=SimpleNamespace(sha256='b'*64))
        self.prepare = stack.enter_context(patch.object(
            workflow, 'prepare_first_party_godot_animation', return_value=self.prepared,
        ))
        self.publish = stack.enter_context(patch.object(
            workflow, 'publish_first_party_godot_playback', side_effect=self.publish_receipt,
        ))

    @staticmethod
    def marker(path):
        path.write_bytes(('UNIT_NONSHIPPING_NOT_EXECUTABLE:'+path.name).encode())
        return path

    def write_authorization(self, selection=None, confirmed=True):
        selection = self.fixture.selection if selection is None else selection
        self.authorization.write_bytes(canonical_bytes({
            'schema_version': 1,
            'policy': 'UCC_PRIVATE_FIRST_PARTY_GODOT_AUTHORIZATION_V1',
            'selection': selection.to_dict(),
            'permissions': [permission.to_dict() for permission in self.fixture.permissions],
            'purpose': 'Synthetic desktop authority only',
            'private_local_execution_confirmed': confirmed,
        }))

    def queue(self, operation, *, cancel):
        self.pending.append((operation, cancel))
        return True

    def publish_receipt(self, store, **arguments):
        directory = arguments['destination'].path
        directory.mkdir()
        names = self.flow.RUNTIME_FILES | {'character.tscn', 'playback.json'}
        files = {}
        for name in sorted(names):
            marker = self.marker(directory/name)
            files[name] = sha256(marker.read_bytes()).hexdigest()
        receipt = canonical_bytes({
            'schema_version': 1,
            'policy': self.flow.POLICY,
            'private_local_only': True,
            'binding_sha256': arguments['selection'].binding_sha256,
            'diagnostic_receipt_sha256': self.prepared.diagnostic.receipt_sha256,
            'runtime_provenance_sha256': self.prepared.provenance.sha256,
            'observation_sha256': 'e'*64,
            'observed': self.flow.VERIFIED,
            'files': files,
            'distribution_review_complete': False,
            'material_appearance_approved': False,
        })
        (directory/self.flow.RECEIPT).write_bytes(receipt)
        return self.flow.PublishedFirstPartyGodotPlayback(directory, sha256(receipt).hexdigest())

    def start(self, *, selections=None, name=None):
        if selections is None:
            selections = [self.authorization, self.blender, self.godot, self.godot_main]
        with (
            patch.object(self.flow.QFileDialog, 'getOpenFileName',
                         side_effect=[(str(path), '') for path in selections]) as files,
            patch.object(self.flow.QFileDialog, 'getExistingDirectory',
                         return_value=str(self.export_parent)) as parent,
            patch.object(self.flow.QInputDialog, 'getText',
                         side_effect=name or (lambda *args, **kwargs: (self.destination.name, True))),
        ):
            self.action.trigger()
        return files, parent

    def assert_no_native_dispatch(self):
        self.assertEqual(self.pending, [])
        self.prepare.assert_not_called()
        self.publish.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_cancelling_authorization_picker_never_asks_for_tools_or_dispatches(self):
        self.assertTrue(self.action.isEnabled())
        files, parent = self.start(selections=[''])
        files.assert_called_once()
        parent.assert_not_called()
        self.window._error.assert_not_called()
        self.assert_no_native_dispatch()

    def test_cancelling_new_folder_name_never_dispatches(self):
        files, parent = self.start(name=lambda *args, **kwargs: ('', False))
        self.assertEqual(files.call_count, 4)
        parent.assert_called_once()
        self.window._error.assert_not_called()
        self.assert_no_native_dispatch()

    def test_authorization_for_different_saved_revision_cannot_dispatch(self):
        self.write_authorization(selection=replace(self.fixture.selection,
                                                   revision=self.fixture.selection.revision+1))
        self.start()
        self.window._error.assert_called_once()
        self.assert_no_native_dispatch()

    def test_project_edit_during_destination_picker_prevents_dispatch(self):
        def change_draft(*args, **kwargs):
            self.window.rename('UNIT_CHANGED_WHILE_PICKING')
            return self.destination.name, True

        self.start(name=change_draft)
        self.window._error.assert_called_once()
        self.assert_no_native_dispatch()

    def test_authorization_changed_after_queue_blocks_native_before_preparation(self):
        self.start()
        self.assertEqual(len(self.pending), 1)
        operation, _ = self.pending[0]
        self.write_authorization(confirmed=False)
        with self.assertRaises((ProjectConflict, ProjectStorageError, ValidationError)):
            operation()
        self.prepare.assert_not_called()
        self.publish.assert_not_called()

    def test_authorization_revoked_after_preparation_never_starts_publication(self):
        self.start()
        operation, _ = self.pending[0]

        def prepare_and_revoke(*args, **kwargs):
            self.write_authorization(confirmed=False)
            return self.prepared

        self.prepare.side_effect = prepare_and_revoke
        with self.assertRaises((ProjectConflict, ProjectStorageError, ValidationError)):
            operation()
        self.prepare.assert_called_once()
        self.publish.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_menu_queues_native_work_and_reports_only_receipt_confirmed_result(self):
        self.start()
        self.assertEqual(self.window._work_kind, self.flow.KIND)
        self.assertEqual(len(self.pending), 1)
        self.prepare.assert_not_called()
        self.publish.assert_not_called()
        self.window._busy_changed(True)
        self.assertTrue(self.window.statusBar().currentMessage())
        self.window._busy_changed(False)
        operation, cancellation = self.pending[0]
        result = operation()
        self.assertFalse(cancellation.is_set())
        self.prepare.assert_called_once()
        self.publish.assert_called_once()
        prepare, publish = self.prepare.call_args.kwargs, self.publish.call_args.kwargs
        self.assertTrue(callable(publish['authorization_guard']))
        self.assertEqual(prepare['selection'], self.fixture.selection)
        self.assertIs(prepare['permissions'], publish['permissions'])
        self.assertEqual(prepare['worker_script'], self.worker)
        self.assertEqual(publish['destination'].path, self.destination)
        self.window._job_success(result)
        self.window._error.assert_not_called()
        self.assertIn('Private animated Godot project verified', self.window.log.toPlainText())
        self.assertIn(str(self.destination), self.window.log.toPlainText())

    def test_changed_playback_receipt_cannot_display_verified(self):
        self.start()
        operation, _ = self.pending[0]
        result = operation()
        (self.destination/self.flow.RECEIPT).write_bytes(b'UNIT_CHANGED_AFTER_NATIVE')
        self.window._job_success(result)
        self.window._error.assert_called_once()
        self.assertIn('could not be confirmed', self.window._error.call_args.args[0])
        self.assertNotIn('Private animated Godot project verified', self.window.log.toPlainText())

    def test_same_byte_replaced_scene_cannot_display_verified(self):
        self.start()
        operation, _ = self.pending[0]
        result = operation()
        scene = self.destination/'character.tscn'
        replacement = self.root/'replacement.tscn'
        replacement.write_bytes(scene.read_bytes())
        replacement.replace(scene)
        self.window._job_success(result)
        self.window._error.assert_called_once()
        self.assertIn('could not be confirmed', self.window._error.call_args.args[0])
        self.assertNotIn('Private animated Godot project verified', self.window.log.toPlainText())
