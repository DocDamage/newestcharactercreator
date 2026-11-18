"""Synthetic private-cache UI boundary tests; no Blender, pixels or GPU proof."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import Mock, patch

from fixtures.target_action_contract import metadata_pair
from fixtures.motion_skin_contract import write_cache
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.target_action_format import canonical_bytes
from ucc.preview.motion_cache import read_motion_cache

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QTextEdit, QWidget
    from ucc.desktop.target_action_dialog import TargetActionChoice
    from ucc.desktop.target_action_preview import (
        _changed, _stamp, clear_target_action_preview, publish_target_action,
        refresh_target_action_preview,
    )
    from ucc.desktop.target_action_workflow import TargetActionContext, finish_target_action, _boundary
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None and os.environ.get('UCC_REQUIRE_QT') != '1', 'Optional PySide6 not installed')
class TargetActionDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError('Target Action desktop tests require PySide6')
        cls.app = QApplication.instance() or QApplication(['target-action-desktop-tests'])

    def setUp(self):
        from ucc.jobs.target_action import PreparedTargetAction
        class Canvas(QWidget):
            failed = Signal(str)
            def __init__(self, cache, parent):
                super().__init__(parent)
                self.cache = cache
                self.frame = 0
            def release(self):
                pass
            def reset_view(self):
                pass
        self.addCleanup(patch.stopall)
        patch('ucc.desktop.motion_viewer.MotionCanvas', Canvas).start()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.root = root
        metadata = root/'project.ucc.json'; metadata.write_bytes(b'{"nonshipping":"unit metadata"}')
        master = root/'unit-master.blend'; master.write_bytes(b'nonshipping unit master bytes')
        source_dir = root/'unit-source'; source_dir.mkdir()
        source = source_dir/'unit-source.fbx'; source.write_bytes(b'nonshipping unit source bytes')
        database = root/'unit-catalog.db'; database.write_bytes(b'unit catalog token checked by mock')
        record = {'nonshipping': 'unit source registration'}
        request, original = metadata_pair()
        source_meta = replace(original.source, source_sha256=sha256(source.read_bytes()).hexdigest(),
                              source_binding_sha256=canonical_digest(record))
        target = replace(original.target, project_sha256=sha256(metadata.read_bytes()).hexdigest(),
                         master_sha256=sha256(master.read_bytes()).hexdigest())
        request = replace(request, source=source_meta, project_sha256=target.project_sha256,
                          master_sha256=target.master_sha256)
        payloads = {item.name: b'NONSHIPPING UI METADATA FIXTURE: ' + item.name.encode() for item in original.files}
        payloads['preparation_request.json'] = canonical_bytes(request.to_dict())
        files = tuple(replace(item, sha256=sha256(payloads[item.name]).hexdigest(),
                              bytes=len(payloads[item.name])) for item in original.files)
        self.binding = replace(original, source=source_meta, target=target,
            preparation_request_sha256=request.sha256, files=files,
            mapping_sha256=sha256(payloads['native_mapping.json']).hexdigest())
        directory = root/'animations/actions'/self.binding.sha256
        directory.mkdir(parents=True)
        binding_path = directory/'binding.json'; binding_path.write_bytes(canonical_bytes(self.binding.to_dict()))
        for name, data in payloads.items():
            path = directory/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        reference_path = root/'animations/references'/(sha256(source_meta.clip_id.encode()).hexdigest()+'.json')
        reference_path.parent.mkdir(parents=True)
        reference_path.write_bytes(canonical_bytes(record))
        cache_folder = root/'unit-cache'; cache_folder.mkdir()
        _, report, bindings, timeline = write_cache(cache_folder)
        cache = read_motion_cache(cache_folder, report, bindings, timeline)
        cache = replace(cache, chunks=(cache.chunks[0],)*300, hips=(cache.hips[0],)*300,
                        fps=30., source_first_frame=2)
        hashes = {directory/name: item.sha256 for name, item in self.binding.file_map.items()}
        hashes.update({metadata: target.project_sha256, master: target.master_sha256,
                       source: source_meta.source_sha256, binding_path: self.binding.sha256,
                       reference_path: source_meta.source_binding_sha256})
        directories = {root, *(path.parent for path in hashes), directory.parent, directory.parent.parent}
        identities = tuple((path, _stamp(path)) for path in (*hashes, database, *sorted(directories)))
        self.result = PreparedTargetAction(target.project_id, target.revision, target.project_sha256,
            target.master_sha256, source_meta.clip_id, source_meta.source_sha256,
            directory, binding_path, self.binding.sha256, cache,
            tuple(hashes.items()), identities)
        project = SimpleNamespace(project_id=target.project_id, revision=target.revision,
            master_blend=master.name, animations=(source_meta.clip_id,))
        store = SimpleNamespace(root=root, file=metadata, load=lambda: project, _check_safety=lambda: None)
        self.context = TargetActionContext(store, project, database, target.project_sha256)
        self.review = SimpleNamespace(project_sha256=target.project_sha256, master_sha256=target.master_sha256,
                                      source=source_meta, source_path=source)
        patch('ucc.jobs.animation_reference_storage.load_source_binding', return_value=record).start()
        self.catalog = patch('ucc.jobs.target_action.check_target_action_catalog').start()
        self.window = QMainWindow()
        self.window.controller = SimpleNamespace(store=store, has_project=True, dirty=False,
                                                 require_project=lambda: project)
        self.window.mesh_dock = QDockWidget(self.window)
        self.window.log = QTextEdit(self.window)
        self.window._clear_native_review = Mock()
        self.window._error = Mock()
        self.window.jobs = SimpleNamespace(cancel_requested=False)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(lambda: clear_target_action_preview(self.window))

    def publish(self):
        publish_target_action(self.window, self.context, self.review, self.result,
                              selected_binding=self.result.binding_sha256)
        return self.window._target_action_viewer

    def test_one_shot_play_pause_seek_and_last_frame_without_unsupported_actions(self):
        viewer = self.publish()
        self.assertIn(self.result.clip_id, viewer.status.text())
        self.assertFalse(viewer.loop.isChecked())
        for widget in (viewer.loop, viewer.try_fit, viewer.review_body, viewer.highlight,
                       viewer.focus, viewer.next_flagged, viewer.max_pairs, viewer.inspection,
                       viewer.variant, viewer.surface_status):
            self.assertTrue(widget.isHidden())
            self.assertFalse(widget.isEnabled())
        with patch('ucc.desktop.motion_viewer.time.monotonic', return_value=10.):
            viewer.play.click()
        self.assertTrue(viewer.clock.playing)
        self.assertTrue(viewer.guard_timer.isActive())
        with patch('ucc.desktop.motion_viewer.time.monotonic', return_value=20.):
            viewer.tick()
        self.assertEqual(viewer.clock.frame, 299)
        self.assertFalse(viewer.clock.playing)
        self.assertFalse(viewer.timer.isActive())
        self.assertFalse(viewer.guard_timer.isActive())
        self.assertIn('Source frame 301', viewer.position.text())
        viewer.scrub.setValue(149)
        self.assertEqual(viewer.clock.frame, 149)
        self.assertIn('Source frame 151', viewer.position.text())
        self.assertFalse(viewer.canvas.highlight_intersections)

    def test_policy_recheck_on_play_seek_and_live_guard_stops_revoked_preview(self):
        viewer = self.publish()
        count = self.catalog.call_count
        viewer.scrub.setValue(10)
        self.assertGreater(self.catalog.call_count, count)
        viewer.play.click()
        count = self.catalog.call_count
        viewer._guard_playing()
        self.assertGreater(self.catalog.call_count, count)
        self.catalog.side_effect = ProjectStorageError('Selected source permission changed')
        viewer._guard_playing()
        self.assertIsNone(viewer.clock)
        self.assertFalse(viewer.play.isEnabled())
        self.assertIsNone(self.window._target_action_result)
        self.assertIn('records are retained', self.window.log.toPlainText())
        self.assertTrue(self.result.binding_path.is_file())

    def test_catalog_coordination_with_same_selected_rows_keeps_preview(self):
        viewer = self.publish()
        self.context.database.write_bytes(b'unrelated catalog coordination changed size')
        (self.root/'unit-catalog.db-wal').write_bytes(b'unit WAL coordination')
        _changed(self.window, str(self.root), directory=True)
        self.assertIs(self.window._target_action_result, self.result)
        self.assertIsNotNone(viewer.clock)

    def test_shm_only_parent_notifications_do_not_recursively_query_but_wal_data_does(self):
        self.publish()
        wal = Path(str(self.context.database)+'-wal')
        shm = Path(str(self.context.database)+'-shm')
        wal.write_bytes(b'unit WAL data')
        shm.write_bytes(b'unit reader coordination')
        _changed(self.window, str(self.root), directory=True)
        self.assertIn(str(wal), self.window._target_action_watcher.files())
        count = self.catalog.call_count
        for index in range(20):
            shm.write_bytes(str(index).encode())
            _changed(self.window, str(self.root), directory=True)
        self.assertEqual(self.catalog.call_count, count, 'Own SHM metadata events must not trigger a query loop')
        _changed(self.window, str(wal), directory=False)
        self.assertGreater(self.catalog.call_count, count, 'A WAL data event must check the selected rows')
        self.catalog.side_effect = ProjectStorageError('Selected committed policy changed')
        _changed(self.window, str(wal), directory=False)
        self.assertIsNone(self.window._target_action_result)

    def test_late_catalog_change_between_watch_checks_rejects_adoption_but_retains_binding(self):
        self.catalog.side_effect = [None, ProjectStorageError('Selected SQL row changed before adoption')]
        with self.assertRaisesRegex(ProjectStorageError, 'SQL row'):
            self.publish()
        self.assertIsNone(self.window._target_action_result)
        self.assertTrue(self.result.binding_path.is_file())

    def test_cache_replacement_invalidates_even_while_old_bytes_are_in_memory(self):
        viewer = self.publish()
        old_cache = self.result.cache
        path = self.result.directory/'playback/motion_skin.bin'
        path.write_bytes(b'changed unit cache')
        _changed(self.window, str(path.parent), directory=True)
        self.assertIsNone(viewer.clock)
        self.assertFalse(viewer.play.isEnabled())
        self.assertEqual(old_cache.frame_count, 300)
        self.assertTrue(self.result.binding_path.exists())

    def test_parent_replacement_with_same_hardlinked_source_does_not_keep_preview(self):
        self.publish()
        source = self.root/'unit-source/unit-source.fbx'
        before = _stamp(source)
        previous = self.root/'unit-source-old'
        source.parent.rename(previous)
        source.parent.mkdir()
        os.link(previous/source.name, source)
        self.assertEqual(_stamp(source), before)
        _changed(self.window, str(self.root), directory=True)
        self.assertIsNone(self.window._target_action_result)

    def test_dirty_detached_or_other_project_context_clears_transport(self):
        self.publish()
        self.window.controller.dirty = True
        refresh_target_action_preview(self.window)
        self.assertIsNone(self.window._target_action_result)
        self.window.controller.dirty = False
        self.window.controller.store = SimpleNamespace(root=self.root, file=self.context.store.file)
        with self.assertRaises(ProjectConflict):
            self.publish()

    def test_explicit_binding_mismatch_or_watch_failure_cannot_adopt_result(self):
        with self.assertRaises(ValidationError):
            publish_target_action(self.window, self.context, self.review, self.result, selected_binding='0'*64)
        with patch('ucc.desktop.target_action_preview.QFileSystemWatcher.addPaths', return_value=['unit-failed-watch']):
            with self.assertRaisesRegex(ProjectStorageError, 'monitor'):
                self.publish()
        self.assertIsNone(self.window._target_action_result)
        self.assertTrue(self.result.binding_path.exists())

    def test_typed_result_with_omitted_proof_watch_is_rejected(self):
        omitted = self.result.directory/'playback/motion_skin.bin'
        invalid = replace(self.result, watched_inputs=tuple(
            row for row in self.result.watched_inputs if row[0] != omitted))
        with self.assertRaisesRegex(ValidationError, 'exact saved proof'):
            publish_target_action(self.window, self.context, self.review, invalid)
        self.assertTrue(self.result.binding_path.exists())

    def test_late_cancel_truthfully_retains_completed_record_without_adoption(self):
        w = self.window
        w.jobs.cancel_requested = True
        w._work_kind = 'target_action_prepare'
        w._target_action_context = self.context
        choice = TargetActionChoice('prepare', self.result.clip_id, None, Path('unit-map.json'), 'c'*64,
                                    'Unit test only', True)
        w._target_action_selection = (self.review, choice)
        finish_target_action(w, self.result)
        self.assertTrue(self.result.binding_path.exists())
        self.assertIsNone(w._target_action_result)
        message = w._error.call_args.args[0]
        self.assertIn('record retained', message)
        self.assertNotIn('rolled back', message)
        self.assertFalse(w.controller.dirty)

    def test_background_error_notes_remain_actionable(self):
        def failure():
            error = ProjectStorageError('Unit cancellation')
            error.add_note('Saved private record retained at unit-test location')
            raise error
        with self.assertRaisesRegex(ProjectStorageError, 'record retained'):
            _boundary(failure)

    def test_prepare_dispatch_binds_exact_context_source_policy_mapping_and_consent(self):
        from ucc.desktop.target_action_workflow import _chosen
        from ucc.library.provenance import LicensePolicy
        w = self.window
        w.jobs.busy = False
        w._target_action_context = self.context
        w._blender_executable = self.root/'unit-blender.exe'
        w._blender_executable.write_bytes(b'nonshipping executable fixture')
        review = SimpleNamespace(**vars(self.review), policy=LicensePolicy(
            'Unit author', 'Unit local rights', 'unit:test', reviewed=True, no_ai=True,
            local_preview_allowed=True))
        choice = TargetActionChoice('prepare', self.result.clip_id, None, self.root/'unit-map.json',
                                    'c'*64, 'Explicit private unit purpose', True)
        dialog = SimpleNamespace(choice=choice, review=review, deleteLater=Mock())
        def submit(window, kind, operation, **_kwargs):
            self.assertEqual(kind, 'target_action_prepare')
            operation(Event(), Mock())
        with patch('ucc.desktop.target_action_workflow._submit', side_effect=submit), \
                patch('ucc.desktop.target_action_workflow.bundled_worker_path', return_value=self.root/'unit-worker.py'), \
                patch('ucc.jobs.target_action.prepare_target_action', return_value=self.result) as prepare:
            _chosen(w, dialog)
        args = prepare.call_args.kwargs
        self.assertEqual(args['expected_project_sha256'], self.context.project_sha256)
        self.assertEqual(args['expected_source_binding_sha256'], self.review.source.source_binding_sha256)
        self.assertEqual(args['expected_catalog_record_sha256'], self.review.source.catalog_record_sha256)
        self.assertEqual(args['expected_source_sha256'], self.review.source.source_sha256)
        self.assertEqual(args['expected_mapping_sha256'], 'c'*64)
        self.assertEqual(args['purpose'], 'Explicit private unit purpose')
        self.assertIs(args['local_preview_confirmed'], True)
        self.assertIs(args['expected_policy'], review.policy)

    def test_saved_load_dispatch_requires_exact_sha_and_never_selects_blender(self):
        from ucc.desktop.target_action_workflow import _chosen
        w = self.window
        w.jobs.busy = False
        w._target_action_context = self.context
        choice = TargetActionChoice('load', self.result.clip_id, self.result.binding_sha256,
                                    None, None, '', True)
        dialog = SimpleNamespace(choice=choice, review=self.review, deleteLater=Mock())
        def submit(window, kind, operation, **_kwargs):
            self.assertEqual(kind, 'target_action_load')
            operation(Event(), Mock())
        with patch('ucc.desktop.target_action_workflow._submit', side_effect=submit), \
                patch('ucc.desktop.target_action_workflow.QFileDialog.getOpenFileName') as picker, \
                patch('ucc.desktop.target_action_workflow.bundled_worker_path') as worker, \
                patch('ucc.jobs.target_action.load_target_action', return_value=self.result) as load:
            _chosen(w, dialog)
        picker.assert_not_called()
        worker.assert_not_called()
        self.assertEqual(load.call_args.kwargs['binding_sha256'], self.result.binding_sha256)
        self.assertEqual(load.call_args.kwargs['expected_clip_id'], self.result.clip_id)
        self.assertEqual(load.call_args.kwargs['expected_catalog_record_sha256'], self.review.source.catalog_record_sha256)

    def test_real_menu_is_wired_and_readiness_rejects_busy_dirty_or_detached(self):
        from PySide6.QtGui import QAction
        from ucc.desktop.window import MainWindow
        from ucc.desktop.target_action_workflow import refresh_target_action
        with patch('ucc.desktop.target_action_workflow.start_target_action') as start:
            native = MainWindow()
            self.addCleanup(native.deleteLater)
            self.assertFalse(native.target_action_action.isEnabled())
            native.target_action_action.setEnabled(True)
            native.target_action_action.trigger()
            start.assert_called_once_with(native)
        w = self.window
        w.target_action_action = QAction(w)
        w.jobs.busy = False
        refresh_target_action(w)
        self.assertTrue(w.target_action_action.isEnabled())
        w.jobs.busy = True
        refresh_target_action(w)
        self.assertFalse(w.target_action_action.isEnabled())
        w.jobs.busy = False
        w.controller.dirty = True
        refresh_target_action(w)
        self.assertFalse(w.target_action_action.isEnabled())
        w.controller.dirty = False
        self.context.project.animations = ()
        refresh_target_action(w)
        self.assertFalse(w.target_action_action.isEnabled())

    def test_late_stale_context_after_commit_retains_saved_record(self):
        w = self.window
        w._work_kind = 'target_action_load'
        w._target_action_context = self.context
        choice = TargetActionChoice('load', self.result.clip_id, self.result.binding_sha256,
                                    None, None, '', True)
        w._target_action_selection = (self.review, choice)
        w.controller.dirty = True
        finish_target_action(w, self.result)
        self.assertTrue(self.result.binding_path.is_file())
        self.assertIsNone(w._target_action_result)
        self.assertIn('record retained', w._error.call_args.args[0])

    def test_closed_cancelled_source_review_does_not_show_operation_error(self):
        from ucc.desktop.target_action_workflow import target_action_error
        w = self.window
        w._work_kind = 'target_action_review'
        w.jobs.cancel_requested = True
        target_action_error(w, 'Unit review cancelled')
        w._error.assert_not_called()
        self.assertIn('review cancelled', w.log.toPlainText())

    def test_backend_failure_after_commit_reports_retained_record_and_loading_cancel(self):
        from PySide6.QtWidgets import QPushButton
        from ucc.desktop.target_action_workflow import _submit, target_action_error
        w = self.window
        w._work_kind = 'target_action_prepare'
        w._submit = Mock()
        def committed_then_failed(_cancel, progress):
            progress('RECORD_COMMITTED')
            error = ProjectStorageError('Unit post-save loading cancelled')
            error.add_note('Saved private target Action record retained at unit fixture')
            raise error
        _submit(w, 'target_action_prepare', committed_then_failed, progress=True)
        operation = w._submit.call_args.args[1]
        with self.assertRaises(ProjectStorageError) as failed:
            operation()
        self.assertTrue(w._target_action_record_committed)
        self.assertTrue(any(button.text() == 'Cancel preview loading'
            for button in w._target_action_progress_dialog.findChildren(QPushButton)))
        target_action_error(w, str(failed.exception))
        message = w._error.call_args.args[0]
        self.assertIn('record retained; preview loading did not complete', message)
        self.assertNotIn('rolled back', message)
        self.assertTrue(self.result.binding_path.is_file())

    def test_commit_note_survives_string_signal_even_without_progress_delivery(self):
        from ucc.desktop.target_action_workflow import SavedTargetActionRetained, target_action_error
        def failure():
            error = ProjectStorageError('Unit load failure after save')
            for index in range(12):
                error.add_note('Bounded unit diagnostic ' + str(index))
            error.add_note('Completed private target binding retained at unit fixture')
            raise error
        with self.assertRaises(SavedTargetActionRetained) as failed:
            _boundary(failure)
        self.window._work_kind = 'target_action_prepare'
        self.window._target_action_record_committed = False
        signal_text = type(failed.exception).__name__ + ': ' + str(failed.exception)
        target_action_error(self.window, signal_text)
        self.assertIn('record retained; preview loading did not complete', self.window._error.call_args.args[0])
        self.assertTrue(self.result.binding_path.is_file())


    def authored_mapping_dialog(self):
        from ucc.desktop.target_action_workflow import start_target_action
        from ucc.library.provenance import LicensePolicy

        window = self.window
        window.jobs.busy = False
        window._catalog_path = lambda: self.context.database
        window.animations = SimpleNamespace(references=SimpleNamespace(currentItem=lambda: None))
        with patch('ucc.desktop.target_action_workflow._review'):
            start_target_action(window)
        dialog = window._target_action_dialog
        self.assertFalse(dialog.save_authored_mapping.isEnabled())
        review = SimpleNamespace(**vars(self.review), policy=LicensePolicy(
            'Unit review', 'Private local rights', 'local://unit', reviewed=True, local_preview_allowed=True))
        dialog.set_review(review, ())
        return dialog, review

    def test_authored_mapping_export_then_ordinary_review_requires_fresh_consent(self):
        from PySide6.QtWidgets import QFileDialog, QInputDialog
        from ucc.desktop.target_action_workflow import IDLE_MAPPING_SAVE
        from ucc.jobs.authored_idle_target_map import PublishedAuthoredIdleTargetMapping

        dialog, review = self.authored_mapping_dialog()
        dialog.set_mapping(self.root/'old-map.json', 'a'*64)
        dialog.consent.click()
        dialog.purpose.setText('Unit private preview only')
        self.assertTrue(dialog.prepare.isEnabled())
        proof = self.root/'unit-idle-proof.json'
        with tempfile.TemporaryDirectory() as outside:
            parent = Path(outside).resolve()
            output = PublishedAuthoredIdleTargetMapping(parent/'new-map'/'idle-target-mapping.json', 'c'*64)
            with (patch.object(QFileDialog, 'getOpenFileName', return_value=(str(proof), '')),
                  patch.object(QFileDialog, 'getExistingDirectory', return_value=str(parent)),
                  patch.object(QInputDialog, 'getText', return_value=('new-map', True)),
                  patch('ucc.desktop.target_action_workflow._submit') as submit,
                  patch('ucc.jobs.authored_idle_target_map.publish_authored_idle_target_mapping', return_value=output) as publisher):
                dialog.save_authored_mapping.click()
                window, kind, operation = submit.call_args.args
                self.assertIs(window, self.window)
                self.assertEqual(kind, IDLE_MAPPING_SAVE)
                self.assertFalse(dialog.prepare.isEnabled())
                self.assertFalse(dialog.consent.isChecked())
                cancel = Event()
                result = operation(cancel, Mock())
                self.assertIs(publisher.call_args.kwargs['expected_review'], review)
                self.assertIs(publisher.call_args.kwargs['cancel'], cancel)
                self.assertEqual(publisher.call_args.kwargs['proof_file'], proof)
                self.assertEqual(publisher.call_args.kwargs['destination'].path, output.path.parent)
            self.window._work_kind = IDLE_MAPPING_SAVE
            finish_target_action(self.window, result)
            self.assertIsNone(dialog.mapping_sha256)
            self.assertIn(str(output.path), dialog.status.text())
            with (patch.object(QFileDialog, 'getOpenFileName', return_value=(str(output.path), '')),
                  patch('ucc.desktop.target_action_workflow._submit') as submit,
                  patch('ucc.desktop.target_action_workflow.read_native_profile', return_value=({}, output.sha256)) as reader):
                dialog.choose_mapping.click()
                _, kind, operation = submit.call_args.args
                self.assertEqual(kind, 'target_action_mapping')
                result = operation(Event(), Mock())
                reader.assert_called_once_with(output.path, review.source.source_sha256,
                                               review.source.snapshot_sha256, review.master_sha256)
            self.window._work_kind = 'target_action_mapping'
            finish_target_action(self.window, result)
            self.assertEqual(dialog.mapping_sha256, output.sha256)
            self.assertFalse(dialog.prepare.isEnabled())
            dialog.consent.click()
            self.assertTrue(dialog.prepare.isEnabled())

    def test_authored_mapping_chooser_cancel_or_stale_review_does_not_submit(self):
        from PySide6.QtWidgets import QFileDialog, QInputDialog

        dialog, _ = self.authored_mapping_dialog()
        dialog.set_mapping(self.root/'old-map.json', 'a'*64)
        with (patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')),
              patch('ucc.desktop.target_action_workflow._submit') as submit):
            dialog.save_authored_mapping.click()
            submit.assert_not_called()
        self.assertEqual(dialog.mapping_sha256, 'a'*64)

        def stale_while_choosing(*args, **kwargs):
            dialog.review = None
            return 'selected-new-folder', True

        with (patch.object(QFileDialog, 'getOpenFileName', return_value=(str(self.root/'proof.json'), '')),
              patch.object(QFileDialog, 'getExistingDirectory', return_value=str(self.root.parent)),
              patch.object(QInputDialog, 'getText', side_effect=stale_while_choosing),
              patch('ucc.desktop.target_action_workflow._submit') as submit):
            dialog.save_authored_mapping.click()
            submit.assert_not_called()
        self.assertIn('changed', dialog.status.text())

    def test_authored_mapping_job_has_actual_mainwindow_busy_dispatch(self):
        from ucc.desktop.target_action_workflow import IDLE_MAPPING_SAVE
        from ucc.desktop.window import MainWindow

        window = MainWindow(catalog_path=self.context.database)
        self.addCleanup(window.deleteLater)
        window._work_kind = IDLE_MAPPING_SAVE
        window._busy_changed(True)
        self.assertTrue(window.cancel_generation_action.isEnabled())
        self.assertIn('saving the exact target mapping', window.statusBar().currentMessage())
        window._busy_changed(False)


if __name__ == '__main__':
    unittest.main()
