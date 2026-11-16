"""Plain-reference transaction contracts with synthetic, non-geometry workers."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.reference_plain_master_contract import PlainReferenceMasterFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.master_versions import stage_unverified_master
from ucc.core.reference_master_intent import supports_referenced_master_intent
from ucc.jobs.animation_reference_storage import check_registered_source
from ucc.jobs.hand_revision import HandRevisionResult
from ucc.jobs.hand_storage import load_hand_library
from ucc.jobs.reference_master_revision import revise_referenced_master
from ucc.jobs.runner import WorkerFailure

MODULE = 'ucc.jobs.reference_plain_master.'


class PlainReferenceMasterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture()
        self.neutral = patch(MODULE+'_neutral').start()
        self.final_neutral = patch(MODULE+'inspect_saved_neutral_master').start()
        self.body_intent = patch(MODULE+'inspect_plain_body_intent', return_value={}).start()
        self.source = patch(MODULE+'verify_catalog_fbx_clip', return_value=self.f.reference).start()
        self.face = patch(MODULE+'apply_saved_face_revision', side_effect=self.fake_body).start()
        self.refit = patch(MODULE+'apply_saved_customized_body_revision', side_effect=self.fake_body).start()
        self.generate = patch(MODULE+'generate_customized_humanoid', side_effect=self.fake_body).start()
        self.build = patch(MODULE+'build_hand_library', side_effect=lambda private, **kw:
            SimpleNamespace(library=self.f.library(private), observed={'synthetic_only': True})).start()
        self.hand = patch(MODULE+'apply_hand_revision', side_effect=self.fake_hand).start()
        patch(MODULE+'installed_inputs', return_value={}).start()
        patch(MODULE+'bundled_face_assets', return_value={}).start()
        self.addCleanup(patch.stopall)

    def fixture(self, *, hand=True, face=True):
        self.f = PlainReferenceMasterFixture(self.root/('fixture-'+str(len(list(self.root.iterdir())))),
                                             hand=hand, face=face)
        self.store = self.f.store
        if hasattr(self, 'source'): self.source.return_value = self.f.reference
        self.capture()

    def capture(self):
        self.initial = self.store.load(); self.before = self.store.file.read_bytes()
        self.history = self.store.list_backups()
        self.protected = {p: sha256(p.read_bytes()).hexdigest()
                          for p in (self.store.root/'master/versions').glob('*.blend')}

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

    def fake_body(self, private, **kwargs):
        current = private.load(); self.assertIsNone(current.expression); self.assertFalse(current.animations)
        self.assertFalse(current.parts)
        path = private.root/'unit-plain-body-output.blend'
        path.write_bytes(b'BLENDER'+('SYNTHETIC_PLAIN_NOT_GEOMETRY'+str(current.parameters)
                                    +str(current.facial_parameters)).encode()*30)
        revision = stage_unverified_master(private, path, authorized_source_root=private.root,
            expected_project=current, expected_revision=current.revision)
        return SimpleNamespace(revision=revision)

    def test_all_three_operations_rebuild_hand_and_preserve_source_ids_and_instance(self):
        for operation in ('face_revision', 'body_refit', 'body_generation'):
            with self.subTest(operation=operation):
                self.fixture()
                intent = dict(facial_parameters=(('nose_width', .65),))
                if operation != 'face_revision':
                    intent['parameters'] = (('height', .6), ('muscle', .5), ('weight', .5))
                self.change_intent(**intent)
                result = self.run_edit(operation)
                self.assertEqual(result.project, replace(self.initial, master_blend=result.project.master_blend,
                    parts=result.project.parts, geometry_state='generated_unverified', rig_profile=None,
                    revision=self.initial.revision+1))
                self.assertIsNone(result.project.expression)
                self.assertEqual(result.project.parts[0].part_id, self.initial.parts[0].part_id)
                self.assertTrue(result.project.parts[0].part_asset_id.endswith('-shorter'))
                self.assertNotEqual(result.project.parts[0].part_asset_id, self.initial.parts[0].part_asset_id)
                self.assertTrue(result.observed['registered_hand_rebuilt'])
                self.assertFalse(result.observed['target_animation_verified'])
                record = check_registered_source(self.store, self.f.database, self.initial.project_id, self.f.clip_id)
                self.assertTrue(record['license']['no_ai']); self.assertFalse(record['editing_authorized'])
                for path, digest in self.protected.items(): self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)

    def test_no_hand_with_and_without_face_intent_never_introduces_parts_or_expressions(self):
        for face in (False, True):
            for operation in ('body_refit', 'body_generation'):
                with self.subTest(face=face, operation=operation):
                    self.fixture(hand=False, face=face)
                    result = self.run_edit(operation)
                    self.assertEqual(result.project.parts, ()); self.assertIsNone(result.project.expression)
                    self.assertEqual(result.project.animations, self.initial.animations)
        self.build.assert_not_called()

    def test_verified_face_noop_preserves_outer_history_and_selected_hand(self):
        self.face.side_effect = lambda *a, **kw: SimpleNamespace(revision=None)
        result = self.run_edit()
        self.assertIsNone(result.revision); self.assertEqual(result.project, self.initial)
        self.build.assert_not_called(); self.unchanged()

    def test_fresh_source_mismatch_prevents_private_body_work(self):
        self.source.return_value = replace(self.f.reference, source_sha256='d'*64)
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.face.assert_not_called(); self.unchanged()

    def test_missing_hand_receipt_is_not_admitted(self):
        (self.store.root/'parts/revisions'/(Path(self.initial.master_blend).stem+'.json')).unlink()
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.face.assert_not_called(); self.unchanged()

    def test_private_failure_preserves_originals(self):
        self.face.side_effect = WorkerFailure('injected private failure')
        with self.assertRaises(WorkerFailure): self.run_edit()
        self.unchanged()

    def test_pending_body_is_checked_before_face_worker_and_preserves_outer_intent(self):
        self.change_intent(parameters=(('height', .6), ('muscle', .5), ('weight', .5)))
        self.body_intent.side_effect = WorkerFailure('MPFB height phenotype differed from saved slider')
        with self.assertRaises(WorkerFailure): self.run_edit()
        self.face.assert_not_called(); self.build.assert_not_called(); self.unchanged()

    def test_final_body_readback_failure_prevents_hand_rebuild_and_publication(self):
        self.body_intent.side_effect = WorkerFailure('saved physical body differs')
        with self.assertRaises(WorkerFailure): self.run_edit('body_refit')
        self.refit.assert_called_once(); self.build.assert_not_called(); self.unchanged()

    def test_changed_source_after_body_work_prevents_promotion(self):
        def mutate(private, **kw):
            result = self.fake_body(private, **kw); self.f.source.write_bytes(b'changed'); return result
        self.face.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_external_save_is_preserved(self):
        def mutate(private, **kw):
            result = self.fake_body(private, **kw); current = self.store.load()
            self.store.save(replace(current, name='External saved edit', revision=current.revision+1),
                            expected_revision=current.revision)
            return result
        self.face.side_effect = mutate
        with self.assertRaises(ProjectConflict): self.run_edit()
        self.assertEqual(self.store.load().name, 'External saved edit')
        self.assertEqual(self.store.load().master_blend, self.initial.master_blend)

    def test_cancel_and_outer_save_conflict_preserve_metadata(self):
        cancelled = Event(); cancelled.set()
        with self.assertRaises(ProjectStorageError): self.run_edit(cancel=cancelled)
        self.unchanged()
        with patch.object(self.store, 'save', side_effect=ProjectConflict('injected save conflict')):
            with self.assertRaises(ProjectConflict): self.run_edit()
        self.unchanged()

    def test_output_changed_after_final_inspection_is_rejected(self):
        def mutate(private, **kw):
            path = private.root/private.load().master_blend; path.write_bytes(path.read_bytes()+b'changed')
        self.final_neutral.side_effect = mutate
        with self.assertRaises(ProjectStorageError): self.run_edit()
        self.unchanged()

    def test_missing_face_intent_is_rejected_before_workers(self):
        self.fixture(hand=False, face=False)
        with self.assertRaises(ValidationError): self.run_edit()
        self.source.assert_not_called(); self.face.assert_not_called(); self.unchanged()

    def test_plain_intent_eligibility_keeps_unknown_parts_and_missing_master_denied(self):
        self.assertTrue(supports_referenced_master_intent(self.initial))
        self.assertFalse(supports_referenced_master_intent(replace(self.initial, master_blend=None,
            geometry_state='not_generated', parts=())))
        self.assertFalse(supports_referenced_master_intent(replace(self.initial,
            parts=(replace(self.initial.parts[0], part_asset_id='unknown'),))))
