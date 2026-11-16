"""Structural transaction/storage fixtures only; not real deformation evidence."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from ucc.core.commands import CharacterSession
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import (build_expression_manifest, canonical_digest,
                                         source_intent, validate_expression_manifest,
                                         build_expression_receipt, validate_expression_receipt)
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.expression_keys import PreparedExpressionKeys
from ucc.jobs.expression_inspection import CheckedExpressionMaster
from ucc.jobs.expression_revisions import publish_expression_receipt, read_expression_receipt, admit_expression_source
from ucc.jobs.expression_verification import verify_saved_expression_master
from ucc.jobs.expression_preparation import prepare_saved_expressions
from ucc.jobs.expression_storage import (install_master_copy, load_expression_library,
                                          publish_library, safe_directory)


class ExpressionPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.worker = self.root/'worker'; self.worker.mkdir()
        self.store = ProjectStore(self.root/'project'); self.store.root.mkdir()
        self.original = self.worker/'original.blend'
        self.original.write_bytes(b'BLENDER'+b'original-structural-fixture-not-real-geometry'*100)
        self.original_sha = sha256(self.original.read_bytes()).hexdigest()
        install_master_copy(self.store, self.original, self.original_sha, self.worker)
        self.initial = self.store.save(replace(CharacterProject.new('Structural expression transaction only'),
            master_blend='master/versions/'+self.original_sha+'.blend', geometry_state='generated_unverified'))
        self.before = self.store.file.read_bytes()
        self.prepared = self.worker/'prepared.blend'
        self.prepared.write_bytes(b'BLENDER'+b'prepared-structural-fixture-not-real-geometry'*100)
        prepared_sha = sha256(self.prepared.read_bytes()).hexdigest()
        self.recipe = build_expression_recipe(self.original_sha)
        self.observation = {'fixture': 'NOT_DEFORMATION_EVIDENCE'}
        self.report = self.worker/'report.json'
        self.report.write_text(json.dumps({'source_master_sha256': self.original_sha,
            'prepared_sha256': prepared_sha, 'policy': self.recipe['policy'], 'observation': self.observation,
            'visual_quality_approved': False, 'engine_import_verified': False}))
        self.keys = PreparedExpressionKeys(self.original_sha, self.prepared, prepared_sha, self.report,
            sha256(self.report.read_bytes()).hexdigest(), self.recipe, canonical_digest(self.observation),
            {'fixture_only': True}, 'structural-stage', 'structural-verify')
        self.common = dict(blender_exe=self.worker/'not-used.exe', worker_script=self.worker/'not-used.py',
            mpfb_data_dir=self.worker/'not-used-data', expected_project_id=self.initial.project_id,
            expected_revision=self.initial.revision, expected_master_blend=self.initial.master_blend)

    def prepare(self, side_effect=None, **kwargs):
        with (patch('ucc.jobs.expression_preparation.installed_expression_inputs', return_value={}),
              patch('ucc.jobs.expression_preparation.stage_expression_keys',
                    side_effect=side_effect, return_value=self.keys)):
            return prepare_saved_expressions(self.store, **self.common, **kwargs)

    def manifest(self):
        return build_expression_manifest(source_intent(self.initial), self.recipe, self.keys.sha256,
                                          self.keys.report_sha256, self.keys.observation_sha256)

    def structural_revision(self, name):
        path = self.worker/(name+'.blend')
        path.write_bytes(self.prepared.read_bytes()+name.encode())
        digest = sha256(path.read_bytes()).hexdigest()
        master = install_master_copy(self.store, path, digest, self.worker)
        proof = {'schema_version': 1, 'master_sha256': digest, 'expression_keys_sha256': 'c'*64,
                 'policy': self.recipe['policy'], 'recipe_sha256': canonical_digest(build_expression_recipe(digest)),
                 'sample_count': 20,
                 'observation': {'structural_only': name}, 'exact_neutral_restoration': True,
                 'visual_quality_approved': False, 'engine_import_verified': False}
        report = self.worker/(name+'.json'); report.write_text(json.dumps(proof))
        return CheckedExpressionMaster(master, digest, proof, report, sha256(report.read_bytes()).hexdigest(),
                                       'structural-not-a-real-worker', 'structural-not-a-real-worker')

    def test_complete_metadata_commits_once_and_has_one_step_history(self):
        result = self.prepare(); saved = self.store.load()
        self.assertEqual(saved, result.project); self.assertEqual(saved.revision, self.initial.revision+1)
        self.assertTrue(saved.expression.neutral); self.assertEqual(saved.schema_version, 3)
        library = load_expression_library(self.store, result.library_sha256)
        self.assertEqual(library.original_master.read_bytes(), self.original.read_bytes())
        self.assertEqual(library.prepared_master.read_bytes(), self.prepared.read_bytes())
        session = CharacterSession(self.initial)
        session.accept_saved_expression_master(saved, library_sha256=result.library_sha256)
        self.assertEqual(replace(session.undo(), revision=self.initial.revision), self.initial)
        self.assertEqual(replace(session.redo(), revision=saved.revision), saved)

    def test_manifest_and_copy_registration_do_not_change_project_pointer(self):
        install_master_copy(self.store, self.prepared, self.keys.sha256, self.worker)
        identity = publish_library(self.store, self.manifest(), self.report)
        self.assertEqual(publish_library(self.store, self.manifest(), self.report), identity)
        self.assertEqual(load_expression_library(self.store, identity).sha256, identity)
        self.assertEqual(self.store.file.read_bytes(), self.before)
        self.assertEqual(self.store.load(), self.initial)

    def test_manifest_is_closed_and_cannot_expand_rights(self):
        for change in (lambda r: r.update(schema_version=True), lambda r: r.update(extra=True),
                lambda r: r['rights'].update(no_ai=False), lambda r: r['rights'].update(ai_input_allowed=True),
                lambda r: r['rights'].update(engine_export_authorized=True),
                lambda r: r['rights'].update(ai_input_allowed=float('nan')),
                lambda r: r['recipe']['targets'][0].update(file='../elsewhere'),
                lambda r: r.update(prepared_master_sha256=self.original_sha),
                lambda r: r['source'].update(height_m=True),
                lambda r: r['source'].update(height_m=10**1000),
                lambda r: r['source']['body_parameters'].update(unknown=.5)):
            raw = deepcopy(self.manifest()); change(raw)
            with self.subTest(raw=raw), self.assertRaises(ValidationError): validate_expression_manifest(raw)

    def test_library_schema_matches_closed_provenance(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema not installed')
        path = Path(__file__).resolve().parents[1]/'docs/schemas/expression-library.v1.schema.json'
        schema = json.loads(path.read_text()); Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema); manifest = self.manifest(); validator.validate(manifest)
        for field in manifest:
            broken = deepcopy(manifest); del broken[field]
            self.assertTrue(list(validator.iter_errors(broken)))
        for change in (lambda r: r['rights'].update(ai_input_allowed=True),
                lambda r: r['recipe']['targets'][0].update(key='Basis'),
                lambda r: r.update(extra=True), lambda r: r['source'].update(height_m=True)):
            broken = deepcopy(manifest); change(broken)
            self.assertTrue(list(validator.iter_errors(broken)))

    def test_worker_failure_cancellation_and_external_edit_preserve_old_pointer(self):
        with self.assertRaises(RuntimeError): self.prepare(side_effect=RuntimeError('worker failed'))
        self.assertEqual(self.store.file.read_bytes(), self.before)
        cancel = Event(); cancel.set()
        with self.assertRaises(ProjectStorageError): self.prepare(cancel=cancel)
        self.assertEqual(self.store.file.read_bytes(), self.before)
        def conflict(*args, **kwargs):
            raw = json.loads(self.store.file.read_text()); raw['name'] = 'external retained'
            self.store.file.write_text(json.dumps(raw)); return self.keys
        with self.assertRaises(ProjectConflict): self.prepare(side_effect=conflict)
        self.assertEqual(self.store.load().name, 'external retained')
        self.assertEqual(self.store.load().master_blend, self.initial.master_blend)

    def test_changed_prepared_output_and_source_are_rejected(self):
        for path in (self.prepared, self.store.root/self.initial.master_blend):
            original = path.read_bytes(); path.write_bytes(original+b'changed')
            with self.subTest(path=path), self.assertRaises(ProjectStorageError): self.prepare()
            self.assertEqual(self.store.file.read_bytes(), self.before); path.write_bytes(original)

    def test_source_removed_after_worker_returns_has_explicit_storage_error(self):
        def removed(*args, **kwargs):
            (self.store.root/self.initial.master_blend).unlink()
            return self.keys
        with self.assertRaisesRegex(ProjectStorageError, 'missing'):
            self.prepare(side_effect=removed)
        self.assertEqual(self.store.file.read_bytes(), self.before)

    def test_registered_library_changed_during_final_master_copy_blocks_commit(self):
        from ucc.core.master_versions import stage_unverified_master
        def corrupt_before_commit(*args, **kwargs):
            library = next((self.store.root/'expressions/manifests').glob('*.json'))
            library.write_bytes(library.read_bytes()+b'changed after registration')
            return stage_unverified_master(*args, **kwargs)
        with patch('ucc.jobs.expression_preparation.stage_unverified_master', side_effect=corrupt_before_commit):
            with self.assertRaises(ProjectStorageError): self.prepare()
        self.assertEqual(self.store.file.read_bytes(), self.before)

    def test_immutable_master_copy_rejects_overwrite_cancel_and_escape(self):
        cancel = Event(); cancel.set()
        with self.assertRaises(ProjectStorageError):
            install_master_copy(self.store, self.prepared, self.keys.sha256, self.worker, cancel)
        with self.assertRaises(ProjectStorageError):
            install_master_copy(self.store, self.prepared, self.original_sha, self.worker)
        for component in ('..', '../elsewhere', '', 'master/versions'):
            with self.assertRaises(ValidationError): safe_directory(self.store, component, create=True)
        self.assertEqual(self.store.file.read_bytes(), self.before)

    def test_corrupt_registered_manifest_report_and_provenance_master_reject(self):
        result = self.prepare(); library = load_expression_library(self.store, result.library_sha256)
        for path in (library.manifest_path, library.report_path, library.original_master, library.prepared_master):
            original = path.read_bytes(); path.write_bytes(original+b'changed')
            with self.subTest(path=path), self.assertRaises(ProjectStorageError):
                load_expression_library(self.store, result.library_sha256)
            path.write_bytes(original)

    def test_already_prepared_and_stale_calls_cannot_reregister_or_mutate(self):
        self.prepare(); before = self.store.file.read_bytes(); saved = self.store.load()
        with self.assertRaises(ProjectConflict): self.prepare()
        current = dict(self.common, expected_revision=saved.revision, expected_master_blend=saved.master_blend)
        with self.assertRaisesRegex(ValidationError, 'already prepared'):
            prepare_saved_expressions(self.store, **current)
        self.assertEqual(self.store.file.read_bytes(), before)

    def test_expression_revision_registration_is_closed_bound_and_pointer_neutral(self):
        ready = self.prepare(); library = load_expression_library(self.store, ready.library_sha256)
        before = self.store.file.read_bytes(); checked = self.structural_revision('first-revision')
        receipt = publish_expression_receipt(self.store, library, self.keys.sha256, checked, 'body_refit')
        self.assertEqual(read_expression_receipt(self.store, library, checked.sha256), receipt)
        self.assertEqual(admit_expression_source(self.store, library, checked.sha256), receipt)
        self.assertIsNone(admit_expression_source(self.store, library, self.keys.sha256))
        self.assertEqual(self.store.file.read_bytes(), before)
        for change in (lambda r: r.update(schema_version=True), lambda r: r.update(extra=True),
                lambda r: r.update(source_master_sha256=r['master_sha256']),
                lambda r: r.update(operation='arbitrary_external_adoption'),
                lambda r: r.update(inspection_sha256='../elsewhere')):
            raw = deepcopy(receipt); change(raw)
            with self.subTest(raw=raw), self.assertRaises(ValidationError): validate_expression_receipt(raw)

    def test_expression_revision_schema_is_closed_and_matches_receipt(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema not installed')
        path = Path(__file__).resolve().parents[1]/'docs/schemas/expression-revision.v1.schema.json'
        validator = Draft202012Validator(json.loads(path.read_text()))
        receipt = build_expression_receipt('a'*64, 'b'*64, 'c'*64, 'body_refit', 'd'*64, 'e'*64, 'f'*64)
        validator.validate(receipt)
        for field in receipt:
            broken = deepcopy(receipt); del broken[field]
            self.assertTrue(list(validator.iter_errors(broken)))
        for edit in (lambda r: r.update(operation='external_adoption'), lambda r: r.update(extra=True),
                     lambda r: r.update(master_sha256='../elsewhere')):
            broken = deepcopy(receipt); edit(broken)
            self.assertTrue(list(validator.iter_errors(broken)))

    def test_missing_expression_receipt_blocks_unknown_master_before_any_worker(self):
        ready = self.prepare(); checked = self.structural_revision('unknown-master')
        current = self.store.load(); unknown = self.store.save(replace(current, revision=current.revision+1,
            master_blend='master/versions/'+checked.sha256+'.blend'), expected_revision=current.revision)
        before = self.store.file.read_bytes()
        with patch('ucc.jobs.expression_verification._inspect_expression_copy', side_effect=AssertionError('must not launch')):
            with self.assertRaisesRegex(ProjectStorageError, 'receipt'):
                verify_saved_expression_master(self.store, blender_exe=Path('not-used'), worker_script=Path('not-used'),
                    mpfb_data_dir=Path('not-used'), expected_project_id=unknown.project_id,
                    expected_revision=unknown.revision, expected_master_blend=unknown.master_blend)
        self.assertEqual(self.store.file.read_bytes(), before)

    def test_corrupt_revision_report_and_cyclic_provenance_are_rejected(self):
        ready = self.prepare(); library = load_expression_library(self.store, ready.library_sha256)
        first = self.structural_revision('cycle-first'); second = self.structural_revision('cycle-second')
        publish_expression_receipt(self.store, library, second.sha256, first, 'body_refit')
        publish_expression_receipt(self.store, library, first.sha256, second, 'face_revision')
        with self.assertRaisesRegex(ProjectStorageError, 'Cyclic'):
            admit_expression_source(self.store, library, first.sha256)
        path = self.store.root/'expressions/inspections'/(first.report_sha256+'.json')
        path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(ProjectStorageError): read_expression_receipt(self.store, library, first.sha256)
