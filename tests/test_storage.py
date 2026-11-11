import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.models import CharacterProject
from ucc.core.commands import CharacterSession
from ucc.core.storage import ProjectStore, PROJECT_FILE


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "Project"
        self.store = ProjectStore(self.root)

    def test_create_load_update_and_backup(self):
        source = CharacterProject.new("Lena")
        first = self.store.save(source)
        self.assertEqual(first.revision, 1)
        self.assertEqual(self.store.load(), first)
        session = CharacterSession(first)
        changed = session.set_morph("muscle", .7)
        latest = self.store.save(changed, expected_revision=first.revision)
        self.assertEqual(latest.revision, 2)
        self.assertEqual(len(self.store.list_backups()), 1)
        prior = json.loads(self.store.list_backups()[0].read_text())
        self.assertEqual(prior["revision"], 1)
        self.assertEqual(self.store.load(), latest)

    def test_reject_stale_or_bad_identity(self):
        first = self.store.save(CharacterProject.new("Lena"))
        session = CharacterSession(first)
        changed = session.rename("Revised")
        self.store.save(changed, expected_revision=1)
        with self.assertRaises(ProjectConflict):
            self.store.save(changed, expected_revision=1)
        other = replace(changed, project_id="other", revision=5)
        with self.assertRaises(ProjectConflict):
            self.store.save(other, expected_revision=2)

    def test_do_not_overwrite_future_schema(self):
        self.store.save(CharacterProject.new("Test"))
        path = self.root / PROJECT_FILE
        data = json.loads(path.read_text())
        data["schema_version"] = 999
        path.write_text(json.dumps(data))
        original_bytes = path.read_bytes()
        with self.assertRaises(ProjectStorageError):
            self.store.load()
        with self.assertRaises(ProjectStorageError):
            self.store.save(CharacterProject.new("Other"))
        self.assertEqual(path.read_bytes(), original_bytes)

    def test_atomic_replace_failure_retains_previous_revision(self):
        first = self.store.save(CharacterProject.new("Test"))
        old_bytes = (self.root / PROJECT_FILE).read_bytes()
        changed = CharacterSession(first).rename("new")
        real_replace = os.replace
        def fail_project_only(src, dst):
            if Path(dst).name == PROJECT_FILE:
                raise OSError("disk failure injected")
            return real_replace(src, dst)
        with patch("ucc.core.storage.os.replace", side_effect=fail_project_only):
            with self.assertRaises(ProjectStorageError):
                self.store.save(changed, expected_revision=1)
        self.assertEqual((self.root / PROJECT_FILE).read_bytes(), old_bytes)
        self.assertEqual(self.store.load().name, "Test")

    def test_refuse_symlink_history(self):
        if not hasattr(os, "symlink"):
            self.skipTest("Symlinks unsupported")
        self.root.mkdir()
        external = Path(self.tmp.name) / "external"
        external.mkdir()
        try:
            (self.root / "history").symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaises(ProjectStorageError):
            self.store.save(CharacterProject.new("Test"))

    def test_master_only_if_existing_blend_header(self):
        source = CharacterProject.new("Test")
        candidate = replace(source, geometry_state="generated_unverified", master_blend="master/human.blend")
        with self.assertRaises(ProjectStorageError):
            self.store.save(candidate)
        master = self.root / "master/human.blend"
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(b"this is not Blender" * 10)
        with self.assertRaises(ProjectStorageError):
            self.store.save(candidate)
        # Header alone is a structural format check, NOT evidence of real MPFB output.
        master.write_bytes(b"BLENDER" + b"\0" * 100)
        stored = self.store.save(candidate)
        self.assertEqual(stored.geometry_state, "generated_unverified")
        self.assertTrue(stored.export_readiness())

    def test_lock_existing_blocks_without_corruption(self):
        self.root.mkdir()
        (self.root / ".project.ucc.lock").write_text("another process")
        with patch("ucc.core.storage.time.sleep", return_value=None):
            # Do not wait full 3 seconds in the test: set the timer to expire.
            with patch("ucc.core.storage.time.monotonic", side_effect=[0, 4]):
                with self.assertRaises(ProjectConflict):
                    self.store.save(CharacterProject.new("Test"))
        self.assertFalse((self.root / PROJECT_FILE).exists())
