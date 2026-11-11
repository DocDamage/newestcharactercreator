"""Controller tests require no Qt or Blender; test actual metadata and failure paths."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from ucc.core.errors import ProjectConflict, ValidationError
from ucc.core.storage import PROJECT_FILE, ProjectStore
from ucc.desktop.controller import DesktopController


class DesktopControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "hero"

    def created(self):
        ctrl = DesktopController()
        ctrl.create(self.folder, "Hero")
        return ctrl

    def test_create_and_save_roundtrip(self):
        ctrl = self.created()
        self.assertEqual(ctrl.view().revision, 1)
        self.assertFalse(ctrl.dirty)
        self.assertEqual(ctrl.view().geometry_state, "not_generated")
        ctrl.set_morph("height", .75)
        self.assertTrue(ctrl.dirty)
        ctrl.save()
        opened = DesktopController()
        opened.open(self.folder)
        self.assertAlmostEqual(dict(opened.view().morphs)["height"], .75)
        self.assertEqual(opened.view().revision, 2)
        self.assertFalse(opened.dirty)

    def test_undo_redo_advances_revision_and_reloads(self):
        ctrl = self.created()
        ctrl.set_morph("muscle", .10)
        ctrl.set_morph("weight", .90)
        ctrl.undo()
        self.assertEqual(dict(ctrl.view().morphs)["weight"], .5)
        ctrl.redo()
        self.assertEqual(dict(ctrl.view().morphs)["weight"], .9)
        ctrl.save()
        self.assertEqual(ProjectStore(self.folder).load().revision, 5)

    def test_create_rejects_existing_user_data(self):
        self.folder.mkdir()
        (self.folder / "notes.txt").write_text("Important user data")
        with self.assertRaisesRegex(ValidationError, "not empty"):
            DesktopController().create(self.folder, "Hero")
        self.assertEqual((self.folder / "notes.txt").read_text(), "Important user data")

    def test_create_invalid_name_does_not_create_project(self):
        with self.assertRaises(ValidationError):
            DesktopController().create(self.folder, "  ")
        self.assertFalse((self.folder / PROJECT_FILE).exists())

    def test_new_controller_refuses_uncreated_master(self):
        ctrl = self.created()
        with self.assertRaisesRegex(ValidationError, "no staged"):
            ctrl.master_path()

    def test_open_missing_or_malformed_project_never_creates(self):
        ctrl = DesktopController()
        with self.assertRaises(FileNotFoundError):
            ctrl.open(self.folder)
        self.assertFalse(self.folder.exists())
        self.folder.mkdir()
        (self.folder / PROJECT_FILE).write_text("{bad", encoding="utf-8")
        with self.assertRaises(Exception):
            ctrl.open(self.folder)
        self.assertEqual((self.folder / PROJECT_FILE).read_text(), "{bad")

    def test_save_conflict_does_not_overwrite_outside_change(self):
        a = self.created()
        b = DesktopController()
        b.open(self.folder)
        a.rename("Hero 2")
        a.save()
        b.rename("Stale")
        with self.assertRaises(ProjectConflict):
            b.save()
        self.assertEqual(ProjectStore(self.folder).load().name, "Hero 2")
        self.assertTrue(b.dirty)

    def test_no_op_edits_do_not_enable_save(self):
        c = self.created()
        c.set_morph("height", .5)
        c.rename("Hero")
        self.assertFalse(c.dirty)
        self.assertEqual(c.save().revision, 1)

    def test_session_rejects_bad_morphs_and_preserves_revision(self):
        c = self.created()
        for name, value in [("unknown", .4), ("height", -1.0), ("weight", float("nan"))]:
            with self.subTest(name=name, value=value), self.assertRaises(ValidationError):
                c.set_morph(name, value)
        self.assertFalse(c.dirty)
        self.assertEqual(c.view().revision, 1)

    def test_failed_open_does_not_discard_current_character(self):
        c = self.created()
        c.rename("Unsaved")
        with self.assertRaises(FileNotFoundError):
            c.open(self.root / "missing")
        self.assertEqual(c.view().name, "Unsaved")
        self.assertTrue(c.dirty)

    def test_close_reload_keeps_earlier_backups(self):
        c = self.created()
        for i in range(3):
            c.set_morph("height", .1 * (i + 1))
            c.save()
        self.assertEqual(len(ProjectStore(self.folder).list_backups()), 3)
        self.assertEqual(DesktopController().open(self.folder).revision, 4)

    def test_save_without_project_fails(self):
        with self.assertRaises(ValidationError):
            DesktopController().save()


if __name__ == "__main__":
    unittest.main()
