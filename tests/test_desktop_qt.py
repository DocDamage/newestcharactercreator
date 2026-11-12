"""Actual offscreen PySide6 widgets; optional locally, mandatory on desktop CI."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ucc.desktop.controller import DesktopController
    from ucc.desktop.window import MainWindow
except ImportError as error:
    QApplication = None
    QT_IMPORT_ERROR = str(error)


@unittest.skipIf(QApplication is None and os.environ.get("UCC_REQUIRE_QT") != "1", "Optional PySide6 not installed")
class DesktopQtSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is None:
            raise RuntimeError(f"Qt smoke tests REQUIRED but PySide6 UI import failed: {QT_IMPORT_ERROR}")
        cls.app = QApplication.instance() or QApplication(["ucc-qt-tests"])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.controller = DesktopController()
        self.controller.create(Path(self.tmp.name) / "hero", "Testing Hero")
        self.window = MainWindow(self.controller)
        self.addCleanup(self.window.deleteLater)

    def test_real_qt_tabs_and_save_action(self):
        self.assertEqual(self.window.tabs.count(), 3)
        self.assertEqual(self.window.character.heading.text(), "Testing Hero")
        self.assertFalse(self.window.save_action.isEnabled())
        self.window.rename("Changed Hero")
        self.assertTrue(self.window.save_action.isEnabled())
        self.window.save_project()
        self.assertFalse(self.window.save_action.isEnabled())
        self.assertEqual(self.controller.view().name, "Changed Hero")

    def test_slider_and_advanced_anatomy_controls(self):
        self.assertFalse(self.window.character.advanced.isVisible())
        self.window.character.mode.setCurrentText("Advanced")
        # setVisible may be false until window shown, but the group isn't hidden by mode.
        self.assertFalse(self.window.character.advanced.isHidden())
        self.assertGreater(self.window.character.slot_table.rowCount(), 30)
        slider = self.window.character.sliders["muscle"]
        slider.setValue(650)
        slider.sliderReleased.emit()
        self.assertAlmostEqual(dict(self.controller.view().morphs)["muscle"], .65)
        self.window.undo()
        self.assertAlmostEqual(dict(self.controller.view().morphs)["muscle"], .5)

    def test_existing_master_refit_button_disabled_until_generated(self):
        self.assertFalse(self.window.character.apply_body.isEnabled())
        worker = Path(self.tmp.name) / "contract-worker"
        worker.mkdir()
        fake = worker / "fake.blend"
        fake.write_bytes(b"BLENDER" + b"contract-only" * 170)
        from ucc.core.master_versions import stage_unverified_master
        stage_unverified_master(
            self.controller.store, fake, authorized_source_root=worker,
        )
        self.controller.open(Path(self.tmp.name) / "hero")
        self.window.refresh_project()
        self.assertTrue(self.window.character.apply_body.isEnabled())

    def test_refit_prompt_shows_saved_values_and_dispatches_only_on_yes(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        self.controller.set_morph("muscle", .72)
        self.controller.save()
        self.window.refresh_project()
        fake_exe = Path(self.tmp.name) / "fake-blender-executable"
        fake_exe.write_text("unit-test-only")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes) as dialog:
            with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                       return_value=(str(fake_exe), "")):
                with patch.object(self.window, "_submit") as submit:
                    self.window.character.apply_body.click()
        message = dialog.call_args.args[2]
        self.assertIn("muscle=0.720", message)
        self.assertIn("COPY", message)
        submit.assert_called_once()
        args, kwargs = submit.call_args
        self.assertEqual(args[0], "body_refit")
        self.assertFalse(kwargs["cancel"].is_set())

    def test_dirty_project_blocks_existing_master_refit(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        self.controller.set_morph("weight", .82)
        with (patch.object(self.window, "_error") as error,
              patch.object(self.window, "_submit") as submit):
            self.window.apply_saved_body()
        self.assertIn("Save all body", error.call_args.args[0])
        submit.assert_not_called()

    def test_rig_pose_check_available_only_when_master_exists(self):
        self.assertFalse(self.window.character.check_rig_pose.isEnabled())
        self.test_existing_master_refit_button_disabled_until_generated()
        self.assertTrue(self.window.character.check_rig_pose.isEnabled())
        blender = Path(self.tmp.name) / "test-blender-ignored"
        blender.write_bytes(b"not an actual executable")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(blender), "")):
            with patch.object(self.window, "_submit") as submit:
                self.window.character.check_rig_pose.click()
        submit.assert_called_once()
        args, options = submit.call_args
        self.assertEqual(args[0], "skin_pose_check")
        self.assertTrue(callable(args[1]))
        self.assertFalse(options["cancel"].is_set())

    def test_rig_pose_result_reports_measurement_but_does_not_modify_revision(self):
        from ucc.jobs.pose_diagnostic import SavedMasterPoseCheck
        self.test_existing_master_refit_button_disabled_until_generated()
        current = self.controller.require_project()
        result = SavedMasterPoseCheck(
            current.project_id, current.revision, current.master_blend,
            "a" * 64,
            {
                "selected_deform_bone": "UpperArm.L",
                "rotation_degrees": 20.0,
                "rotation_axis_index": 0,
                "moved_vertex_count": 450,
                "evaluated_vertex_count": 19158,
                "max_vertex_displacement_local": .03,
            },
            ("mock-first", "mock-second"),
        )
        self.window._work_kind = "skin_pose_check"
        self.window._job_success(result)
        self.assertIn("450", self.window.log.toPlainText())
        self.assertIn("NOT an animation clip", self.window.log.toPlainText())
        self.assertEqual(self.controller.require_project().revision, current.revision)
        self.assertEqual(self.controller.require_project().master_blend, current.master_blend)

    def test_rig_pose_check_requires_saved_metadata(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        self.controller.set_morph("muscle", .81)
        with patch.object(self.window, "_error") as error:
            with patch.object(self.window, "_submit") as submit:
                self.window.verify_saved_rig_pose()
        self.assertIn("Save metadata", error.call_args.args[0])
        submit.assert_not_called()

    def test_keyframed_timeline_action_requires_saved_master_and_explicit_blender(self):
        self.assertFalse(self.window.character.test_timeline.isEnabled())
        self.test_existing_master_refit_button_disabled_until_generated()
        self.assertTrue(self.window.character.test_timeline.isEnabled())
        executable = Path(self.tmp.name) / "fake-test-blender"
        executable.write_bytes(b"unit-test-only-not-executed")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(executable), "")):
            with patch.object(self.window, "_submit") as submit:
                self.window.character.test_timeline.click()
        submit.assert_called_once()
        args, options = submit.call_args
        self.assertEqual(args[0], "keyframed_timeline")
        self.assertTrue(callable(args[1]))
        self.assertFalse(options["cancel"].is_set())

    def test_keyframed_timeline_reports_five_frames_but_no_user_clip_claim(self):
        from ucc.jobs.timeline_diagnostic import SavedTimelineDiagnostic
        self.test_existing_master_refit_button_disabled_until_generated()
        project = self.controller.require_project()
        samples = [
            {"frame": frame, "moved_vertices": move,
             "max_displacement_local": .04 if move else 0.0}
            for frame, move in ((1, 0), (7, 200), (13, 450), (19, 200), (25, 0))
        ]
        result = SavedTimelineDiagnostic(
            project.project_id, project.revision, project.master_blend,
            "a" * 64,
            {"sampled_frames": samples, "selected_deform_bone": "head"},
            ("first-test-job", "second-test-job"),
        )
        self.window._work_kind = "keyframed_timeline"
        self.window._job_success(result)
        log = self.window.log.toPlainText()
        self.assertIn("KEYFRAMED TIMELINE", log)
        self.assertIn("Frame 13", log)
        self.assertIn("NOT your own imported animation clip", log)
        self.assertEqual(self.controller.require_project().revision, project.revision)

    def test_keyframed_timeline_blocks_unsaved_metadata(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        self.controller.set_morph("muscle", .63)
        with patch.object(self.window, "_error") as error:
            with patch.object(self.window, "_submit") as submit:
                self.window.verify_saved_timeline()
        self.assertIn("Save metadata", error.call_args.args[0])
        submit.assert_not_called()

    def test_local_bvh_preview_requires_license_review_before_running(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        clip = Path(self.tmp.name) / "original-preview.bvh"
        clip.write_text("test-only UI path, worker not launched", encoding="utf-8")
        pane = self.window.animations
        pane.selected.setText(str(clip))
        pane.provider.setText("original")
        pane.license.setText("original self-authored")
        pane.uri.setText("local-original://unit-test")
        with (patch.object(self.window, "_error") as error,
              patch.object(self.window, "_submit") as submit):
            self.window.test_selected_bvh(
                str(clip), pane.provider.text(), pane.license.text(),
                pane.uri.text(), False,
            )
        self.assertIn("reviewed-rights", error.call_args.args[0])
        submit.assert_not_called()
        pane.local_preview_review.setChecked(True)
        blender = Path(self.tmp.name) / "test-blender-not-executed"
        blender.write_bytes(b"mock-binary")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(blender), "")):
            with patch.object(self.window, "_submit") as submit:
                pane.test_local_bvh.click()
        submit.assert_called_once()
        args, options = submit.call_args
        self.assertEqual(args[0], "local_bvh_motion")
        self.assertFalse(options["cancel"].is_set())
        pane.uri.setText("changed-source-uri")
        self.assertFalse(pane.local_preview_review.isChecked())

    def test_local_bvh_result_reports_source_motion_without_retarget_claim(self):
        from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck
        self.test_existing_master_refit_button_disabled_until_generated()
        snapshot = self.controller.require_project()
        evidence = {
            "source_bone": "head", "target_bone": "head",
            "source_frame_count": 25, "distinct_geometry_states": 3,
            "sampled_frames": [
                {"frame": i, "moved_vertices": v, "max_displacement_local": .03}
                for i, v in ((1, 0), (7, 100), (13, 300), (19, 100), (25, 0))
            ],
        }
        result = LocalBvhClipCheck(
            snapshot.project_id, snapshot.revision, snapshot.master_blend,
            "a" * 64, "b" * 64, "Original Motion", evidence,
            ("first", "second"),
        )
        self.window._work_kind = "local_bvh_motion"
        self.window._job_success(result)
        log = self.window.log.toPlainText()
        self.assertIn("REAL USER-SELECTED BVH", log)
        self.assertIn("Frame 13", log)
        self.assertIn("NOT certified retargeting", log)
        self.assertEqual(self.controller.require_project().revision, snapshot.revision)

    def test_two_bone_bvh_requires_explicit_axis_and_current_license_review(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        clip = Path(self.tmp.name) / "unit-only-two-bone.bvh"
        clip.write_text("UI-only unit test, never passed to Blender", encoding="utf-8")
        pane = self.window.animations
        pane.selected.setText(str(clip))
        pane.provider.setText("original")
        pane.license.setText("self-authored")
        pane.uri.setText("original-local://two-bone-unit")
        pane.local_preview_review.setChecked(True)
        self.assertEqual(pane.source_axes.currentData(), "")
        with (patch.object(self.window, "_error") as error,
              patch.object(self.window, "_submit") as submit):
            pane.test_multi_bvh.click()
        self.assertIn("up-axis", error.call_args.args[0])
        submit.assert_not_called()
        pane.source_axes.setCurrentIndex(1)
        pane.local_preview_review.setChecked(True)
        blender = Path(self.tmp.name) / "fake-blender-not-started"
        blender.write_bytes(b"unit-test")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(blender), "")):
            with patch.object(self.window, "_submit") as submit:
                pane.test_multi_bvh.click()
        args, kwargs = submit.call_args
        self.assertEqual(args[0], "multi_bvh_chain")
        self.assertFalse(kwargs["cancel"].is_set())
        pane.selected.setText(str(clip.with_name("different.bvh")))
        self.assertFalse(pane.local_preview_review.isChecked())

    def test_two_bone_bvh_result_discloses_rest_axis_vs_uncalibrated_bone_roll(self):
        from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck
        self.test_existing_master_refit_button_disabled_until_generated()
        project = self.controller.require_project()
        report = {
            "axis_profile": "Y_UP_TO_Z_UP", "mapped_bone_count": 2,
            "rest_scale_consistency_verified": False,
            "mapped_bones": [
                {"source": "neck03", "target": "neck03",
                 "parent": None, "rest_alignment_cos": None},
                {"source": "head", "target": "head",
                 "parent": "neck03", "rest_alignment_cos": .97},
            ],
            "per_bone_deformation": [
                {"bone": "neck03", "moved_vertices": 200},
                {"bone": "head", "moved_vertices": 500},
            ],
            "source_frame_count": 25,
            "distinct_geometry_states": 5,
            "sampled_frames": [
                {"frame": frame, "moved_vertices": moved,
                 "max_displacement_local": .03 if moved else 0}
                for frame, moved in ((1, 0), (7, 200), (13, 600), (19, 200), (25, 0))
            ],
        }
        outcome = LocalBvhClipCheck(
            project.project_id, project.revision, project.master_blend,
            "a" * 64, "b" * 64, "Unit source", report, ("first", "second"),
        )
        self.window._work_kind = "multi_bvh_chain"
        self.window._job_success(outcome)
        message = self.window.log.toPlainText()
        self.assertIn("2–4 BONE BVH SOURCE CHAIN", message)
        self.assertIn("neck03 → neck03", message)
        self.assertIn("head → head", message)
        self.assertIn("rest DIRECTION", message)
        self.assertIn("NOT calibrated", message)
        self.assertIn("NOT certified retargeting", message)
        self.assertEqual(self.controller.require_project().revision, project.revision)

    def test_calibrated_bvh_requires_explicit_axes_rights_and_saved_master(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        pane = self.window.animations
        source = Path(self.tmp.name) / "unit-calibrated-motion.bvh"
        source.write_text("UI unit fixture; worker never starts", encoding="utf-8")
        pane.selected.setText(str(source))
        pane.provider.setText("original")
        pane.license.setText("original user-authored")
        pane.uri.setText("local-original://test-axes")
        pane.local_preview_review.setChecked(True)
        self.assertEqual(pane.source_axes.currentData(), "")
        with (patch.object(self.window, "_error") as error,
              patch.object(self.window, "_submit") as submit):
            pane.test_calibrated_bvh.click()
        self.assertIn("up-axis", error.call_args.args[0])
        submit.assert_not_called()
        pane.source_axes.setCurrentIndex(1)
        pane.local_preview_review.setChecked(True)
        blender = Path(self.tmp.name) / "fake-blender-unused"
        blender.write_bytes(b"not-executed")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(blender), "")):
            with patch.object(self.window, "_submit") as submit:
                pane.test_calibrated_bvh.click()
        submit.assert_called_once()
        args, kwargs = submit.call_args
        self.assertEqual(args[0], "calibrated_bvh_chain")
        self.assertFalse(kwargs["cancel"].is_set())
        pane.provider.setText("changed provider")
        self.assertFalse(pane.local_preview_review.isChecked())

    def test_calibration_result_discloses_two_rest_landmarks_and_unverified_retarget(self):
        from ucc.jobs.bvh_clip_diagnostic import LocalBvhClipCheck
        self.test_existing_master_refit_button_disabled_until_generated()
        character = self.controller.require_project()
        data = {
            "axis_profile": "Y_UP_TO_Z_UP",
            "rest_landmark_count": 2,
            "max_rest_residual_degrees": 0.3,
            "mapped_bone_count": 2,
            "mapped_bones": [
                {"source": "neck03", "target": "neck03", "parent": None},
                {"source": "head", "target": "head", "parent": "neck03"},
            ],
            "per_bone_deformation": [
                {"bone": "neck03", "moved_vertices": 300},
                {"bone": "head", "moved_vertices": 500},
            ],
            "source_frame_count": 25,
            "distinct_geometry_states": 3,
            "sampled_frames": [
                {"frame": frame, "moved_vertices": count,
                 "max_displacement_local": .04 if count else 0.0}
                for frame, count in (
                    (1, 0), (7, 300), (13, 900), (19, 300), (25, 0)
                )
            ],
        }
        output = LocalBvhClipCheck(
            character.project_id, character.revision, character.master_blend,
            "f" * 64, "e" * 64, "Local unit source", data,
            ("blender-A", "blender-B"),
        )
        self.window._work_kind = "calibrated_bvh_chain"
        self.window._job_success(output)
        message = self.window.log.toPlainText()
        self.assertIn("REST-SPACE-CALIBRATED", message)
        self.assertIn("independent rest landmarks: 2", message)
        self.assertIn("neck03 → neck03", message)
        self.assertIn("NOT independently certified", message)
        self.assertIn("NOT certified retargeting", message)
        self.assertEqual(self.controller.require_project().revision, character.revision)

    def test_generate_action_requires_explicit_blender_selection(self):
        self.assertTrue(self.window.character.generate.isEnabled())
        exe = Path(self.tmp.name) / "selected-blender"
        exe.write_bytes(b"fake-test-executable-not-invoked")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                       return_value=(str(exe), "")):
                with patch.object(self.window, "_submit") as submit:
                    self.window.character.generate.click()
        submit.assert_called_once()
        args, kwargs = submit.call_args
        self.assertEqual(args[0], "generate_humanoid")
        self.assertTrue(callable(args[1]))
        self.assertFalse(kwargs["cancel"].is_set())

    def test_dialog_shows_saved_body_controls_not_unsaved_slider_values(self):
        self.controller.set_morph("height", .8)
        self.controller.set_morph("weight", .2)
        self.controller.save()
        self.window.refresh_project()
        exe = Path(self.tmp.name) / "test-selected-blender"
        exe.write_bytes(b"test fake executable not launched")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.No) as dialog:
            with patch.object(self.window, "_submit") as submit:
                self.window.generate_humanoid()
        submit.assert_not_called()
        message = dialog.call_args.args[2]
        self.assertIn("height=0.800", message)
        self.assertIn("weight=0.200", message)
        self.assertIn("new Blender master", message)

    def test_dirty_metadata_blocks_generation_without_a_worker(self):
        self.controller.rename("Unsaved hero")
        with patch.object(self.window, "_error") as error:
            with patch.object(self.window, "_submit") as submit:
                self.window.generate_humanoid()
        error.assert_called_once()
        self.assertIn("Save all metadata", error.call_args.args[0])
        submit.assert_not_called()

    def test_busy_blender_generation_locks_all_project_edits(self):
        self.window._work_kind = "generate_humanoid"
        self.window._busy_changed(True)
        self.assertFalse(self.window.character.generate.isEnabled())
        self.assertFalse(self.window.new_action.isEnabled())
        self.assertFalse(self.window.open_action.isEnabled())
        self.assertTrue(self.window.cancel_generation_action.isEnabled())
        self.window._busy_changed(False)
        self.assertTrue(self.window.character.generate.isEnabled())
        self.assertTrue(self.window.new_action.isEnabled())
        self.assertFalse(self.window.cancel_generation_action.isEnabled())

    def test_genuine_workflow_result_refreshes_project_but_does_not_certify(self):
        # Structural unit-test bytes; neither this test nor this output is MPFB proof.
        from ucc.core.master_versions import stage_unverified_master
        from ucc.jobs.humanoid_generation import HumanoidGeneration
        worker = Path(self.tmp.name) / "fake-worker-results"
        worker.mkdir()
        master = worker / "generated_human.blend"
        master.write_bytes(b"BLENDER" + b"unit-test-only" * 100)
        result = stage_unverified_master(
            self.controller.store, master, authorized_source_root=worker
        )
        outcome = HumanoidGeneration(
            result, {
                "created_vertex_count": 2000, "reopened_bone_count": 60,
                "macro_parameters_observed": {"height": .5, "muscle": .5, "weight": .5},
                "macro_evaluated_sha256": "a" * 64,
            },
            "unit-create", "unit-inspect",
        )
        self.window._work_kind = "generate_humanoid"
        self.window._job_success(outcome)
        self.assertEqual(self.window.controller.view().geometry_state, "generated_unverified")
        self.assertTrue(self.window.character.open_master.isEnabled())
        self.assertIn("MPFB evaluated shape", self.window.log.toPlainText())
        self.assertIn("height=0.500", self.window.log.toPlainText())
        self.assertIn("NOT live morph editing", self.window.log.toPlainText())
        self.assertIn("Master geometry has not passed", self.window.character.blockers.toPlainText())

    def test_explicit_mapped_bvh_button_enforces_reviewed_pairs_and_axis(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        pane = self.window.animations
        clip = Path(self.tmp.name) / "reviewed-names.bvh"
        clip.write_text("UI-only, not executed", encoding="utf-8")
        pane.selected.setText(str(clip))
        pane.provider.setText("original")
        pane.license.setText("author retained rights")
        pane.uri.setText("local-original://mapped-unit")
        pane.manual_bone_pairs.setPlainText(
            "SrcNeck02 -> neck02\nSrcNeck03 -> neck03\nSrcHead -> head"
        )
        pane.local_preview_review.setChecked(True)
        with (patch.object(self.window, "_error") as error,
              patch.object(self.window, "_submit") as submit):
            pane.test_reviewed_bvh.click()
        self.assertIn("up-axis", error.call_args.args[0])
        submit.assert_not_called()
        pane.source_axes.setCurrentIndex(1)
        pane.local_preview_review.setChecked(True)
        blender = Path(self.tmp.name) / "fake-blender-not-running"
        blender.write_bytes(b"UNIT_ONLY")
        with patch("ucc.desktop.window.QFileDialog.getOpenFileName",
                   return_value=(str(blender), "")):
            with patch.object(self.window, "_submit") as submit:
                pane.test_reviewed_bvh.click()
        self.assertEqual(submit.call_args.args[0], "reviewed_bvh_chain")
        pane.manual_bone_pairs.setPlainText("SrcNeck02 -> neck02")
        self.assertFalse(pane.local_preview_review.isChecked())

    def test_branching_map_editor_preserves_64_rows_and_clears_rights_on_edit(self):
        from ucc.animations.review_mapping import parse_review_mapping
        pane = self.window.animations
        text = "\n".join(f"Source{i} -> Target{i}" for i in range(64))
        pane.local_preview_review.setChecked(True)
        pane.manual_bone_pairs.setPlainText(text)
        self.assertFalse(pane.local_preview_review.isChecked())
        self.assertIn("branching", pane.manual_bone_pairs.toolTip())
        received = []
        pane.reviewed_bvh_requested.connect(lambda *args: received.append(args))
        with patch.object(self.window, "_error"):
            pane.test_reviewed_bvh.click()
        self.assertEqual(len(parse_review_mapping(received[0][6])), 64)
        self.assertFalse(received[0][4])

    def test_audited_render_requires_descriptor_before_dispatch(self):
        with patch.object(self.window, "_error") as error, patch.object(self.window, "test_selected_bvh") as submit:
            self.window.test_reviewed_bvh("", "", "", "", False, "Y_UP_TO_Z_UP", "A -> B", "", True)
        error.assert_called_once()
        self.assertIn("SHA-bound", error.call_args.args[0])
        submit.assert_not_called()

    def test_fbx_inspection_requires_rights_before_prompt_or_launch(self):
        with patch.object(self.window,"_error") as error, patch.object(self.window,"_submit") as submit:
            self.window.inspect_animation("selected.fbx")
        self.assertIn("local Blender rights",error.call_args.args[0])
        submit.assert_not_called()

    def test_fbx_inspection_dispatches_private_cancelable_job_and_reports_limits(self):
        pane=self.window.animations
        source=Path(self.tmp.name)/"UI_ONLY_NOT_REAL.fbx";source.write_bytes(b"UI_ONLY")
        blender=Path(self.tmp.name)/"blender-not-running";blender.write_bytes(b"UI_ONLY")
        self.window._blender_executable=blender
        pane.provider.setText("original");pane.license.setText("Original retained rights")
        pane.uri.setText("local-original://fixture");pane.local_preview_review.setChecked(True)
        with patch("ucc.jobs.fbx_intake.inspect_selected_fbx") as service,patch.object(self.window,"_submit") as submit:
            self.window.inspect_animation(str(source))
            submit.call_args.args[1]()
        self.assertEqual(submit.call_args.args[0],"fbx_intake")
        self.assertEqual(service.call_args.args[0],source)
        self.assertIs(service.call_args.kwargs["cancel"],submit.call_args.kwargs["cancel"])
        self.assertTrue(service.call_args.kwargs["permission"].local_preview_allowed)
        self.window._work_kind="fbx_intake"
        self.window._job_success({"bone_count":76,"root_count":3,"first_frame":1,"last_frame":300,
                                  "fps":30.,"private_snapshot":"PRIVATE LOCAL TEST PATH"})
        self.assertIn("No animation was applied",self.window.log.toPlainText())
        self.assertIn("300",self.window.log.toPlainText())

    def test_native_body_requires_license_and_dispatches_auto_mapping_with_cancel(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        pane = self.window.animations
        source = Path(self.tmp.name) / "ui-only.fbx"
        source.write_bytes(b"UNIT_ONLY_NOT_IMPORTED")
        executable = Path(self.tmp.name) / "unit-blender"
        executable.write_bytes(b"UNIT_ONLY_NOT_EXECUTED")
        self.window._blender_executable = executable
        pane.selected.setText(str(source))
        with patch.object(self.window, "_error") as error, patch.object(self.window, "_submit") as submit:
            pane.test_native_body.click()
        self.assertIn("rights", error.call_args.args[0])
        submit.assert_not_called()
        pane.provider.setText("original")
        pane.license.setText("Original retained rights")
        pane.uri.setText("local-original://unit")
        pane.local_preview_review.setChecked(True)
        with patch.object(self.window, "_submit") as submit, patch("ucc.desktop.native_body.preview_native_body") as service:
            pane.test_native_body.click()
            submit.call_args.args[1]()
        self.assertEqual(submit.call_args.args[0], "native_body")
        self.assertIsNone(service.call_args.kwargs["mapping_profile"])
        self.assertIs(service.call_args.kwargs["cancel"], submit.call_args.kwargs["cancel"])
        self.assertTrue(service.call_args.kwargs["permission"].no_ai)
        for kind in ("native_body", "native_playback", "fbx_intake"):
            self.window._work_kind = kind
            self.window._busy_changed(True)
            self.assertTrue(self.window.cancel_generation_action.isEnabled())
            self.assertFalse(self.window.character.isEnabled())
            self.window._busy_changed(False)
            self.assertFalse(self.window.cancel_generation_action.isEnabled())

    def test_cached_motion_button_requires_current_preview_and_dispatches_with_cancel(self):
        from types import SimpleNamespace
        from ucc.desktop.native_body import start_native_playback
        pane=self.window.animations
        self.assertFalse(pane.load_native_motion.isEnabled())
        with patch.object(self.window,"_error") as error,patch.object(self.window,"_submit") as submit:
            start_native_playback(self.window)
        self.assertIn("preview",error.call_args.args[0]);submit.assert_not_called()
        pane.provider.setText("original");pane.license.setText("Original retained rights");pane.uri.setText("original-unit://clip")
        pane.local_preview_review.setChecked(True)
        executable=Path(self.tmp.name)/"unit-not-executed";executable.write_bytes(b"UNIT_ONLY")
        self.window._blender_executable=executable
        self.window._native_review=SimpleNamespace()
        pane.load_native_motion.setEnabled(True)
        with patch.object(self.window,"_submit") as submit,patch("ucc.desktop.native_body.prepare_native_playback") as prepare:
            pane.load_native_motion.click();submit.call_args.args[1]()
        self.assertEqual(submit.call_args.args[0],"native_playback")
        self.assertIs(prepare.call_args.kwargs["cancel"],submit.call_args.kwargs["cancel"])
        self.assertTrue(prepare.call_args.kwargs["permission"].no_ai)

    def test_dirty_character_and_license_changes_clear_cached_motion(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        self.window.motion_viewer=Mock();self.window.motion_dock=Mock()
        project=self.controller.require_project()
        self.window._native_review=SimpleNamespace(project_id=project.project_id,revision=project.revision)
        self.window.animations.load_native_motion.setEnabled(True)
        self.window.rename("Dirty character")
        self.assertIsNone(self.window._native_review);self.window.motion_viewer.clear.assert_called()
        self.assertFalse(self.window.animations.load_native_motion.isEnabled())
        for field in (self.window.animations.provider,self.window.animations.license,self.window.animations.uri):
            self.window._native_review=object();self.window.animations.load_native_motion.setEnabled(True)
            field.setText("new licence details")
            self.assertIsNone(self.window._native_review);self.assertFalse(self.window.animations.load_native_motion.isEnabled())

    def test_native_results_clear_when_source_or_mapping_changes(self):
        pane = self.window.animations
        for field in (pane.selected, pane.native_body_profile):
            self.window._native_review = object()
            pane.open_native_animation.setEnabled(True)
            pane.open_native_renders.setEnabled(True)
            pane.local_preview_review.setChecked(True)
            field.setText("changed-input")
            self.assertIsNone(self.window._native_review)
            self.assertFalse(pane.open_native_animation.isEnabled())
            self.assertFalse(pane.open_native_renders.isEnabled())
            self.assertFalse(pane.local_preview_review.isChecked())

    def test_native_hip_anchor_result_discloses_error_and_keeps_quality_unverified(self):
        from types import SimpleNamespace
        from fixtures.native_body_contract import contract
        from ucc.desktop.native_body import native_result_text
        data=contract()[0]
        data.update(root_motion_policy="SOURCE_HIP_MIDPOINT_V1",hip_anchor={"max_residual_world":1e-7})
        text=native_result_text(SimpleNamespace(evidence=data))
        self.assertIn("Hip movement matches",text)
        self.assertIn("0.0001 mm",text)
        self.assertIn("foot-contact quality and engine import remain unverified",text)

    def test_native_corrective_result_discloses_private_smoothing_and_actual_reopen(self):
        from types import SimpleNamespace
        from fixtures.native_body_contract import contract
        from ucc.desktop.native_body import native_result_text
        data=contract()[0];data["skin_deformation_policy"]="BOUND_CORRECTIVE_SMOOTH_V1"
        text=native_result_text(SimpleNamespace(evidence=data,private_reopen_job_id="unit-third-job"))
        self.assertIn("Bound joint smoothing applied",text)
        self.assertIn("third Blender process",text)
        self.assertIn("foot-contact quality and engine import remain unverified",text)

    def test_native_open_refuses_missing_or_changed_review_artifacts(self):
        from types import SimpleNamespace
        from ucc.desktop.native_body import open_native_result
        self.window._native_review = SimpleNamespace(
            private_visual_review_blend=str(Path(self.tmp.name) / "review_motion.blend"),
            worker_report={"visual_review_blend": {"name": "review_motion.blend", "bytes": 12345, "sha256": "a"*64}})
        with patch.object(self.window, "_error") as error, patch("ucc.desktop.native_body.subprocess.Popen") as launch:
            open_native_result(self.window)
        self.assertIn("Missing", error.call_args.args[0])
        launch.assert_not_called()

    def test_tools_are_real_and_cannot_claim_geometry(self):
        self.assertIn("PNG", self.window.tools.pack.text())
        self.assertFalse(self.window.character.open_master.isEnabled())
        self.assertIn("No live updates", self.window.character.note.text())

    def test_rest_profile_picker_clears_rights_and_dispatches_selected_path(self):
        self.test_existing_master_refit_button_disabled_until_generated()
        pane = self.window.animations
        rest = Path(self.tmp.name) / "source-rest.json"
        rest.write_text("{}", encoding="utf-8")  # UI wiring only; coordinator validates contents.
        pane.local_preview_review.setChecked(True)
        with patch("ucc.desktop.panes.QFileDialog.getOpenFileName", return_value=(str(rest), "")):
            pane.choose_rest_profile.click()
        self.assertEqual(pane.source_rest_profile.text(), str(rest))
        self.assertFalse(pane.local_preview_review.isChecked())
        self.assertIn("source rest-frame JSON", pane.source_rest_profile.placeholderText())
        clip = Path(self.tmp.name) / "ui-only.bvh"
        clip.write_text("Not executed", encoding="utf-8")
        pane.selected.setText(str(clip))
        pane.provider.setText("original")
        pane.license.setText("original retained rights")
        pane.uri.setText("local-original://unit")
        pane.source_axes.setCurrentIndex(1)
        pane.manual_bone_pairs.setPlainText("A -> neck02\nB -> neck03\nC -> head")
        pane.local_preview_review.setChecked(True)
        pane.audit_and_render.setChecked(True)
        self.assertFalse(pane.local_preview_review.isChecked())
        pane.local_preview_review.setChecked(True)
        blender = Path(self.tmp.name) / "blender-unit-not-running"
        blender.write_bytes(b"TEST_ONLY")
        self.window._blender_executable = blender
        with patch.object(self.window, "_submit") as submit:
            pane.test_reviewed_bvh.click()
        with patch("ucc.desktop.window.test_local_bvh_from_desktop") as service:
            submit.call_args.args[1]()
        self.assertEqual(service.call_args.kwargs["source_rest_profile"], rest)
        self.assertTrue(service.call_args.kwargs["audit_source_frames"])
        self.assertTrue(service.call_args.kwargs["render_private_frames"])
        pane.source_axes.setCurrentIndex(2)
        self.assertFalse(pane.local_preview_review.isChecked())
        self.assertIn("local", self.window.tools.ai.text())


if __name__ == "__main__":
    unittest.main()
