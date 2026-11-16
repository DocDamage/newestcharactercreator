"""Synthetic storage/transaction boundaries; never real Blender evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from fixtures.project_reference_contract import ReferenceFixture
from ucc.core.errors import CompatibilityError, ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.hand_parts import (build_hand_library_recipe, build_hand_manifest,
    build_hand_receipt, hand_asset_id)
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import PartInstance
from ucc.jobs.animation_reference_storage import publish_source_binding, load_source_binding
from ucc.jobs.hand_revision import HandRevisionResult
from ucc.jobs.hand_storage import publish_asset, publish_manifest, publish_hand_receipt
from ucc.jobs.reference_edit_scratch import create_hand_edit_scratch
from ucc.jobs.reference_hand_revision import apply_referenced_hand_revision
from ucc.jobs.runner import WorkerFailure

MODULE = 'ucc.jobs.reference_hand_revision.'


class ReferenceHandRevisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = ReferenceFixture(Path(temporary.name)); self.store = self.f.store
        assets = {}
        for variant in ('shorter', 'longer'):
            path = self.f.root/(variant+'.blend'); path.write_bytes(b'BLENDER'+variant.encode()*500)
            identity = sha256(path.read_bytes()).hexdigest()
            publish_asset(self.store, path, identity, path.parent)
            assets[variant] = {'sha256': identity, 'observation_sha256': 'e'*64}
        manifest = build_hand_manifest(build_hand_library_recipe(self.f.project, self.f.master_sha), assets)
        self.identity = publish_manifest(self.store, manifest)
        publish_source_binding(self.store, self.f.project.project_id, self.f.reference)
        self.initial = self.store.save(replace(self.f.project, animations=(self.f.clip_id,), revision=self.f.project.revision+1), expected_revision=self.f.project.revision)
        self.metadata = self.store.file.read_bytes(); self.history = self.store.list_backups()
        self.neutral = patch(MODULE+'_neutral').start()
        self.final_neutral = patch(MODULE+'inspect_saved_neutral_master').start()
        self.source = patch(MODULE+'verify_catalog_fbx_clip', return_value=self.f.reference).start()
        self.edit = patch(MODULE+'apply_hand_revision', side_effect=self.fake_edit).start()
        self.addCleanup(patch.stopall)

    def run_edit(self, **overrides):
        return apply_referenced_hand_revision(self.store, self.f.database,
            manifest_sha256=self.identity, selection=overrides.pop('selection', 'shorter'),
            mpfb_data_dir=self.f.root, **{**self.f.kwargs(), **overrides})

    def fake_edit(self, scratch, *, selection, **kwargs):
        current = scratch.load()
        if selection == 'neutral':
            return HandRevisionResult(current, None, self.identity, {'selection_changed': False}, 'unit-stage', 'unit-reopen')
        output = scratch.root/'unit-output.blend'
        output.write_bytes(b'BLENDER'+b'NONSHIPPING_SYNTHETIC_HAND_OUTPUT'*80)
        output_sha = sha256(output.read_bytes()).hexdigest()
        receipt = build_hand_receipt(self.identity, output_sha, self.f.master_sha, selection, 'f'*64)
        publish_hand_receipt(scratch, receipt)
        parts = (PartInstance('unit-part', hand_asset_id(self.identity, selection), 'hand.L'),)
        revision = stage_unverified_master(scratch, output, authorized_source_root=scratch.root,
            expected_project=current, expected_revision=current.revision, proposed_parts=parts)
        return HandRevisionResult(revision.project, revision, self.identity,
            {'selection_changed': True}, 'unit-stage', 'unit-reopen')

    def unchanged(self):
        self.assertEqual(self.store.file.read_bytes(), self.metadata)
        self.assertEqual(self.store.list_backups(), self.history)
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)

    def test_atomic_hand_result_preserves_references_rights_and_other_intent(self):
        result = self.run_edit()
        self.assertEqual(result.project, replace(self.initial, revision=self.initial.revision+1,
            master_blend=result.project.master_blend, parts=result.project.parts))
        self.assertEqual(self.store.load(), result.project)
        self.assertEqual(result.project.animations, (self.f.clip_id,))
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)
        binding = load_source_binding(self.store, self.initial.project_id, self.f.clip_id)
        self.assertTrue(binding['license']['no_ai']); self.assertFalse(binding['editing_authorized'])
        self.assertFalse(result.observed['engine_import_verified'])
        self.assertEqual(self.source.call_count, 1); self.assertEqual(self.neutral.call_count, 1)

    def test_noop_retains_outer_revision_and_history(self):
        result = self.run_edit(selection='neutral')
        self.assertIsNone(result.revision); self.assertEqual(result.project, self.initial); self.unchanged()

    def test_scratch_omits_only_external_ids_and_never_writes_outer_metadata(self):
        scratch = create_hand_edit_scratch(self.store, self.initial, self.identity, None)
        self.assertEqual(scratch.project, replace(self.initial, animations=(), revision=1))
        self.assertFalse((scratch.store.root/'animations').exists())
        self.assertEqual(len(scratch.dependencies), 4); self.unchanged()
        # Copying never hard-links authoritative originals into editable scratch.
        copied = scratch.store.root/self.initial.master_blend
        copied.write_bytes(copied.read_bytes()+b'private edit')
        self.assertEqual(self.f.master.read_bytes(), self.f.master_bytes)

    def test_empty_reference_list_and_invalid_selection_reject(self):
        with self.assertRaises(ValidationError): self.run_edit(selection='unsupported')
        self.store.save(replace(self.initial, animations=(), revision=self.initial.revision+1), expected_revision=self.initial.revision)
        with self.assertRaises(ValidationError): self.run_edit()
        self.edit.assert_not_called()

    def test_missing_source_rejects_before_any_worker(self):
        self.f.source.unlink()
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.neutral.assert_not_called(); self.edit.assert_not_called(); self.unchanged()

    def test_changed_fresh_identity_rejects_without_private_edit(self):
        self.source.return_value = replace(self.f.reference, source_sha256='d'*64)
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.edit.assert_not_called(); self.unchanged()

    def test_animated_neutral_rejection_preserves_active_project(self):
        self.neutral.side_effect = WorkerFailure('actual animation forbidden')
        with self.assertRaises(WorkerFailure): self.run_edit()
        self.source.assert_not_called(); self.edit.assert_not_called(); self.unchanged()

    def test_hand_body_recipe_mismatch_rejects(self):
        changed = replace(self.initial, parameters=(('height', .6), ('muscle', .5), ('weight', .5)), revision=self.initial.revision+1)
        self.store.save(changed, expected_revision=self.initial.revision); before = self.store.file.read_bytes()
        with self.assertRaises(CompatibilityError): self.run_edit()
        self.assertEqual(self.store.file.read_bytes(), before); self.edit.assert_not_called()

    def test_coherently_rehashed_master_without_current_hand_receipt_rejects(self):
        parts = (PartInstance('unadmitted', hand_asset_id(self.identity, 'shorter'), 'hand.L'),)
        self.store.save(replace(self.initial, parts=parts, revision=self.initial.revision+1), expected_revision=self.initial.revision)
        before = self.store.file.read_bytes()
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.assertEqual(self.store.file.read_bytes(), before); self.edit.assert_not_called()

    def test_original_asset_changed_during_private_edit_prevents_promotion(self):
        def mutate(scratch, **kwargs):
            result = self.fake_edit(scratch, **kwargs)
            path = self.store.root/'parts/manifests'/(self.identity+'.json')
            path.write_bytes(path.read_bytes()+b' ')
            return result
        self.edit.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_source_changed_during_private_edit_prevents_promotion(self):
        def mutate(scratch, **kwargs):
            result = self.fake_edit(scratch, **kwargs); self.f.source.write_bytes(b'changed'); return result
        self.edit.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_private_unrelated_intent_change_is_rejected(self):
        def mutate(scratch, **kwargs):
            result = self.fake_edit(scratch, **kwargs); current = scratch.load()
            altered = scratch.save(replace(current, name='unexpected', revision=current.revision+1), expected_revision=current.revision)
            return replace(result, project=altered)
        self.edit.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_private_worker_failure_and_cancellation_preserve_outer_master(self):
        self.edit.side_effect = WorkerFailure('injected private Blender failure')
        with self.assertRaises(WorkerFailure): self.run_edit()
        self.unchanged()
        cancelled = Event(); cancelled.set()
        with self.assertRaises(ProjectStorageError): self.run_edit(cancel=cancelled)
        self.unchanged()

    def test_atomic_save_failure_does_not_promote_private_metadata(self):
        with patch.object(self.store, 'save', side_effect=ProjectConflict('injected save failure')):
            with self.assertRaises(ProjectConflict): self.run_edit()
        self.unchanged()


if __name__ == '__main__': unittest.main()
