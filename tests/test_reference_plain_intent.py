"""Synthetic two-read-back contracts; never actual MPFB acceptance."""
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.reference_plain_master_contract import PlainReferenceMasterFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.reference_plain_intent import inspect_plain_body_intent


class PlainBodyIntentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.f = PlainReferenceMasterFixture(Path(temporary.name).resolve(), hand=False)
        self.store = self.f.store; self.calls = []; self.after_copy = None
        self.report = dict(macro_parameters_observed={'height': .5, 'muscle': .5, 'weight': .5},
            macro_evaluated_vertices=1000, macro_evaluated_sha256='a'*64,
            macro_active_shape_keys=1, macro_shape_evaluated=True,
            visual_deformation_verified=False, engine_import_verified=False)
        runner = SimpleNamespace(run=self.run_worker)
        self.factory = patch('ucc.jobs.reference_plain_intent.BlenderJobRunner', return_value=runner).start()
        self.addCleanup(patch.stopall)

    def run_worker(self, request, *, staged_inputs, **kwargs):
        self.calls.append(request)
        directory = self.store.root/'.ucc-jobs'/('unit-read-'+str(len(self.calls)))
        directory.mkdir(parents=True)
        copied = directory/'plain_candidate.blend'
        copied.write_bytes(staged_inputs['plain_candidate.blend'].read_bytes())
        details = dict(self.report)
        if self.after_copy: self.after_copy(copied, details)
        return SimpleNamespace(details=details), directory

    def inspect(self):
        return inspect_plain_body_intent(self.store, cancel=None, timeout_s=30, **self.f.kwargs())

    def test_two_fresh_staged_readbacks_must_agree_with_saved_parameters(self):
        before = self.store.file.read_bytes(); proof = self.inspect()
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(job.operation == 'inspect_character' for job in self.calls))
        self.assertTrue(all(job.options == {'macro_parameters': {'height': .5, 'muscle': .5, 'weight': .5}}
                            for job in self.calls))
        self.assertTrue(proof['morph_save_reopen_verified'])
        self.assertFalse(proof['engine_import_verified']); self.assertEqual(self.store.file.read_bytes(), before)

    def test_wrong_macro_in_second_readback_is_rejected(self):
        def fault(path, details):
            if len(self.calls) == 2:
                details['macro_parameters_observed'] = {'height': .6, 'muscle': .5, 'weight': .5}
        self.after_copy = fault
        with self.assertRaises(ValidationError): self.inspect()

    def test_different_evaluated_geometry_between_readbacks_is_rejected(self):
        def fault(path, details):
            if len(self.calls) == 2: details['macro_evaluated_sha256'] = 'b'*64
        self.after_copy = fault
        with self.assertRaises(ValidationError): self.inspect()

    def test_changed_actual_staged_input_is_rejected(self):
        self.after_copy = lambda path, details: path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(ProjectStorageError): self.inspect()
        self.assertEqual(len(self.calls), 1)

    def test_external_metadata_save_is_preserved_and_stops_second_worker(self):
        def save(path, details):
            current = self.store.load()
            self.store.save(replace(current, name='External edit', revision=current.revision+1),
                            expected_revision=current.revision)
        self.after_copy = save
        with self.assertRaises(ProjectConflict): self.inspect()
        self.assertEqual(len(self.calls), 1); self.assertEqual(self.store.load().name, 'External edit')
