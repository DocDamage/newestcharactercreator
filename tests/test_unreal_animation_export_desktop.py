"""Headless Qt coverage for the private Unreal animation export menu and delivery seal."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, PropertyMock, patch

from fixtures.godot_registered_retention_logic import RetentionFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.unreal_animation_authorization import POLICY

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1',
                 'Optional PySide6 unavailable')
class UnrealAnimationExportDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Required PySide6 is unavailable')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from ucc.desktop import unreal_animation_export_workflow as workflow
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
        self.action = self.window.unreal_animation_export_action
        self.window._error = Mock()
        catalog = self.root/'catalog'
        catalog.mkdir()
        self.database = self.marker(catalog/'catalog.sqlite3')
        self.export_parent = self.root/'export'
        self.export_parent.mkdir()
        self.destination = self.export_parent/'PRIVATE_UNIT'
        self.authorization = self.root/'authority.json'
        self.write_authorization()
        self.blender = self.marker(self.root/'unit-blender.exe')
        self.worker = self.marker(self.root/'unit-worker.py')
        self.unreal = self.marker(self.root/'unit-unreal.exe')
        self.pending = []
        self.receipt_overrides = {}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(self.window, '_catalog_path', return_value=self.database))
        stack.enter_context(patch.object(self.window.jobs, 'submit', side_effect=self.queue))
        stack.enter_context(patch.object(workflow, 'bundled_worker_path', return_value=self.worker))
        self.export = stack.enter_context(patch.object(workflow, 'export_unreal_animation', side_effect=self.publish))

    @staticmethod
    def marker(path):
        path.write_bytes(('UNIT_NONSHIPPING_NOT_EXECUTABLE:'+path.name).encode())
        return path

    def write_authorization(self, *, selection=None, engine='unreal'):
        if selection is None:
            selection = self.fixture.selection
        self.authorization.write_bytes(canonical_bytes(dict(schema_version=1, policy=POLICY, engine=engine,
            selection=selection.to_dict(), permissions=[
                replace(row, policy=replace(row.policy, can_use_unreal=True, can_use_non_unreal=False)).to_dict()
                for row in self.fixture.permissions
            ],
            purpose='Synthetic Unreal desktop permission only', private_local_execution_confirmed=True)))

    def queue(self, operation, *, cancel):
        self.pending.append((operation, cancel))
        return True

    def publish(self, store, **arguments):
        arguments['authorization_guard']()
        directory = arguments['destination'].path
        directory.mkdir()
        files = {}
        for name in sorted(self.flow.PORTABLE_FILES):
            path = directory/name
            path.parent.mkdir(parents=True, exist_ok=True)
            files[name] = sha256(self.marker(path).read_bytes()).hexdigest()
        (directory/'README.txt').write_bytes(self.flow.README)
        receipt = dict(schema_version=1, policy=self.flow.POLICY,
            unreal_version=self.flow.ENGINE_VERSION, verification_sha256='a'*64, portable_files=files,
            binding_sha256=self.fixture.selection.binding_sha256,
            private_local_only=True, corrected_runtime_verified=True, pie_verified=True,
            material_appearance_approved=False, distribution_review_complete=False)
        receipt.update(self.receipt_overrides)
        raw = canonical_bytes(receipt)
        (directory/self.flow.RECEIPT).write_bytes(raw)
        return self.flow.PublishedUnrealAnimation(directory, sha256(raw).hexdigest())

    def start(self, *, selections=None, name=None, parent=None):
        if selections is None:
            selections = [self.authorization, self.blender, self.unreal]
        with (
            patch.object(self.flow.QFileDialog, 'getOpenFileName',
                         side_effect=[(str(path), '') for path in selections]) as files,
            patch.object(self.flow.QFileDialog, 'getExistingDirectory',
                         return_value=str(parent if parent is not None else self.export_parent)) as folder_picker,
            patch.object(self.flow.QInputDialog, 'getText',
                         side_effect=name or (lambda *args, **kwargs: (self.destination.name, True))),
        ):
            self.action.trigger()
        return files, folder_picker

    def assert_no_dispatch(self):
        self.assertEqual(self.pending, [])
        self.export.assert_not_called()
        self.assertFalse(self.destination.exists())

    def assert_no_success(self):
        self.assertNotIn('Private animated Unreal project verified', self.window.log.toPlainText())
        self.assertNotEqual(self.window.statusBar().currentMessage(), 'Private animated Unreal project verified')

    def test_file_menu_dispatches_only_exact_private_authority_and_verified_delivery(self):
        actions = [action for menu in self.window.menuBar().actions() if menu.text() == '&File'
                   for action in menu.menu().actions()]
        self.assertIn(self.action, actions)
        self.assertIn(self.window.unreal_export_action, actions)
        self.assertIn(self.window.unity_animation_export_action, actions)
        self.assertIn(self.window.godot_animation_export_action, actions)
        self.assertEqual(self.action.text(), 'Export private animated Unreal project…')
        self.assertTrue(self.action.isEnabled())
        name_picker = Mock(return_value=(self.destination.name, True))
        files, parent = self.start(name=name_picker)
        self.assertEqual([call.args[1] for call in files.call_args_list], [
            'Choose private Unreal animation authorization',
            'Choose installed Blender executable',
            'Choose installed Unreal Editor executable',
        ])
        parent.assert_called_once_with(self.window, 'Choose parent folder for private animated Unreal project')
        name_picker.assert_called_once_with(self.window, 'Private animated Unreal project', 'New export folder name')
        self.assertEqual(self.window._work_kind, self.flow.KIND)
        self.export.assert_not_called()
        self.window._busy_changed(True)
        self.assertFalse(self.action.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.assertIn('animated Unreal project', self.window.statusBar().currentMessage())
        self.window._busy_changed(False)
        self.assertTrue(self.action.isEnabled())
        operation, cancel = self.pending[0]
        result = operation()
        arguments = self.export.call_args.kwargs
        self.assertIs(self.export.call_args.args[0], self.controller.store)
        self.assertEqual(arguments['authorization'].selection, self.fixture.selection)
        self.assertEqual(arguments['database_path'], self.database)
        self.assertEqual(arguments['blender_exe'], self.blender)
        self.assertEqual(arguments['worker_script'], self.worker)
        self.assertEqual(arguments['unreal_exe'], self.unreal)
        self.assertEqual(arguments['unreal_executable_sha256'], sha256(self.unreal.read_bytes()).hexdigest())
        self.assertEqual(arguments['destination'].path, self.destination)
        self.assertFalse(cancel.is_set())
        self.window._job_success(result)
        self.window._error.assert_not_called()
        log = self.window.log.toPlainText()
        self.assertIn('Private animated Unreal project verified', log)
        self.assertIn(str(self.destination), log)
        self.assertIn('Material appearance and distribution approval are pending.', log)
        self.export.assert_called_once()

    def test_cancelling_authorization_picker_never_asks_for_tools_or_dispatches(self):
        files, folder = self.start(selections=[''])
        files.assert_called_once()
        folder.assert_not_called()
        self.window._error.assert_not_called()
        self.assert_no_dispatch()

    def test_cancelling_destination_name_does_not_dispatch(self):
        files, folder = self.start(name=lambda *args, **kwargs: ('', False))
        self.assertEqual(files.call_count, 3)
        folder.assert_called_once()
        self.window._error.assert_not_called()
        self.assert_no_dispatch()

    def test_other_engine_and_saved_revision_do_not_dispatch(self):
        self.write_authorization(engine='godot')
        self.start()
        self.window._error.assert_called_once()
        self.assert_no_dispatch()
        self.window._error.reset_mock()
        self.write_authorization(selection=replace(self.fixture.selection, revision=self.fixture.selection.revision+1))
        self.start()
        self.window._error.assert_called_once()
        self.assert_no_dispatch()

    def test_dirty_project_during_picker_blocks_dispatch_and_disables_action(self):
        def change_draft(*args, **kwargs):
            self.window.rename('UNIT_CHANGED_WHILE_PICKING')
            return self.destination.name, True

        self.start(name=change_draft)
        self.window._error.assert_called_once()
        self.assertFalse(self.action.isEnabled())
        self.assert_no_dispatch()

    def test_destination_inside_catalog_is_refused_before_dispatch(self):
        self.start(parent=self.database.parent)
        self.window._error.assert_called_once()
        self.assert_no_dispatch()
        self.assertFalse((self.database.parent/self.destination.name).exists())

    def test_byte_changed_authority_blocks_worker_dispatch_even_with_same_fields(self):
        self.start()
        operation, _ = self.pending[0]
        self.authorization.write_bytes(self.authorization.read_bytes()+b' ')
        with self.assertRaises(ProjectConflict):
            operation()
        self.export.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_closing_authorization_guard_rejects_revocation_during_pipeline(self):
        def revoke(*args, **kwargs):
            self.write_authorization(engine='godot')
            kwargs['authorization_guard']()

        self.export.side_effect = revoke
        self.start()
        operation, _ = self.pending[0]
        with self.assertRaises(ProjectConflict):
            operation()
        self.export.assert_called_once()
        self.assertFalse(self.destination.exists())

    def test_cancelled_worker_never_calls_native_pipeline(self):
        self.start()
        operation, cancel = self.pending[0]
        cancel.set()
        with self.assertRaises(ProjectStorageError):
            operation()
        self.export.assert_not_called()
        with patch.object(type(self.window.jobs), 'cancel_requested', new_callable=PropertyMock, return_value=True):
            self.window._job_error('Unit cancellation')
        self.window._error.assert_not_called()
        self.assertIn('Animated Unreal export cancelled', self.window.log.toPlainText())
        self.assert_no_success()

    def test_unverified_receipt_never_reports_success(self):
        for field, value in [('pie_verified', False), ('binding_sha256', 'd'*64)]:
            with self.subTest(field=field):
                self.receipt_overrides = {field: value}
                self.start()
                operation, _ = self.pending.pop()
                with self.assertRaisesRegex(ProjectStorageError, 'Inspect the retained package'):
                    operation()
                self.assert_no_success()
                self.destination = self.export_parent/'SECOND_PRIVATE_UNIT'

    def test_portable_payload_hash_must_match_published_receipt(self):
        def change_asset(*args, **kwargs):
            result = self.publish(*args, **kwargs)
            (self.destination/'Content/UccAnimation/CharacterScene.umap').write_bytes(b'UNIT_UNSEALED_SCENE')
            return result

        self.export.side_effect = change_asset
        self.start()
        operation, _ = self.pending[0]
        with self.assertRaisesRegex(ProjectStorageError, 'sealed files'):
            operation()
        self.assert_no_success()

    def test_receipt_change_after_worker_rejects_verification(self):
        self.start()
        operation, _ = self.pending[0]
        result = operation()
        (self.destination/self.flow.RECEIPT).write_bytes(b'UNIT_CHANGED_RECEIPT')
        self.window._job_success(result)
        self.window._error.assert_called_once()
        self.assert_no_success()

    def test_nested_same_byte_scene_replacement_after_worker_rejects_verification(self):
        self.start()
        operation, _ = self.pending[0]
        result = operation()
        scene = self.destination/'Content/UccAnimation/CharacterScene.umap'
        replacement = self.root/'replacement.umap'
        replacement.write_bytes(scene.read_bytes())
        replacement.replace(scene)
        self.window._job_success(result)
        self.window._error.assert_called_once()
        self.assert_no_success()

    def test_extra_nested_output_after_worker_rejects_verification(self):
        self.start()
        operation, _ = self.pending[0]
        result = operation()
        self.marker(self.destination/'Content/UccAnimation/extra.bytes')
        self.window._job_success(result)
        self.window._error.assert_called_once()
        self.assert_no_success()
