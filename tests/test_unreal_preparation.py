"""Source admission faults with NONSHIPPING byte markers, never engine evidence."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch
import json
from fixtures.unreal_source_logic import UnrealSourceFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.skin_material_preparation import _BudgetCancel
from ucc.jobs.unreal_preparation import prepare_unreal_source
import ucc.jobs.unreal_preparation as preparation


class UnrealPreparationTests(TestCase):
    def run_case(self, fixture, **options):
        with ExitStack() as stack:
            for p in fixture.patches():
                stack.enter_context(p)
            return prepare_unreal_source(fixture.store, **fixture.options, **options)

    def test_private_source_result_binds_both_workers_and_false_capabilities(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); before = f.store.file.read_bytes()
            result = self.run_case(f)
            self.assertEqual(result.request_sha256, f.request.sha256)
            self.assertEqual(len(result.files), 5)
            self.assertEqual(result.expected_unreal_material_slot_name, 'UNIT_SLOT_NOT_REAL')
            self.assertEqual(len(f.calls), 2)
            self.assertNotEqual(result.stage_job_id, result.verify_job_id)
            self.assertEqual(f.store.file.read_bytes(), before)
            proof = json.loads((result.directory/'unreal_source_verification.json').read_bytes())
            self.assertTrue(proof['fresh_original_master_reopened'])
            self.assertFalse(proof['exported_fbx_rebuilt'])
            self.assertFalse(proof['engine_import_verified'])
            self.assertFalse(proof['export_published'])
            (result.directory/'unreal_source_stage.json').write_bytes(b'altered')
            with self.assertRaises(ProjectStorageError):
                _ = result.expected_unreal_material_slot_name

    def test_stale_review_never_starts_worker(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp))
            f.request = replace(f.request, project_sha256='0'*64)
            with self.assertRaises(ProjectConflict):
                self.run_case(f)
            self.assertFalse(f.calls)

    def test_pre_cancel_does_not_enumerate_or_launch(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); cancel = Event(); cancel.set()
            with patch.object(preparation, 'bounded_paths') as traversal:
                with self.assertRaisesRegex(ProjectStorageError, 'cancelled by caller'):
                    self.run_case(f, cancel=cancel)
                traversal.assert_not_called()
            self.assertFalse(f.calls)

    def test_cancel_between_workers_retains_truthful_failure(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); cancel = Event(); f.after_stage = cancel.set
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled by caller') as raised:
                self.run_case(f, cancel=cancel)
            self.assertEqual(len(f.calls), 1)
            journal = f.store.root/'.ucc-jobs'/('unreal-source-'+f.request.job_id)/'preparation.json'
            self.assertEqual(json.loads(journal.read_bytes())['failure_reason'], 'user_cancel')
            self.assertTrue(any('Retained Unreal source diagnostics' in n for n in raised.exception.__notes__))

    def test_nested_deadline_is_preserved_and_not_user_cancel(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); now = [0.]
            outer = _BudgetCancel(Event(), 3.)
            f.after_stage = lambda:now.__setitem__(0, 4.)
            with patch.object(preparation.time, 'monotonic', side_effect=lambda:now[0]):
                with self.assertRaisesRegex(ProjectStorageError, 'total deadline exceeded'):
                    self.run_case(f, cancel=outer)
            self.assertEqual(len(f.calls), 1)
            self.assertEqual(f.calls[0][2].deadline, 3.)
            self.assertLessEqual(f.calls[0][1], 3.)
            journal = f.store.root/'.ucc-jobs'/('unreal-source-'+f.request.job_id)/'preparation.json'
            self.assertEqual(json.loads(journal.read_bytes())['failure_reason'], 'total_deadline')

    def test_deadline_expiring_inside_initial_digest_normalizes_cause(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); now = [0.]
            def expire(*args):
                now[0] = 8.
                raise RuntimeError('raw hash cancellation')
            with patch.object(preparation.time, 'monotonic', side_effect=lambda:now[0]), patch.object(preparation, '_digest', side_effect=expire):
                with self.assertRaisesRegex(ProjectStorageError, 'total deadline exceeded') as raised:
                    self.run_case(f, timeout_s=7)
            self.assertIsInstance(raised.exception.__cause__, RuntimeError)
            self.assertFalse(f.calls)

    def test_full_original_proof_closure_addition_blocks_fresh_worker(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp))
            proof = f.store.root/'expressions/UNLISTED_NEW_PROOF.json'
            f.after_stage = lambda:proof.write_bytes(b'UNIT_NOT_REAL_PROOF')
            with self.assertRaisesRegex(ProjectConflict, 'proof/history changed'):
                self.run_case(f)
            self.assertEqual(len(f.calls), 1)

    def test_identical_byte_source_proof_replacement_is_rejected(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp))
            proof = next((f.store.root/'expressions').rglob('*.json'))
            old = proof.read_bytes()
            def replace_identity():
                replacement = proof.with_name('replacement.UNIT')
                replacement.write_bytes(old); replacement.replace(proof)
            f.after_stage = replace_identity
            with self.assertRaisesRegex(ProjectConflict, 'proof/history changed'):
                self.run_case(f)
            self.assertEqual(proof.read_bytes(), old)
            self.assertEqual(len(f.calls), 1)

    def test_helper_or_selected_mpfb_change_blocks_fresh_worker(self):
        for which in ('helper', 'data', 'executable'):
            with self.subTest(which=which), TemporaryDirectory() as temp:
                f = UnrealSourceFixture(Path(temp))
                path = f.worker if which == 'helper' else f.exe if which == 'executable' else f.data/'UNIT_NOT_REAL_DATA'
                f.after_stage = lambda:path.write_bytes(b'changed')
                with self.assertRaisesRegex(ProjectStorageError, 'helper or selected MPFB'):
                    self.run_case(f)
                self.assertEqual(len(f.calls), 1)

    def test_staged_or_fresh_fbx_corruption_never_admits_source(self):
        for which in ('stage', 'fresh'):
            with self.subTest(which=which), TemporaryDirectory() as temp:
                f = UnrealSourceFixture(Path(temp))
                def corrupt(inputs, folder):
                    path = inputs['character.fbx'] if which == 'stage' else folder/'character.fbx'
                    path.write_bytes(b'CORRUPTED_NOT_REAL_FBX')
                f.after_verify = corrupt
                with self.assertRaises(ProjectStorageError):
                    self.run_case(f)
                self.assertEqual(len(f.calls), 2)
                self.assertFalse((f.root/'descriptor.json').exists())

    def test_rebuilt_fbx_or_promoted_capability_proof_is_rejected(self):
        for key in ('exported_fbx_rebuilt', 'engine_import_verified', 'export_published'):
            with self.subTest(key=key), TemporaryDirectory() as temp:
                f = UnrealSourceFixture(Path(temp))
                f.alter_proof = lambda proof:proof.__setitem__(key, True)
                with self.assertRaises(ValidationError):
                    self.run_case(f)

    def test_same_byte_recipe_replacement_is_not_admitted(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp))
            recipe = f.store.root/'.ucc-jobs'/('unreal-source-'+f.request.job_id)/'unreal_source_recipe.json'
            def replace_recipe():
                replacement = recipe.with_name('REPLACEMENT_UNIT.json')
                replacement.write_bytes(recipe.read_bytes()); replacement.replace(recipe)
            f.after_stage = replace_recipe
            with self.assertRaisesRegex(ProjectStorageError, 'recipe changed'):
                self.run_case(f)
            self.assertEqual(len(f.calls), 1)

    def test_final_journal_replace_failure_leaves_truthful_failed_diagnostics(self):
        with TemporaryDirectory() as temp:
            f = UnrealSourceFixture(Path(temp)); real_replace = preparation.os.replace
            def fail_final(source, destination):
                if json.loads(Path(source).read_bytes())['state'] == 'UNREAL_SOURCE_VERIFIED_ENGINE_IMPORT_PENDING':
                    raise OSError('UNIT_FORCED_FINAL_JOURNAL_REPLACE_FAILURE')
                return real_replace(source, destination)
            with patch.object(preparation.os, 'replace', side_effect=fail_final):
                with self.assertRaisesRegex(OSError, 'UNIT_FORCED_FINAL_JOURNAL'):
                    self.run_case(f)
            work = f.store.root/'.ucc-jobs'/('unreal-source-'+f.request.job_id)
            journal = json.loads((work/'preparation.json').read_bytes())
            self.assertEqual(journal['state'], 'FAILED')
            self.assertEqual(journal['raw_error_type'], 'OSError')
            self.assertFalse(journal['export_published'])
            self.assertFalse((work/'preparation.tmp').exists())
            self.assertEqual(len(f.calls), 2)
