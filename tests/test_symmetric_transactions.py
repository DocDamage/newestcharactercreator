"""Layer transaction boundaries with mock-worker files; no Blender claim."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import unittest

import test_native_fit_coordinator as legacy
from ucc.animations.contact_fit import HASHES
from ucc.core.errors import ValidationError
from ucc.jobs.symmetric_fit_evidence import layer_base_inputs, cached_base_inputs


class SymmetricTransactionTests(unittest.TestCase):
    def setUp(self):
        self.f = legacy.NativeFitCoordinatorTests('test_three_distinct_staged_jobs_and_png_checks_precede_candidate_publication')
        self.f.setUpClass(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.base = self.f.fit(); self.jobs = self.f.store.root/'.ucc-jobs'
        self.identities = {k: self.base.verification['bindings'][k] for k in HASHES}

    def inputs(self, base=None, **kwargs):
        return layer_base_inputs(self.base if base is None else base, self.f.preview, self.jobs, self.identities,
                                 self.f.base, self.f.profile, **kwargs)

    def test_independent_legacy_base_evidence_is_bound_before_any_layer_worker(self):
        paths, expected = self.inputs()
        self.assertEqual(set(paths), {'base_contact_fit.json', 'base_fitted_motion.blend', 'base_fitted_timeline.json'})
        self.assertEqual({n: sha256(p.read_bytes()).hexdigest() for n, p in paths.items()}, expected)
        self.assertEqual(self.f.store.load(), self.f.project)

    def test_other_source_character_revision_and_partial_base_bindings_reject(self):
        for field, value in (('project_id', 'other'), ('revision', self.base.revision+1), ('master_sha256', 'f'*64),
                             ('source_sha256', 'f'*64), ('fit_policy_sha256', 'f'*64), ('fitted_scene_sha256', 'f'*64)):
            with self.subTest(field=field), self.assertRaises(ValidationError): self.inputs(replace(self.base, **{field: value}))
        bad = deepcopy(self.base.verification); del bad['bindings']['fit_report_sha256']
        with self.assertRaises(ValidationError): self.inputs(replace(self.base, verification=bad))

    def test_each_changed_base_file_rejects_before_a_new_worker(self):
        paths, _ = self.inputs()
        for name, path in paths.items():
            before = path.read_bytes(); path.write_bytes(b'CHANGED_UNIT_INPUT')
            try:
                with self.subTest(name=name), self.assertRaises(ValidationError): self.inputs()
            finally: path.write_bytes(before)

    def test_redirected_out_of_project_scene_and_forged_base_receipt_reject(self):
        external = self.f.root/'foreign.blend'; external.write_bytes(Path(self.base.private_fitted_scene).read_bytes())
        with self.assertRaises(ValidationError): self.inputs(replace(self.base, private_fitted_scene=str(external)))
        bad = deepcopy(self.base.verification); bad['frames_verified'] -= 1
        with self.assertRaises(ValidationError): self.inputs(replace(self.base, verification=bad))

    def test_cancellation_interrupts_base_intake(self):
        def cancelled(): raise RuntimeError('cancel-base-intake')
        with self.assertRaisesRegex(RuntimeError, 'cancel-base-intake'): self.inputs(cancel_check=cancelled)

    def test_cache_base_inputs_require_one_private_worker_directory(self):
        options = {'base_fit_policy_sha256': 'a'*64, 'base_fitted_sha256': 'b'*64, 'base_fit_report_sha256': 'c'*64}
        folder = Path(self.base.private_fitted_scene).parent
        paths, identities = cached_base_inputs(folder, options, self.jobs)
        self.assertEqual(identities['base_fitted_motion.blend'], 'b'*64)
        self.assertEqual(paths['base_contact_fit.json'], folder/'base_contact_fit.json')
        with self.assertRaises(ValidationError): cached_base_inputs(self.f.root, options, self.jobs)


if __name__ == '__main__': unittest.main()
