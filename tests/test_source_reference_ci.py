"""Aggregate validation/privacy contracts; actual Blender evidence is separate."""
from pathlib import Path
import unittest

from ci.source_reference_summary import STATUS, FLAGS, FAULTS, WORKERS, validate_summary

ROOT = Path(__file__).resolve().parents[1]


def summary():
    return {'status': STATUS, **{key: True for key in FLAGS}, 'source_frames': 300,
        'source_bones': 71, 'catalog_source_workers': 2, 'complete_source_frame_observations': 3600,
        'positive_workers': dict(WORKERS), 'guards': {key: True for key in FAULTS},
        'visual_quality_approved': False, 'engine_import_verified': False}


class SourceReferenceCIContracts(unittest.TestCase):
    def test_complete_aggregate_retains_only_fixed_metadata(self):
        self.assertEqual(validate_summary(summary()), summary())
        self.assertEqual(sum(WORKERS.values()), 52)
        self.assertEqual(len(FAULTS), 6)

    def test_missing_false_boolean_and_unknown_aggregate_fields_reject(self):
        for key in summary():
            bad = summary(); bad.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): validate_summary(bad)
        for key in FLAGS:
            for value in (False, 1, None):
                bad = summary(); bad[key] = value
                with self.subTest(flag=key, value=value), self.assertRaises(ValueError): validate_summary(bad)
        for key in ('poses', 'vertices', 'cache', 'source_path'):
            bad = summary(); bad[key] = []
            with self.assertRaises(ValueError): validate_summary(bad)

    def test_partial_worker_fault_and_source_coverage_cannot_claim_success(self):
        cases = []
        for key in ('source_frames', 'source_bones', 'catalog_source_workers', 'complete_source_frame_observations'):
            for value in (True, 0, summary()[key]-1):
                bad = summary(); bad[key] = value; cases.append(bad)
        for key in WORKERS:
            bad = summary(); bad['positive_workers'][key] -= 1; cases.append(bad)
        for key in FAULTS:
            for value in (False, 1):
                bad = summary(); bad['guards'][key] = value; cases.append(bad)
        for bad in cases:
            with self.subTest(summary=bad), self.assertRaises(ValueError): validate_summary(bad)

    def test_source_reference_gate_never_grants_visual_or_engine_approval(self):
        for key in ('visual_quality_approved', 'engine_import_verified'):
            for value in (True, 0, None):
                bad = summary(); bad[key] = value
                with self.assertRaises(ValueError): validate_summary(bad)

    def test_sixth_suite_retains_existing_budgets_and_one_exact_summary(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf-8')
        self.assertIn('suite: [regression, native-fit, body-contacts, symmetric-fit, regional-skin, source-references, reference-creator]', text)
        for snippet in ("'native-fit' && 180", "'symmetric-fit' && 120", "'body-contacts' && 90",
                        "'regional-skin' && 90", "'source-references' && 90 || 120"):
            self.assertIn(snippet, text)
        self.assertIn('sha256sum --check --strict', text)
        for path in ('ci/verify_source_references.py', 'ci/source_reference_*.py',
                     'tests/fixtures/blender_source_reference_faults.py', 'src/ucc/core/commands.py',
                     'src/ucc/core/models.py', 'src/ucc/library/provenance.py'):
            self.assertEqual(text.count("- '"+path+"'"), 2)
        artifact = text.split('path: |', 1)[1].split('if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in artifact.splitlines() if 'source-references' in line],
                         ['${{ runner.temp }}/ucc-source-references/source_reference_summary.json'])
        self.assertNotIn('*', artifact)

    def test_ci_sources_use_original_fixture_and_no_owner_paths(self):
        text = (ROOT/'ci/verify_source_references.py').read_text(encoding='utf-8')
        self.assertIn("tests/fixtures/blender_native_body.py", text)
        for path in ('ci/verify_source_references.py', 'ci/source_reference_checks.py',
                     'ci/source_reference_summary.py', 'tests/fixtures/blender_source_reference_faults.py', 'src/ucc/core/commands.py',
                     'src/ucc/core/models.py', 'src/ucc/library/provenance.py'):
            text = (ROOT/path).read_text(encoding='utf-8')
            for forbidden in ('D:/', 'Motifect', 'pasted-text', 'unittest.mock'):
                self.assertNotIn(forbidden, text)


if __name__ == '__main__': unittest.main()
