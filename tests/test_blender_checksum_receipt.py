"""Public metadata-only receipt boundaries; no network, archive or native execution."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.blender_checksum_receipt import CHECKSUM_URL, MAX_CHECKSUM_BYTES, make_receipt, main
from fixtures.ci_blender_checksum import SYNTHETIC_HEAD, SYNTHETIC_MANIFEST, SYNTHETIC_SHA

ROOT = Path(__file__).resolve().parents[1]


class BlenderChecksumReceiptTests(unittest.TestCase):
    def receipt(self, payload=SYNTHETIC_MANIFEST, **changes):
        arguments = dict(source_url=CHECKSUM_URL, effective_url=CHECKSUM_URL,
                         head_sha=SYNTHETIC_HEAD, run_id=123, run_attempt=1)
        arguments.update(changes)
        return make_receipt(payload, **arguments)

    def test_receipt_preserves_exact_public_bytes_and_is_metadata_only(self):
        value = self.receipt()
        self.assertEqual(value['archive_sha256'], SYNTHETIC_SHA)
        self.assertEqual(value['checksum_sha256'], hashlib.sha256(SYNTHETIC_MANIFEST).hexdigest())
        self.assertEqual(value['public_checksum_text'].encode('ascii'), SYNTHETIC_MANIFEST)
        self.assertEqual(value['checksum_bytes'], len(SYNTHETIC_MANIFEST))
        self.assertEqual(value['head_sha'], SYNTHETIC_HEAD)
        self.assertEqual((value['run_id'], value['run_attempt']), (123, 1))
        self.assertTrue(value['metadata_only'] and value['checksum_receipt_only_input'])
        self.assertEqual(value['workflow_event'], 'workflow_dispatch')
        self.assertIsNotNone(datetime.fromisoformat(value['recorded_utc']).tzinfo)
        for key in ('archive_downloaded', 'archive_integrity_verified', 'blender_installed_or_executed',
                    'domain_suites_executed', 'cache_pin_adopted'):
            self.assertIs(value[key], False)

    def test_missing_duplicate_malformed_and_html_responses_are_rejected(self):
        for payload in (b'', b'<html>403 Forbidden</html>', SYNTHETIC_MANIFEST * 2,
                        SYNTHETIC_MANIFEST.replace(b'a' * 64, b'a' * 63),
                        SYNTHETIC_MANIFEST.replace(b'  blender-5.3.0-linux', b'  ./blender-5.3.0-linux')):
            with self.subTest(payload_size=len(payload)), self.assertRaises(ValueError):
                self.receipt(payload)

    def test_checksum_payload_is_bounded_and_ascii(self):
        for payload in (b'x' * (MAX_CHECKSUM_BYTES + 1), SYNTHETIC_MANIFEST + b'\xff'):
            with self.assertRaises(ValueError):
                self.receipt(payload)

    def test_official_query_and_binary_checksum_marker_are_accepted(self):
        query = CHECKSUM_URL + '?ucc_ci=123-1-checksum-receipt'
        value = self.receipt(SYNTHETIC_MANIFEST.replace(b'  blender-5.3.0-linux', b' *blender-5.3.0-linux'),
                             source_url=query, effective_url=query)
        self.assertEqual(value['source_url'], query)
        self.assertEqual(value['archive_sha256'], SYNTHETIC_SHA)

    def test_other_origins_paths_credentials_protocols_and_queries_are_rejected(self):
        for url in (CHECKSUM_URL.replace('https:', 'http:'), CHECKSUM_URL.replace('download.', 'other.'),
                    CHECKSUM_URL.replace('.sha256', '.tar.xz'), CHECKSUM_URL + '#fragment',
                    CHECKSUM_URL.replace('https://', 'https://user@'), CHECKSUM_URL + '?unexpected=true'):
            for field in ('source_url', 'effective_url'):
                with self.subTest(field=field, url=url), self.assertRaises(ValueError):
                    self.receipt(**{field: url})

    def test_workflow_identity_is_required(self):
        for changes in ({'head_sha': 'main'}, {'run_id': True}, {'run_id': 0}, {'run_attempt': -1}):
            with self.assertRaises(ValueError):
                self.receipt(**changes)

    def test_cli_writes_once_and_has_no_network_or_execution(self):
        with tempfile.TemporaryDirectory(prefix='ucc-checksum-receipt-') as directory:
            root = Path(directory); source = root/'public.sha256'; source.write_bytes(SYNTHETIC_MANIFEST)
            output = root/'receipt.json'
            argv = ['--input', str(source), '--out', str(output), '--source-url', CHECKSUM_URL,
                    '--effective-url', CHECKSUM_URL, '--head-sha', SYNTHETIC_HEAD,
                    '--run-id', '123', '--run-attempt', '1']
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 0)
            accepted = output.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(argv), 2)
            self.assertEqual(output.read_bytes(), accepted)
            self.assertTrue(json.loads(accepted)['metadata_only'])
            with patch('pathlib.Path.is_symlink', return_value=True), redirect_stderr(io.StringIO()):
                self.assertEqual(main(argv), 2)

    def test_receipt_dispatch_is_separate_from_all_seven_domain_suites(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf8')
        self.assertIn('checksum_receipt_only:', text)
        self.assertIn('type: boolean\n        default: false', text)
        receipt = text.split('  record-blender-checksum:', 1)[1].split('  verify-mpfb-linux:', 1)[0]
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.checksum_receipt_only", receipt)
        self.assertIn('Metadata only', receipt)
        self.assertIn('--max-filesize 65536', receipt)
        self.assertIn("--proto '=https'", receipt)
        self.assertIn('--max-time 60 --retry-max-time 180', receipt)
        self.assertIn('ci/blender_checksum_receipt.py', receipt)
        self.assertIn('path: ${{ runner.temp }}/ucc-blender-checksum-receipt/receipt.json', receipt)
        self.assertNotIn('path: |', receipt)
        for forbidden in ('--insecure', 'extension install', 'tar -xf', 'run_mpfb_smoke.py'):
            self.assertNotIn(forbidden, receipt)
        domain = text.split('  verify-mpfb-linux:', 1)[1]
        self.assertIn('if: ${{ !inputs.checksum_receipt_only }}', domain)
        self.assertIn('fail-fast: false', domain)
        self.assertIn('suite: [regression, native-fit, body-contacts, symmetric-fit, regional-skin, source-references, reference-creator]', domain)
        self.assertIn('sha256sum --check --strict', domain)


if __name__ == '__main__':
    unittest.main()
