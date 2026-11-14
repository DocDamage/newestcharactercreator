"""Tests for non-destructive staging of Blender bytes (never a Blender test)."""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import contextlib
import io
import json
import tempfile
from threading import Event
import unittest

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.storage import ProjectStore
from ucc.core.master_versions import stage_unverified_master
from ucc.cli import main


class MasterRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.jobs = self.root / "worker" / "jobs"
        self.jobs.mkdir(parents=True)
        self.store = ProjectStore(self.root / "project")
        self.initial = self.store.save(CharacterProject.new("One Human"))
        self.src = self.jobs / "model.blend"
        # Synthetic test-only bytes: NOT a real Blender file, not live MPFB proof.
        self.data = b"BLENDER" + b"synthetic-structural-test-only" * 10
        self.src.write_bytes(self.data)

    def stage(self, **kwargs):
        return stage_unverified_master(self.store, self.src, authorized_source_root=self.jobs, **kwargs)

    def test_content_addressed_revision_and_pointer(self):
        result = self.stage()
        self.assertEqual(result.sha256, sha256(self.data).hexdigest())
        self.assertEqual(result.project.geometry_state, "generated_unverified")
        self.assertIsNone(result.project.rig_profile)
        self.assertEqual(result.project.revision, self.initial.revision + 1)
        self.assertEqual(result.master_path.read_bytes(), self.data)
        self.assertEqual(self.store.load().master_blend, f"master/versions/{result.sha256}.blend")
        self.assertFalse(result.reused)

    def test_identical_content_reuses_immutable_revision(self):
        first = self.stage()
        second = self.stage()
        self.assertEqual(first.master_path, second.master_path)
        self.assertTrue(second.reused)
        self.assertEqual(second.project.revision, first.project.revision + 1)

    def test_explicit_part_intent_commits_with_pointer_and_failure_preserves_both(self):
        part = PartInstance('unit-part', 'unit-asset', 'hand.L')
        def fail():
            raise RuntimeError('forced failure before atomic pointer/parts update')
        with self.assertRaises(RuntimeError):
            self.stage(proposed_parts=(part,), before_project_save=fail)
        self.assertEqual(self.store.load(), self.initial)
        result = self.stage(proposed_parts=(part,))
        saved = self.store.load()
        self.assertEqual(saved.parts, (part,))
        self.assertEqual(saved.master_blend, result.project.master_blend)
        self.assertEqual(saved.revision, self.initial.revision+1)
        reset = self.stage(proposed_parts=())
        self.assertEqual(reset.project.parts, ())
        self.assertTrue(reset.reused)
        self.assertEqual(result.master_path.read_bytes(), self.data)

    def test_part_staging_never_grants_geometry_validation_or_accepts_bad_shape(self):
        proposed = PartInstance('unit-part', 'unit-asset', 'hand.L')
        for value in ([proposed], ('wrong-type',), (replace(proposed, status='geometry_validated'),),
                      (proposed, replace(proposed, part_id='duplicate-slot'))):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.stage(proposed_parts=value)
        self.assertEqual(self.store.load(), self.initial)

    def test_new_revision_does_not_modify_original_master(self):
        first = self.stage()
        self.src.write_bytes(b"BLENDER" + b"second-model-content" * 20)
        second = self.stage()
        self.assertNotEqual(first.master_path, second.master_path)
        self.assertEqual(first.master_path.read_bytes(), self.data)
        self.assertNotEqual(second.master_path.read_bytes(), self.data)
        self.assertEqual(len(self.store.list_backups()), 2)

    def test_invalid_source_does_not_change_metadata(self):
        self.src.write_bytes(b"GLTF" + b"not-blender" * 9)
        with self.assertRaises(ProjectStorageError):
            self.stage()
        self.assertEqual(self.store.load(), self.initial)

    def test_source_outside_authorized_root_rejected(self):
        outside = self.root / "unauthorized.blend"
        outside.write_bytes(self.data)
        with self.assertRaises(ProjectStorageError):
            stage_unverified_master(self.store, outside, authorized_source_root=self.jobs)
        self.assertEqual(self.store.load(), self.initial)

    def test_source_symlink_rejected(self):
        pointer = self.jobs / "pointer.blend"
        try:
            pointer.symlink_to(self.src)
        except (OSError, NotImplementedError):
            self.skipTest("OS did not grant symlink permission")
        with self.assertRaises(ProjectStorageError):
            stage_unverified_master(self.store, pointer, authorized_source_root=self.jobs)

    def test_versions_directory_symlink_rejected(self):
        master = self.store.root / "master"
        master.mkdir()
        try:
            (master / "versions").symlink_to(self.jobs, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("OS did not grant symlink permission")
        with self.assertRaises(ProjectStorageError):
            self.stage()

    def test_oversized_source_rejected_and_temp_cleaned(self):
        with self.assertRaises(ProjectStorageError):
            self.stage(max_bytes=24)
        versions = self.store.root / "master" / "versions"
        self.assertEqual(list(versions.glob("*.tmp")), [])
        self.assertEqual(self.store.load(), self.initial)

    def test_failure_before_pointer_swap_preserves_original(self):
        def fail():
            raise RuntimeError("Simulated forced failure before metadata commit")
        with self.assertRaisesRegex(RuntimeError, "Simulated forced failure"):
            self.stage(before_project_save=fail)
        self.assertEqual(self.store.load(), self.initial)
        # Fully staged, orphaned SHA-256 object is intentionally left for safe recovery.
        self.assertEqual(len(list((self.store.root / "master" / "versions").glob("*.blend"))), 1)

    def test_revision_conflict_preserves_authoritative_state(self):
        def conflicting_edit():
            original = self.store.load()
            changed = replace(original, name="Concurrent editor", revision=original.revision + 1)
            self.store.save(changed, expected_revision=original.revision)
        with self.assertRaises(ProjectConflict):
            self.stage(before_project_save=conflicting_edit)
        self.assertEqual(self.store.load().name, "Concurrent editor")
        self.assertEqual(self.store.load().geometry_state, "not_generated")

    def test_unversioned_external_metadata_edit_is_not_lost_at_atomic_commit(self):
        def manual_edit():
            raw=json.loads(self.store.file.read_text())
            raw['name']='External editor kept the same revision'
            self.store.file.write_text(json.dumps(raw))
        with self.assertRaises(ProjectConflict):
            self.stage(before_project_save=manual_edit,expected_project=self.initial)
        self.assertEqual(self.store.load().name,'External editor kept the same revision')
        self.assertEqual(self.store.load().master_blend,None)

    def test_existing_corrupted_hash_revision_rejected(self):
        digest = sha256(self.data).hexdigest()
        versions = self.store.root / "master" / "versions"
        versions.mkdir(parents=True)
        (versions / f"{digest}.blend").write_bytes(b"BLENDER" + b"tampered!")
        with self.assertRaisesRegex(ProjectStorageError, "digest mismatch"):
            self.stage()
        self.assertEqual(self.store.load(), self.initial)

    def test_expected_project_id_revision_and_digest_block_stale_promotions(self):
        for change in (
            {"expected_project_id": "some-other-character"},
            {"expected_revision": 42},
        ):
            with self.subTest(change=change), self.assertRaises(ProjectConflict):
                self.stage(**change)
            self.assertEqual(self.store.load(), self.initial)
        with self.assertRaisesRegex(ProjectStorageError, "changed"):
            self.stage(expected_sha256="0" * 64)
        self.assertEqual(self.store.load(), self.initial)

    def test_cancel_before_copy_and_before_metadata_pointer_swap(self):
        cancel = Event()
        cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.stage(cancel=cancel)
        self.assertEqual(self.store.load(), self.initial)
        self.assertFalse((self.store.root / "master").exists())

        cancel.clear()
        def stop_at_commit():
            cancel.set()
        with self.assertRaisesRegex(ProjectStorageError, "cancelled"):
            self.stage(cancel=cancel, before_project_save=stop_at_commit)
        self.assertEqual(self.store.load(), self.initial)

    def test_invalid_expected_precondition_types(self):
        for change in (
            {"expected_revision": True},
            {"expected_project_id": ""},
            {"expected_sha256": "not-a-digest"},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                self.stage(**change)
        self.assertEqual(self.store.load(), self.initial)

    def test_cli_stage_reports_unverified(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(["stage-blend", str(self.store.root), str(self.src),
                           "--worker-output-root", str(self.jobs)])
        self.assertEqual(status, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["geometry_state"], "generated_unverified")
        self.assertIn("UNVERIFIED", parsed["note"])
        self.assertNotEqual(self.store.load().export_readiness(), ())

    def test_bad_size_limit(self):
        with self.assertRaises(ValidationError):
            self.stage(max_bytes=0)


if __name__ == "__main__":
    unittest.main()
