"""Synthetic storage/ownership faults; actual MPFB/cache acceptance is separate."""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.reference_expression_contract import preview_stub, body_runner_stub
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.reference_expression_preview import preview_referenced_expressions
from ucc.jobs.reference_expression_evidence import check_referenced_expression_preview, _check_cache_evidence
from ucc.jobs.reference_expression_intent import check_expression_face_intent, inspect_expression_body_intent
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError

MODULE = 'ucc.jobs.reference_expression_preview.'


class ReferenceExpressionPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.f = ReferenceMasterFixture(self.root/'fixture'); self.store = self.f.store
        self.neutral = patch(MODULE+'_neutral').start()
        self.source = patch(MODULE+'verify_catalog_fbx_clip', return_value=self.f.reference).start()
        self.body = patch(MODULE+'inspect_expression_body_intent', return_value=({'synthetic_only': True}, ())).start()
        self.preview = patch(MODULE+'preview_saved_expressions', side_effect=preview_stub).start()
        self.cache = patch('ucc.jobs.reference_expression_evidence._check_cache_evidence').start()
        self.addCleanup(patch.stopall); self.capture()

    def capture(self):
        self.initial = self.store.load(); self.before = self.store.file.read_bytes()
        self.history = self.store.list_backups()
        self.objects = {p: p.read_bytes() for role in ('master', 'parts', 'expressions', 'animations')
                        for p in (self.store.root/role).rglob('*') if p.is_file()}

    def run_preview(self, **kwargs):
        return preview_referenced_expressions(self.store, self.f.database, mpfb_data_dir=self.root,
                                              **{**self.f.kwargs(), **kwargs})

    def unchanged(self):
        self.assertEqual(self.store.file.read_bytes(), self.before)
        self.assertEqual(self.store.list_backups(), self.history)
        for path, data in self.objects.items(): self.assertEqual(path.read_bytes(), data)

    def test_owner_sources_private_snapshot_and_existing_guard_are_all_retained(self):
        result = self.run_preview(); self.unchanged()
        self.assertEqual(result.project, self.initial)
        self.assertEqual(result.context.project, replace(self.initial, animations=(), revision=1))
        self.assertEqual(result.preview.master_sha256, Path(self.initial.master_blend).stem)
        self.assertEqual(tuple(r['clip_id'] for r in result.references), self.initial.animations)
        self.assertTrue(result.references[0]['license']['no_ai'])
        self.assertFalse(result.references[0]['editing_authorized'])
        from ucc.core.expression_clip import build_expression_clip
        with self.assertRaises(ValidationError): build_expression_clip(self.initial, result.preview.master_sha256)
        check_referenced_expression_preview(self.store, self.f.database, result)
        self.assertEqual(self.preview.call_args.kwargs['expected_revision'], 1)

    def test_no_hand_path_does_not_require_or_introduce_a_hand(self):
        self.f = ReferenceMasterFixture(self.root/'without-hand', hand=False); self.store = self.f.store
        self.source.return_value = self.f.reference; self.capture()
        result = self.run_preview(); self.assertFalse(result.context.project.parts); self.unchanged()

    def test_coherent_NoAI_rewrite_rejects_before_neutral_or_source_workers(self):
        path = next((self.store.root/'animations/references').glob('*.json'))
        raw = json.loads(path.read_text(encoding='utf-8')); raw['license']['no_ai'] = False
        path.write_text(json.dumps(raw, sort_keys=True, separators=(',', ':')), encoding='utf-8', newline='\n')
        with self.assertRaises(AssetPolicyError): self.run_preview()
        self.neutral.assert_not_called(); self.source.assert_not_called(); self.preview.assert_not_called()

    def test_wrong_fresh_source_and_missing_hand_provenance_reject_before_preview(self):
        self.source.return_value = replace(self.f.reference, source_sha256='b'*64)
        with self.assertRaises(ProjectStorageError): self.run_preview()
        self.source.return_value = self.f.reference
        (self.store.root/'parts/revisions'/(Path(self.initial.master_blend).stem+'.json')).unlink()
        with self.assertRaises(ProjectStorageError): self.run_preview()
        self.preview.assert_not_called(); self.assertEqual(self.store.file.read_bytes(), self.before)

    def test_pending_saved_hand_shape_intent_cannot_preview_old_physical_body(self):
        saved = self.store.save(replace(self.initial, parameters=(('height', .7), ('muscle', .5), ('weight', .5)),
            revision=self.initial.revision+1), expected_revision=self.initial.revision)
        self.capture()
        with self.assertRaises(ProjectStorageError): self.run_preview()
        self.body.assert_not_called(); self.preview.assert_not_called(); self.unchanged()

    def test_pending_face_values_reject_against_actual_original_key_values(self):
        desired = replace(self.initial, facial_parameters=(('nose_width', .7),))
        with self.assertRaises(ProjectStorageError):
            check_expression_face_intent(desired, {'all_keys': {}})
        for value in (True, float('nan'), .2):
            with self.assertRaises(ProjectStorageError):
                check_expression_face_intent(self.initial,
                    {'all_keys': {'nose-scale-horiz-incr': {'value': value}}})

    def test_pending_no_hand_face_intent_rejects_before_any_display_result(self):
        self.f = ReferenceMasterFixture(self.root/'pending-face', hand=False); self.store = self.f.store
        current = self.store.load()
        self.store.save(replace(current, facial_parameters=(('nose_width', .7),), revision=current.revision+1),
                        expected_revision=current.revision)
        self.source.return_value = self.f.reference; self.capture()
        with self.assertRaises(ProjectStorageError): self.run_preview()
        self.preview.assert_called_once(); self.unchanged()

    def test_body_inspection_requires_two_bound_readbacks_of_the_saved_macro_values(self):
        report = {'macro_parameters_observed': dict(self.initial.parameters), 'macro_evaluated_vertices': 19158,
            'macro_active_shape_keys': 6, 'macro_evaluated_sha256': 'a'*64, 'macro_shape_evaluated': True,
            'visual_deformation_verified': False, 'engine_import_verified': False}
        run, calls = body_runner_stub(self.root, self.store.root/self.initial.master_blend, [report, report])
        with patch('ucc.jobs.reference_expression_intent.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = run
            proof, files = inspect_expression_body_intent(self.store, self.initial,
                blender_exe=self.f.executable, worker_script=self.f.script, cancel=None, timeout_s=300)
        self.assertEqual(len(calls), 2); self.assertEqual(len(files), 6)
        self.assertTrue(proof['morph_save_reopen_verified'])
        report = dict(report, macro_parameters_observed={'height': .8, 'muscle': .5, 'weight': .5})
        new_root = self.root/'wrong-readback'; new_root.mkdir()
        run, _ = body_runner_stub(new_root, self.store.root/self.initial.master_blend, [report, report])
        with patch('ucc.jobs.reference_expression_intent.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = run
            with self.assertRaises(ValidationError):
                inspect_expression_body_intent(self.store, self.initial, blender_exe=self.f.executable,
                    worker_script=self.f.script, cancel=None, timeout_s=300)

    def test_worker_failure_or_live_cancellation_never_publish_outer_state(self):
        self.preview.side_effect = WorkerFailure('Injected private cache failure')
        with self.assertRaises(WorkerFailure): self.run_preview()
        self.unchanged()
        cancel = Event(); cancel.set()
        with self.assertRaises(ProjectStorageError): self.run_preview(cancel=cancel)
        self.unchanged()

    def test_actual_external_save_is_preserved_instead_of_stale_preview_publication(self):
        def changed(private, **kwargs):
            result = preview_stub(private, **kwargs)
            self.store.save(replace(self.initial, name='External edit', revision=self.initial.revision+1),
                            expected_revision=self.initial.revision)
            return result
        self.preview.side_effect = changed
        with self.assertRaises(ProjectConflict): self.run_preview()
        self.assertEqual(self.store.load().name, 'External edit')
        self.assertEqual(self.store.load().master_blend, self.initial.master_blend)

    def test_source_changes_during_private_preview_prevent_publication(self):
        def changed(private, **kwargs):
            result = preview_stub(private, **kwargs); self.f.source.write_bytes(b'changed source'); return result
        self.preview.side_effect = changed
        with self.assertRaises(ProjectStorageError): self.run_preview()
        self.unchanged()

    def test_private_project_and_inspection_tamper_reject(self):
        result = self.run_preview()
        result.preview.inspection.report.write_bytes(b'changed private report')
        with self.assertRaises(ProjectStorageError): check_referenced_expression_preview(self.store, self.f.database, result)
        self.unchanged()

    def test_result_owner_ids_private_revision_receipt_and_worker_directories_cannot_be_substituted(self):
        result = self.run_preview()
        for changed in (replace(result, metadata_sha256='e'*64),
                        replace(result, references=()),
                        replace(result, preview=replace(result.preview, revision=99)),
                        replace(result, receipt_path=self.root/'foreign.json')):
            with self.assertRaises((ProjectConflict, ProjectStorageError)):
                check_referenced_expression_preview(self.store, self.f.database, changed)
        with self.assertRaises(ProjectStorageError):
            _check_cache_evidence(self.store, replace(result, preview=replace(result.preview,
                verify_dir=result.preview.workdir)), None)
        result.receipt_path.write_text('{}', encoding='utf-8', newline='\n')
        with self.assertRaises(ProjectStorageError): check_referenced_expression_preview(self.store, self.f.database, result)
        self.unchanged()

    def test_invalid_timeout_and_unsupported_state_reject_before_workers(self):
        for value in (True, float('nan'), 0, 3601):
            with self.assertRaises(ValidationError): self.run_preview(timeout_s=value)
        self.neutral.assert_not_called()


if __name__ == '__main__': unittest.main()
