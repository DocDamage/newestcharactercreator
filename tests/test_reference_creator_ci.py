"""Closed aggregate and CI privacy contracts; no synthetic geometry proof."""
from copy import deepcopy
from pathlib import Path
import unittest

from ci.reference_creator_summary import STATUS, FLAGS, GUARDS, WORKERS, COUNTS, validate_summary

ROOT = Path(__file__).resolve().parents[1]


def summary():
    return {'status': STATUS, **{key: True for key in FLAGS}, **COUNTS,
        'positive_workers': deepcopy(WORKERS), 'guards': {key: True for key in GUARDS},
        'visual_quality_approved': False, 'engine_import_verified': False}


class ReferenceCreatorCIContracts(unittest.TestCase):
    def test_complete_closed_metadata_covers_every_operation(self):
        self.assertEqual(validate_summary(summary()), summary())
        self.assertEqual(sum(sum(v.values()) for v in WORKERS.values()), 156)
        self.assertEqual(len(GUARDS), 16)
        self.assertEqual(sum(v['inspect_fbx_animation'] for v in WORKERS.values())*300, 4800)

    def test_missing_unknown_and_non_boolean_claims_are_rejected(self):
        for key in summary():
            bad = summary(); bad.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError): validate_summary(bad)
        for key in FLAGS:
            for value in (False, 1, None):
                bad = summary(); bad[key] = value
                with self.subTest(flag=key, value=value), self.assertRaises(ValueError): validate_summary(bad)
        for key in ('poses', 'vertices', 'source_path', 'project_id', 'scene', 'cache', 'private_receipt'):
            bad = summary(); bad[key] = []
            with self.assertRaises(ValueError): validate_summary(bad)

    def test_partial_or_boolean_numeric_coverage_cannot_claim_acceptance(self):
        for key, count in COUNTS.items():
            for value in (True, False, count-1, count+1, float(count), None):
                bad = summary(); bad[key] = value
                with self.subTest(field=key, value=value), self.assertRaises(ValueError): validate_summary(bad)

    def test_missing_worker_group_or_any_worker_rejects(self):
        for group, counts in WORKERS.items():
            bad = summary(); bad['positive_workers'].pop(group)
            with self.assertRaises(ValueError): validate_summary(bad)
            for key, count in counts.items():
                for value in (True, count-1, count+1, float(count)):
                    bad = summary(); bad['positive_workers'][group][key] = value
                    with self.subTest(group=group, worker=key, value=value), self.assertRaises(ValueError): validate_summary(bad)
            bad = summary(); bad['positive_workers'][group]['unknown'] = 1
            with self.assertRaises(ValueError): validate_summary(bad)

    def test_every_guard_and_false_quality_boundary_is_required(self):
        for key in GUARDS:
            bad = summary(); bad['guards'].pop(key)
            with self.assertRaises(ValueError): validate_summary(bad)
            for value in (False, 1, None):
                bad = summary(); bad['guards'][key] = value
                with self.subTest(guard=key, value=value), self.assertRaises(ValueError): validate_summary(bad)
        for key in ('visual_quality_approved', 'engine_import_verified'):
            for value in (True, 0, None):
                bad = summary(); bad[key] = value
                with self.assertRaises(ValueError): validate_summary(bad)

    def test_seventh_suite_preserves_all_prior_routing_budgets_and_strict_checksum(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf-8')
        matrix = next(line for line in text.splitlines() if 'suite: [' in line)
        self.assertEqual(matrix.strip(), 'suite: [regression, native-fit, body-contacts, symmetric-fit, regional-skin, source-references, reference-creator]')
        for snippet in ("'native-fit' && 180", "'symmetric-fit' && 120", "'body-contacts' && 90",
                        "'regional-skin' && 90", "'source-references' && 90 || 120", "'reference-creator' && 90"):
            self.assertIn(snippet, text)
        self.assertIn('sha256sum --check --strict', text)
        for path in ('ci/verify_reference_creator.py', 'ci/reference_creator_*.py', 'tests/test_reference_creator_ci.py'):
            self.assertEqual(text.count("- '"+path+"'"), 2)
        self.assertIn("matrix.suite == 'reference-creator' && 'verify-reference-creator-linux'", text)
        self.assertIn("if: matrix.suite == 'reference-creator'", text)

    def test_new_artifact_is_one_exact_aggregate_path_and_sources_are_original_only(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf-8')
        artifact = text.split('path: |', 1)[1].split('if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in artifact.splitlines() if 'reference-creator' in line],
                         ['${{ runner.temp }}/ucc-reference-creator/reference_creator_summary.json'])
        self.assertNotIn('*', artifact)
        text = (ROOT/'ci/verify_reference_creator.py').read_text(encoding='utf-8')
        self.assertIn('tests/fixtures/blender_native_body.py', text)
        self.assertIn('tests/fixtures/blender_source_reference_faults.py', text)
        for path in (ROOT/'ci').glob('*reference_creator*.py'):
            text = path.read_text(encoding='utf-8')
            for forbidden in ('D:/', 'Motifect', 'pasted-text', 'unittest.mock', 'requests.', 'urlopen', 'pip install'):
                with self.subTest(path=path.name, forbidden=forbidden): self.assertNotIn(forbidden, text)


if __name__ == '__main__': unittest.main()
