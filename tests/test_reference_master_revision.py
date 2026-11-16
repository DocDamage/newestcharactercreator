"""Synthetic storage/transaction guards; real MPFB acceptance is separate."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.master_versions import stage_unverified_master
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.expression_inspection import CheckedExpressionMaster
from ucc.jobs.expression_revisions import publish_expression_receipt
from ucc.jobs.expression_storage import load_expression_library
from ucc.jobs.hand_revision import HandRevisionResult
from ucc.jobs.hand_storage import load_hand_library
from ucc.jobs.reference_master_revision import revise_referenced_master
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError

MODULE = 'ucc.jobs.reference_master_revision.'


class ReferenceMasterRevisionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = ReferenceMasterFixture(Path(temporary.name)); self.store = self.f.store
        self.neutral = patch(MODULE+'_neutral').start()
        self.final_neutral = patch(MODULE+'inspect_saved_neutral_master').start()
        self.source = patch(MODULE+'verify_catalog_fbx_clip', return_value=self.f.reference).start()
        self.verified = []
        self.verify = patch(MODULE+'verify_saved_expression_master',
            side_effect=lambda private, **kw: self.verified.append(private.load())).start()
        self.edit = patch(MODULE+'preserve_expressions', side_effect=self.fake_body).start()
        self.build = patch(MODULE+'build_hand_library', side_effect=lambda private, **kw:
            SimpleNamespace(library=self.f.library(private), observed={'synthetic_only': True})).start()
        self.hand = patch(MODULE+'apply_hand_revision', side_effect=self.fake_hand).start()
        for name in ('installed_expression_inputs', 'installed_inputs', 'bundled_face_assets'):
            patch(MODULE+name, return_value={}).start()
        self.addCleanup(patch.stopall); self.capture()

    def capture(self):
        self.initial = self.store.load(); self.before = self.store.file.read_bytes()
        self.history = self.store.list_backups()
        self.protected = {path: sha256(path.read_bytes()).hexdigest()
                          for path in (self.store.root/'master/versions').glob('*.blend')}

    def change_intent(self, **kwargs):
        current = self.store.load()
        self.store.save(replace(current, **kwargs, revision=current.revision+1), expected_revision=current.revision)
        self.capture()

    def run_edit(self, operation='face_revision', **kwargs):
        return revise_referenced_master(self.store, self.f.database, operation=operation,
            mpfb_data_dir=self.f.root, **{**self.f.kwargs(), **kwargs})

    def unchanged(self):
        self.assertEqual(self.store.file.read_bytes(), self.before)
        self.assertEqual(self.store.list_backups(), self.history)
        for path, digest in self.protected.items(): self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)

    def fake_hand(self, private, *, manifest_sha256, selection, **kwargs):
        library = load_hand_library(private, manifest_sha256)
        revision = self.f.select(private, library, selection)
        return HandRevisionResult(revision.project, revision, manifest_sha256,
            {'synthetic_only': True}, 'unit-stage', 'unit-reopen')

    def fake_body(self, private, *, operation, **kwargs):
        current = private.load(); source_sha = Path(current.master_blend).stem
        path = private.root/'unit-body-output.blend'
        path.write_bytes(b'BLENDER'+('SYNTHETIC_BODY_NOT_GEOMETRY'+operation+str(current.parameters)
                                    +str(current.facial_parameters)).encode()*30)
        sha = sha256(path.read_bytes()).hexdigest()
        observed = {'schema_version': 1, 'master_sha256': sha, 'expression_keys_sha256': 'e'*64,
            'policy': build_expression_recipe(sha)['policy'],
            'recipe_sha256': canonical_digest(build_expression_recipe(sha)), 'sample_count': 20,
            'observation': {'synthetic_only': operation}, 'exact_neutral_restoration': True,
            'visual_quality_approved': False, 'engine_import_verified': False}
        report = private.root/'unit-inspection.json'
        report.write_text(json.dumps(observed), encoding='utf-8', newline='\n')
        checked = CheckedExpressionMaster(path, sha, observed, report,
            sha256(report.read_bytes()).hexdigest(), 'unit-inspect', 'unit-reopen')
        library = load_expression_library(private, current.expression.library_sha256)
        publish_expression_receipt(private, library, source_sha, checked, operation)
        revision = stage_unverified_master(private, path, authorized_source_root=private.root,
            expected_project=current, expected_revision=current.revision)
        return SimpleNamespace(revision=revision)

    def test_pending_body_intent_replays_old_hand_then_rebuilds_same_variant_and_instance(self):
        old_parameters = self.initial.parameters
        self.change_intent(parameters=(('height', .65), ('muscle', .5), ('weight', .5)))
        result = self.run_edit('body_refit')
        self.assertEqual(self.verified[0].parameters, old_parameters)
        self.assertEqual(self.verified[-1].parameters, self.initial.parameters)
        self.assertEqual(result.project, replace(self.initial, master_blend=result.project.master_blend,
            parts=result.project.parts, geometry_state='generated_unverified', rig_profile=None,
            revision=self.initial.revision+1))
        self.assertEqual(result.project.parts[0].part_id, self.initial.parts[0].part_id)
        self.assertTrue(result.project.parts[0].part_asset_id.endswith('-shorter'))
        self.assertNotEqual(result.project.parts[0].part_asset_id, self.initial.parts[0].part_asset_id)
        self.assertEqual(result.project.expression, self.initial.expression)
        record = check_registered_source(self.store, self.f.database, self.initial.project_id, self.f.clip_id)
        self.assertTrue(record['license']['no_ai']); self.assertFalse(record['editing_authorized'])
        self.assertFalse(result.observed['engine_import_verified'])
        for path, digest in self.protected.items(): self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)

    def test_no_hand_uses_existing_expression_chain_and_never_introduces_a_part(self):
        self.f = ReferenceMasterFixture(self.f.root/'without-hand', hand=False); self.store = self.f.store
        self.source.return_value = self.f.reference; self.capture()
        self.change_intent(facial_parameters=(('nose_width', .65),))
        first = self.run_edit(); self.assertEqual(first.project.parts, ()); self.build.assert_not_called()
        self.capture(); self.change_intent(facial_parameters=(('nose_width', .75),))
        second = self.run_edit()
        self.assertEqual(second.project.expression, first.project.expression)
        self.assertEqual(second.project.animations, first.project.animations)

    def test_verified_face_noop_does_not_publish_or_change_outer_history(self):
        self.edit.side_effect = lambda *args, **kw: SimpleNamespace(revision=None)
        result = self.run_edit()
        self.assertIsNone(result.revision); self.assertEqual(result.project, self.initial)
        self.build.assert_not_called(); self.unchanged()

    def test_policy_tamper_rejects_before_neutral_or_private_workers(self):
        key = sha256(self.f.clip_id.encode()).hexdigest()
        path = self.store.root/'animations/references'/(key+'.json')
        raw = json.loads(path.read_text(encoding='utf-8')); raw['license']['no_ai'] = False
        path.write_text(json.dumps(raw, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
        with self.assertRaises(AssetPolicyError): self.run_edit()
        self.neutral.assert_not_called(); self.edit.assert_not_called(); self.unchanged()

    def test_wrong_fresh_source_rejects_before_private_mutation(self):
        self.source.return_value = replace(self.f.reference, source_sha256='d'*64)
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.edit.assert_not_called(); self.unchanged()

    def test_missing_existing_hand_receipt_does_not_gain_admission(self):
        path = self.store.root/'parts/revisions'/(Path(self.initial.master_blend).stem+'.json'); path.unlink()
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.edit.assert_not_called(); self.unchanged()

    def test_private_worker_failure_preserves_originals(self):
        self.edit.side_effect = WorkerFailure('injected private mutation failure')
        with self.assertRaises(WorkerFailure): self.run_edit()
        self.unchanged()

    def test_changed_source_during_private_mutation_prevents_promotion(self):
        def mutate(private, **kwargs):
            result = self.fake_body(private, **kwargs); self.f.source.write_bytes(b'changed source'); return result
        self.edit.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_external_project_save_is_preserved(self):
        def mutate(private, **kwargs):
            result = self.fake_body(private, **kwargs)
            current = self.store.load()
            self.store.save(replace(current, name='External saved edit', revision=current.revision+1),
                            expected_revision=current.revision)
            return result
        self.edit.side_effect = mutate
        with self.assertRaises(ProjectConflict): self.run_edit()
        self.assertEqual(self.store.load().name, 'External saved edit')
        self.assertEqual(self.store.load().master_blend, self.initial.master_blend)

    def test_cancellation_and_outer_save_failure_leave_active_metadata_unchanged(self):
        cancelled = Event(); cancelled.set()
        with self.assertRaises(ProjectStorageError): self.run_edit(cancel=cancelled)
        self.unchanged()
        with patch.object(self.store, 'save', side_effect=ProjectConflict('injected outer save conflict')):
            with self.assertRaises(ProjectConflict): self.run_edit()
        self.unchanged()

    def test_changed_private_output_after_inspection_is_rejected(self):
        def mutate(private, **kwargs):
            path = private.root/private.load().master_blend; path.write_bytes(path.read_bytes()+b'changed')
        self.final_neutral.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_unsupported_operation_and_timeout_reject_before_workers(self):
        for operation in ('unknown', None):
            with self.assertRaises(ValidationError): self.run_edit(operation)
        for value in (True, float('nan'), 0, 3601):
            with self.assertRaises(ValidationError): self.run_edit(timeout_s=value)
        self.neutral.assert_not_called(); self.unchanged()


if __name__ == '__main__': unittest.main()
