"""Pinned cache boundaries with invented bytes; no network or Blender is run."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.blender_archive_cache import (
    ARCHIVE_NAME, ARCHIVE_SHA256, CACHE_KEY, CHECKSUM_NAME, CHECKSUM_SHA256,
    check_restore, checksum_entry, curl_failure_code, main, verify_cache,
)
from fixtures.ci_blender_checksum import SYNTHETIC_ARCHIVE

ROOT = Path(__file__).resolve().parents[1]


class BlenderArchiveCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ucc-public-cache-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root/'archive'; self.directory.mkdir()
        self.archive_sha = hashlib.sha256(SYNTHETIC_ARCHIVE).hexdigest()
        self.manifest = (self.archive_sha + '  ' + ARCHIVE_NAME + '\n').encode('ascii')
        self.manifest_sha = hashlib.sha256(self.manifest).hexdigest()
        (self.directory/ARCHIVE_NAME).write_bytes(SYNTHETIC_ARCHIVE)
        (self.directory/CHECKSUM_NAME).write_bytes(self.manifest)

    def verify(self, **changes):
        arguments = dict(_archive_sha=self.archive_sha, _checksum_sha=self.manifest_sha)
        arguments.update(changes)
        return verify_cache(self.directory, **arguments)

    def test_exact_two_member_bytes_pass_without_execution(self):
        result = self.verify()
        self.assertEqual(result['archive_sha256'], self.archive_sha)
        self.assertEqual(result['checksum_sha256'], self.manifest_sha)
        self.assertEqual(result['archive_bytes'], len(SYNTHETIC_ARCHIVE))
        self.assertIs(result['archive_integrity_verified'], True)
        self.assertIs(result['blender_executed'], False)
        self.assertIs(result['domain_suites_verified'], False)

    def test_wrong_archive_hash_rejects_instead_of_adopting_new_bytes(self):
        (self.directory/ARCHIVE_NAME).write_bytes(SYNTHETIC_ARCHIVE + b'changed')
        with self.assertRaisesRegex(ValueError, 'archive SHA-256'):
            self.verify()

    def test_changed_manifest_bytes_reject_even_with_same_archive_entry(self):
        (self.directory/CHECKSUM_NAME).write_bytes(self.manifest + b'\n')
        with self.assertRaisesRegex(ValueError, 'checksum bytes'):
            self.verify()

    def test_entry_is_checked_independently_of_manifest_hash(self):
        changed = self.manifest.replace(self.archive_sha.encode(), b'a' * 64)
        (self.directory/CHECKSUM_NAME).write_bytes(changed)
        with self.assertRaisesRegex(ValueError, 'Linux entry'):
            self.verify(_checksum_sha=hashlib.sha256(changed).hexdigest())

    def test_missing_duplicate_and_malformed_entries_reject(self):
        for payload in (b'no Linux entry\n', self.manifest * 2,
                        self.manifest.replace(b'  blender-', b'  ./blender-')):
            with self.subTest(bytes=len(payload)), self.assertRaises(ValueError):
                checksum_entry(payload)

    def test_missing_or_extra_cache_members_reject(self):
        missing = self.directory/CHECKSUM_NAME; missing.unlink()
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.verify()
        missing.write_bytes(self.manifest)
        (self.directory/'private-profile').mkdir()
        with self.assertRaisesRegex(ValueError, 'exactly'):
            self.verify()

    def test_symlink_member_mode_rejects_before_member_open(self):
        original = Path.lstat; target = self.directory/ARCHIVE_NAME
        def filesystem_entry(path):
            if path == target:
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_nlink=1, st_size=12)
            return original(path)
        with patch.object(Path, 'lstat', filesystem_entry):
            with self.assertRaisesRegex(ValueError, 'regular, single-link'):
                self.verify()

    def test_actual_hardlinked_cache_member_is_rejected(self):
        os.link(self.directory/ARCHIVE_NAME, self.root/'outside-linked-member')
        with self.assertRaisesRegex(ValueError, 'regular, single-link'):
            self.verify()

    def test_member_bound_is_checked_before_hashing(self):
        with patch('ci.blender_archive_cache.MAX_ARCHIVE_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'bounded'):
                self.verify()

    def test_only_exact_restore_hit_or_explicit_producer_miss_is_allowed(self):
        check_restore('true', CACHE_KEY)
        check_restore('false', '', allow_miss=True)
        check_restore('', '', allow_miss=True)
        for hit, key in [('false', ''), ('', ''), ('true', CACHE_KEY + '-other'),
                         ('false', CACHE_KEY), ('true', CACHE_KEY[:-10])]:
            with self.subTest(hit=hit, key=key), self.assertRaises(ValueError):
                check_restore(hit, key)
        for hit, key in [('false', CACHE_KEY), ('true', CACHE_KEY + '-other')]:
            with self.assertRaises(ValueError):
                check_restore(hit, key, allow_miss=True)

    def test_cli_does_not_allow_fixture_or_caller_supplied_pins(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(['verify', '--directory', str(self.directory)]), 2)
            with self.assertRaises(SystemExit) as failure:
                main(['verify', '--directory', str(self.directory), '--archive-sha', self.archive_sha])
        self.assertEqual(failure.exception.code, 2)

    def test_only_explicit_curl_transport_failures_allow_fallback(self):
        for status in (5, 6, 7, 18, 22, 28, 35, 47, 52, 55, 56):
            self.assertEqual(curl_failure_code(status), 10)
        for status in (1, 2, 3, 23, 26, 27, 60, 63, 77, 92, 95, 99, 255):
            self.assertEqual(curl_failure_code(status), 20)
        for status in (0, -1, True, 256):
            with self.assertRaises(ValueError):
                curl_failure_code(status)
        for status, expected in ((22, 10), (23, 20), (60, 20), (63, 20)):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['classify-curl', '--exit-code', str(status)]), 0)
            self.assertEqual(output.getvalue().strip(), str(expected))
        text = (ROOT/'ci/fetch_blender_archive.sh').read_text(encoding='utf8')
        self.assertNotIn('if ! curl', text)
        self.assertEqual(text.count('status="$?"'), 2)
        self.assertEqual(text.count('classify_curl_failure "$status"'), 2)

    def test_versioned_key_contains_reviewed_official_digest(self):
        self.assertIn(ARCHIVE_SHA256, CACHE_KEY)
        self.assertIn(CHECKSUM_SHA256, CACHE_KEY)
        self.assertIn('linux-x64-5.3.0', CACHE_KEY)
        self.assertEqual(len(ARCHIVE_SHA256), 64)
        self.assertEqual(len(CHECKSUM_SHA256), 64)

    def test_producer_and_consumers_keep_cache_and_domain_boundaries(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf8')
        producer = text.split('  prepare-blender-linux:', 1)[1].split('  verify-mpfb-linux:', 1)[0]
        consumer = text.split('  verify-mpfb-linux:', 1)[1]
        self.assertIn('if: ${{ !inputs.checksum_receipt_only }}', producer)
        self.assertIn('timeout-minutes: 15', producer)
        self.assertIn("if: steps.archive.outputs.cache-hit != 'true'", producer)
        self.assertLess(producer.index('Rehash exact archive'), producer.index('Publish only'))
        self.assertIn('lookup-only: true', producer)
        self.assertIn('fail-on-cache-miss: true', producer)
        self.assertIn('Require the exact published key', producer)
        self.assertIn('needs: prepare-blender-linux', consumer)
        self.assertIn('fail-on-cache-miss: true', consumer)
        self.assertIn('blender_archive_cache.py check-restore', consumer)
        self.assertLess(consumer.index('blender_archive_cache.py verify'), consumer.index('tar -xf'))
        self.assertNotIn('curl ', consumer)
        self.assertNotIn('fetch_blender_archive.sh', consumer)
        self.assertNotIn('restore-keys:', text)
        self.assertNotIn('path: |', producer)
        self.assertIn('path: ${{ runner.temp }}/ucc-blender-archive', producer)
        self.assertIn('sha256sum --check --strict', consumer)
        self.assertIn('fail-fast: false', consumer)
        self.assertIn('cancel-in-progress: false', text)

    def test_cache_only_dispatch_keeps_domains_off_and_receipt_has_precedence(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf8')
        inputs = text.split('    inputs:', 1)[1].split('  pull_request:', 1)[0]
        self.assertIn('archive_cache_only:', inputs)
        self.assertEqual(inputs.count('type: boolean\n        default: false'), 2)
        receipt = text.split('  record-blender-checksum:', 1)[1].split('  prepare-blender-linux:', 1)[0]
        producer = text.split('  prepare-blender-linux:', 1)[1].split('  verify-mpfb-linux:', 1)[0]
        domain = text.split('  verify-mpfb-linux:', 1)[1]
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.checksum_receipt_only", receipt)
        self.assertIn('if: ${{ !inputs.checksum_receipt_only }}', producer)
        self.assertNotIn('tar -xf', producer)
        self.assertNotIn('--background', producer)
        self.assertIn('if: ${{ !inputs.checksum_receipt_only && !inputs.archive_cache_only }}', domain)
        title = next(line for line in text.splitlines() if line.startswith('run-name:'))
        self.assertLess(title.index('inputs.checksum_receipt_only'), title.index('inputs.archive_cache_only'))
        self.assertIn('PUBLIC ARCHIVE CACHE ONLY - no Blender/domain execution', title)

    def test_only_reviewed_primary_and_fallback_routes_have_bounded_fetches(self):
        text = (ROOT/'ci/fetch_blender_archive.sh').read_text(encoding='utf8')
        for origin in ('https://download.blender.org/release/Blender5.3',
                       'https://mirror.clarkson.edu/blender/release/Blender5.3'):
            self.assertIn(origin, text)
        self.assertIn('--max-redirs 0', text)
        self.assertIn('--retry 0', text)
        self.assertIn('--max-filesize 65536', text)
        self.assertIn('--max-filesize 1073741824', text)
        self.assertIn('return 20', text)
        self.assertIn('if [[ "$failure" != 10 ]]', text)
        self.assertIn('checksum --input', text)
        self.assertIn('verify --directory', text)
        for forbidden in ('--insecure', 'extension install', 'tar -xf', 'restore-keys', 'rm -rf'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
