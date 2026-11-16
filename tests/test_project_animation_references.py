"""Source-only reference transaction boundaries; physical Blender is separate."""
from dataclasses import replace
from hashlib import sha256
import json
from threading import Event
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fixtures.project_reference_contract import ReferenceFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.jobs.animation_reference_storage import load_source_binding, check_registered_source
from ucc.jobs.project_animation_references import attach_catalog_reference, detach_catalog_reference
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError


class ProjectAnimationReferenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = ReferenceFixture(Path(temporary.name)); self.store = self.f.store
        self.neutral = patch('ucc.jobs.project_animation_references.inspect_saved_neutral_master', side_effect=self.f.neutral).start()
        self.source = patch('ucc.jobs.project_animation_references.verify_catalog_fbx_clip', return_value=self.f.reference).start()
        self.addCleanup(patch.stopall)

    def attach(self, **overrides):
        kwargs = {**self.f.kwargs(), 'expected_source_sha256': self.f.source_sha, 'expected_policy': self.f.policy, **overrides}
        return attach_catalog_reference(self.store, self.f.database, self.f.clip_id, **kwargs)

    def binding_file(self):
        key = sha256(self.f.clip_id.encode()).hexdigest()
        return self.store.root/'animations/references'/(key+'.json')

    def test_attach_changes_only_reference_and_revision_and_retains_source_rights(self):
        before = self.store.load(); result = self.attach()
        self.assertTrue(result.changed)
        self.assertEqual(result.project, replace(before, animations=(self.f.clip_id,), revision=before.revision+1))
        self.assertEqual(self.store.load(), result.project); self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)
        binding = load_source_binding(self.store, before.project_id, self.f.clip_id)
        self.assertEqual(binding['license'], self.f.policy.to_dict())
        self.assertTrue(binding['source_only']); self.assertFalse(binding['editing_authorized'])
        self.assertFalse(binding['engine_import_verified']); self.assertFalse(binding['target_preview_verified'])
        self.assertEqual(check_registered_source(self.store, self.f.database, before.project_id, self.f.clip_id), binding)
        self.assertTrue(result.project.export_readiness())

    def test_duplicate_attach_is_verified_but_preserves_revision_history_and_binding(self):
        first = self.attach(); metadata = self.store.file.read_bytes(); binding = self.binding_file().read_bytes()
        history = self.store.list_backups(); second = self.attach()
        self.assertFalse(second.changed); self.assertEqual(second.project, first.project)
        self.assertEqual(self.store.file.read_bytes(), metadata); self.assertEqual(self.binding_file().read_bytes(), binding)
        self.assertEqual(self.store.list_backups(), history); self.assertEqual(self.neutral.call_count, 2)

    def test_detach_retains_immutable_binding_for_old_revisions(self):
        added = self.attach(); binding = self.binding_file().read_bytes()
        removed = detach_catalog_reference(self.store, self.f.clip_id, **self.f.kwargs())
        self.assertEqual(removed.project.animations, ()); self.assertTrue(removed.changed)
        self.assertEqual(removed.project.revision, added.project.revision+1)
        self.assertEqual(self.binding_file().read_bytes(), binding)
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)

    def test_noop_detach_has_no_worker_or_revision_change(self):
        before = self.store.file.read_bytes()
        result = detach_catalog_reference(self.store, self.f.clip_id, **self.f.kwargs())
        self.assertFalse(result.changed); self.neutral.assert_not_called(); self.source.assert_not_called()
        self.assertEqual(self.store.file.read_bytes(), before)

    def test_failure_before_project_pointer_leaves_only_inactive_immutable_binding(self):
        before = self.store.file.read_bytes()
        with patch.object(self.store, 'save', side_effect=ProjectConflict('injected pointer conflict')):
            with self.assertRaises(ProjectConflict): self.attach()
        self.assertEqual(self.store.file.read_bytes(), before); self.assertEqual(self.store.load().animations, ())
        self.assertTrue(self.binding_file().is_file()); self.assertEqual(self.store.list_backups(), ())
        self.assertTrue(self.attach().changed)  # Same verified binding can be safely reused.

    def test_corrupt_binding_is_not_overwritten_on_attach(self):
        path = self.binding_file(); path.parent.mkdir(parents=True); path.write_bytes(b'corrupt unit binding')
        before = self.store.file.read_bytes()
        with self.assertRaises(ProjectStorageError): self.attach()
        self.assertEqual(path.read_bytes(), b'corrupt unit binding'); self.assertEqual(self.store.file.read_bytes(), before)

    def test_coherent_policy_tamper_in_active_binding_rejects_before_new_workers(self):
        self.attach(); raw = json.loads(self.binding_file().read_text(encoding='utf-8')); raw['license']['no_ai'] = False
        self.binding_file().write_text(json.dumps(raw, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
        before = self.store.file.read_bytes(); self.neutral.reset_mock(); self.source.reset_mock()
        with self.assertRaises(AssetPolicyError): self.attach()
        self.neutral.assert_not_called(); self.source.assert_not_called(); self.assertEqual(self.store.file.read_bytes(), before)

    def test_foreign_binding_and_noncanonical_encoding_cannot_be_adopted(self):
        self.attach(); original = self.binding_file().read_bytes(); project = self.store.load()
        with self.assertRaises(ProjectStorageError): load_source_binding(self.store, 'another-project', self.f.clip_id)
        self.binding_file().write_bytes(original+b' ')
        with self.assertRaisesRegex(ProjectStorageError, 'immutable encoding'):
            load_source_binding(self.store, project.project_id, self.f.clip_id)

    def test_stale_expected_revision_rejects_before_workers(self):
        with self.assertRaises(ProjectConflict): self.attach(expected_revision=0)
        self.neutral.assert_not_called(); self.source.assert_not_called()

    def test_wrong_source_policy_rejects_before_any_worker_or_binding(self):
        with self.assertRaises(AssetPolicyError): self.attach(expected_policy=replace(self.f.policy, no_ai=False))
        self.neutral.assert_not_called(); self.source.assert_not_called(); self.assertFalse(self.binding_file().exists())

    def test_wrong_fresh_result_cannot_poison_an_immutable_binding(self):
        self.source.return_value = replace(self.f.reference, source_sha256='b'*64)
        before = self.store.file.read_bytes()
        with self.assertRaisesRegex(ProjectStorageError, 'different reference'): self.attach()
        self.assertFalse(self.binding_file().exists()); self.assertEqual(self.store.file.read_bytes(), before)

    def test_animated_target_failure_cannot_clear_existing_guards_or_change_project(self):
        before = self.store.file.read_bytes(); self.neutral.side_effect = WorkerFailure('actual target Action rejected')
        with self.assertRaises(WorkerFailure): self.attach()
        self.source.assert_not_called(); self.assertEqual(self.store.file.read_bytes(), before)

    def test_project_change_during_neutral_verification_is_preserved_not_overwritten(self):
        def changed(store, **kwargs):
            result = self.f.neutral(store, **kwargs); current = store.load()
            store.save(replace(current, name='External edit', revision=current.revision+1), expected_revision=current.revision)
            return result
        self.neutral.side_effect = changed
        with self.assertRaises(ProjectConflict): self.attach()
        self.source.assert_not_called(); self.assertEqual(self.store.load().name, 'External edit')

    def test_cancel_after_neutral_returns_no_reference_or_project_change(self):
        cancel = Event(); before = self.store.file.read_bytes()
        def cancelled(store, **kwargs):
            result = self.f.neutral(store, **kwargs); cancel.set(); return result
        self.neutral.side_effect = cancelled
        with self.assertRaises(ProjectStorageError): self.attach(cancel=cancel)
        self.source.assert_not_called(); self.assertEqual(self.store.file.read_bytes(), before)

    def test_detach_does_not_require_missing_source_but_still_requires_neutral_master(self):
        self.attach(); self.f.source.unlink(); self.source.reset_mock()
        removed = detach_catalog_reference(self.store, self.f.clip_id, **self.f.kwargs())
        self.assertTrue(removed.changed); self.source.assert_not_called()


if __name__ == '__main__': unittest.main()
