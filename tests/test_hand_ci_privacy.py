"""CI retention boundaries: generated scenes/poses stay outside artifacts."""
from pathlib import Path
import unittest


class HandArtifactPrivacyTests(unittest.TestCase):
    def test_only_explicit_summary_json_paths_are_retained(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/mpfb-cloud-smoke.yml').read_text()
        paths=text.split('          path: |',1)[1].split('          if-no-files-found:',1)[0]
        retained=[row.strip() for row in paths.splitlines() if row.strip()]
        approved={'ucc-mpfb-smoke/summary.json','ucc-mpfb-smoke/mpfb_create_result.json',
                  'ucc-mpfb-smoke/reopen_result.json','ucc-production-worker/production_summary.json',
                  'ucc-project-integration/transaction_summary.json','ucc-custom-face/custom_face_summary.json',
                  'ucc-hand-parts/hand_parts_summary.json','ucc-expressions/expression_summary.json',
                  'ucc-native-fit/native_fit_summary.json',
                  'ucc-body-contacts/body_contact_summary.json','ucc-symmetric-math.json',
                  'ucc-symmetric-fit/symmetric_fit_summary.json'}
        self.assertEqual(set(retained),{'${{ runner.temp }}/'+path for path in approved})
        self.assertEqual(len(retained),len(approved))
        self.assertIn('${{ runner.temp }}/ucc-hand-parts/hand_parts_summary.json',retained)
        self.assertIn('${{ runner.temp }}/ucc-custom-face/custom_face_summary.json',retained)
        self.assertTrue(all(row.endswith('.json') and '*' not in row for row in retained))
        self.assertFalse(any(row.rsplit('/',1)[-1] in {'request.json','result.json',
                             'hand_revision_report.json','hand_assets_report.json'} for row in retained))
        self.assertLess(text.index('python3 ci/verify_custom_face.py'),text.index('python3 ci/verify_hand_parts.py'))
        self.assertIn('--source-root "$RUNNER_TEMP/ucc-custom-face"',text)
        self.assertLess(text.index('python3 ci/verify_hand_parts.py'), text.index('python3 ci/verify_expressions.py'))
        self.assertIn('--source-root "$RUNNER_TEMP/ucc-hand-parts"', text)


if __name__=='__main__':unittest.main()
