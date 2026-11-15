"""Closed aggregate and CI privacy contracts; no synthetic geometry proof."""
from copy import deepcopy
from pathlib import Path
import unittest

from ci.plain_reference_summary import STATUS, FLAGS, GUARDS, WORKERS, COUNTS, validate_summary

ROOT = Path(__file__).resolve().parents[1]


def summary():
    return {'status': STATUS, **{key: True for key in FLAGS}, **COUNTS,
        'positive_workers': deepcopy(WORKERS), 'guards': {key: True for key in GUARDS},
        'visual_quality_approved': False, 'engine_import_verified': False}


class PlainReferenceCIContracts(unittest.TestCase):
    def test_complete_closed_metadata_covers_every_operation(self):
        self.assertEqual(validate_summary(summary()), summary())
        self.assertEqual(sum(sum(v.values()) for v in WORKERS.values()), 112)
        self.assertEqual(len(GUARDS), 13)
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

    def test_existing_job_adds_only_the_explicit_plain_summary(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf-8')
        matrix = next(line for line in text.splitlines() if 'suite: [' in line)
        self.assertEqual(matrix.strip(), 'suite: [regression, native-fit, body-contacts, symmetric-fit, regional-skin, source-references, reference-creator]')
        job = text.split('- name: Verify original reference-aware', 1)[1].split('- name:', 1)[0]
        self.assertIn("if: matrix.suite == 'reference-creator'", job)
        self.assertLess(job.index('ci/verify_reference_creator.py'), job.index('ci/verify_plain_reference.py'))
        self.assertIn('--outdir "$RUNNER_TEMP/ucc-plain-reference"', job)
        for path in ('ci/verify_plain_reference.py', 'ci/plain_reference_*.py', 'tests/test_plain_reference_ci.py'):
            self.assertEqual(text.count("- '"+path+"'"), 2)
        artifact = text.split('path: |', 1)[1].split('if-no-files-found:', 1)[0]
        self.assertEqual([line.strip() for line in artifact.splitlines() if 'plain-reference' in line],
                         ['${{ runner.temp }}/ucc-plain-reference/plain_reference_summary.json'])
        self.assertNotIn('*', artifact)
        self.assertIn('sha256sum --check --strict', text)

    def test_portable_entrypoint_imports_and_help_without_blender(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(ROOT/'ci/verify_plain_reference.py'), '--help'],
                                capture_output=True, text=True, timeout=30, cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--blender', result.stdout)
        self.assertIn('--outdir', result.stdout)

    def test_harness_has_no_personal_paths_or_networking(self):
        for path in (ROOT/'ci').glob('*plain_reference*.py'):
            text = path.read_text(encoding='utf-8')
            for forbidden in ('D:/', 'C:/Users/', 'pasted-text', 'requests.', 'urlopen', 'pip install'):
                with self.subTest(path=path.name, forbidden=forbidden):
                    self.assertNotIn(forbidden, text)
        setup = (ROOT/'ci/plain_reference_setup.py').read_text(encoding='utf-8')
        self.assertIn('tests/fixtures/blender_native_body.py', setup)
        self.assertIn('no_ai=True', setup)
        self.assertNotIn('prepare_saved_expressions', setup)

    def test_existing_output_is_preserved_before_any_blender_work(self):
        import tempfile
        from ci.verify_plain_reference import verify
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder); marker = out/'owner.txt'
            marker.write_bytes(b'preserve existing evidence')
            with self.assertRaises(FileExistsError):
                verify(Path('not-an-installed-blender'), out)
            self.assertEqual(marker.read_bytes(), b'preserve existing evidence')
            self.assertEqual(set(out.iterdir()), {marker})


if __name__ == '__main__': unittest.main()
