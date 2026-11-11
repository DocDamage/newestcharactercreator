import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_gate
import check_asset_policy
import collect_p0

GATES = json.loads((ROOT / 'config' / 'gates.json').read_text(encoding='utf-8'))


class P0GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = {
            'audit': 'preflight.json',
            'summary': 'mpfb_smoke/summary.json',
            'created': 'mpfb_smoke/mpfb_create_result.json',
            'reopen': 'mpfb_smoke/reopen_result.json',
            'blend': 'mpfb_smoke/mpfb_created.blend',
        }

    def file(self, name, data):
        path = self.root / self.paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            path.write_text(json.dumps(data), encoding='utf-8')
        else:
            path.write_bytes(data)
        return path

    def valid(self):
        self.file('audit', {'read_only': True, 'blender': {'found': True, 'version_probe': {'exit_code': 0}}})
        self.file('summary', {'passed': True, 'create': {'return_code': 0}, 'reopen': {'return_code': 0}})
        self.file('created', {'status': 'ok', 'new_mesh_vertices': [1001]})
        self.file('reopen', {'status': 'ok', 'vertex_count': 1001})
        self.file('blend', b'BLENDER' + b'\0' * 500)
        tests = []
        names = [('ENV-PROBE', ['audit']), ('MPFB-CREATE', ['summary', 'created', 'blend']),
                 ('MPFB-REOPEN', ['summary', 'reopen', 'blend'])]
        for name, sources in names:
            tests.append({'id': name, 'status': 'pass', 'observed_at_utc': '2026-01-01T00:00:00Z',
                          'artifacts': [{'path': self.paths[source], 'sha256': verify_gate.sha256_file(self.root / self.paths[source])} for source in sources]})
        return {'schema_version': 1, 'gate': 'P0_SPIKE', 'tests': tests}

    def test_missing_evidence_rejected(self):
        e = {'schema_version': 1, 'gate': 'P0_SPIKE', 'tests': []}
        errors = verify_gate.validate_gate(GATES, e, self.root, 'P0_SPIKE')
        self.assertTrue(errors)

    def test_valid_structural_synthetic_fixture(self):
        # Tests the validator only. Fake signature bytes are NOT a real .blend and NEVER constitute user proof.
        e = self.valid()
        errors = verify_gate.validate_gate(GATES, e, self.root, 'P0_SPIKE')
        self.assertEqual(errors, [])

    def test_failed_mpfb_blocks_even_if_hashes_match(self):
        e = self.valid()
        self.file('summary', {'passed': False, 'create': {'return_code': 1}, 'reopen': {'return_code': 0}})
        for item in e['tests']:
            for a in item['artifacts']:
                a['sha256'] = verify_gate.sha256_file(self.root / a['path'])
        self.assertIn('P0 Blender creation/reopen subprocess did not succeed', verify_gate.validate_gate(GATES, e, self.root, 'P0_SPIKE'))

    def test_tampered_file_rejected(self):
        e = self.valid()
        self.file('reopen', {'status': 'fail', 'vertex_count': 0})
        errors = verify_gate.validate_gate(GATES, e, self.root, 'P0_SPIKE')
        self.assertTrue(any('checksum mismatch' in x for x in errors))

    def test_traversal_rejected(self):
        self.valid()
        with self.assertRaises(ValueError):
            verify_gate.safe_evidence_path(self.root, '../outside.txt')
        with self.assertRaises(ValueError):
            verify_gate.safe_evidence_path(self.root, str(self.root / 'preflight.json'))

    def test_manual_review_required(self):
        e = {'schema_version': 1, 'gate': 'M1_EXPORTS', 'tests': []}
        for x in GATES['gates']['M1_EXPORTS']['required']:
            e['tests'].append({'id': x['id'], 'status': 'pass', 'observed_at_utc': '2026-01-01T00:00:00Z',
                               'artifacts': [{'path': 'preflight.json', 'sha256': '0'*64}]})
        self.file('audit', {'sample': True})
        errors = verify_gate.validate_gate(GATES, e, self.root, 'M1_EXPORTS')
        self.assertTrue(any('missing human reviewer' in x for x in errors))

    def test_collector_marks_failures_blocked(self):
        self.valid()
        result = collect_p0.gather(self.root, self.root / self.paths['audit'], self.root / 'mpfb_smoke')
        self.assertTrue(all(t['status'] == 'pass' for t in result['tests']))
        self.file('summary', {'passed': False, 'create': {'return_code': 2}, 'reopen': {'return_code': 0}})
        result = collect_p0.gather(self.root, self.root / self.paths['audit'], self.root / 'mpfb_smoke')
        self.assertEqual(result['tests'][0]['status'], 'pass')
        self.assertEqual(result['tests'][1]['status'], 'blocked')
        self.assertEqual(result['tests'][2]['status'], 'blocked')


class AssetPolicyTests(unittest.TestCase):
    def record(self):
        return dict(asset_id='real-01', provider='owned', source_uri='https://example.com',
                    license_name='Custom', license_reviewed=True,
                    no_ai_training=False, ue_only=False, can_redistribute_source=False,
                    can_use_in_non_unreal=True, ai_training_permission=False)

    def test_private_inventory_accepts_known_fields(self):
        self.assertEqual(check_asset_policy.validate_record(self.record(), 'private_inventory', None), [])

    def test_cross_engine_ue_only_blocks(self):
        r = self.record()
        r['ue_only'] = True
        self.assertIn('cross-engine use not approved', check_asset_policy.validate_record(r, 'engine_export', 'godot'))

    def test_no_ai_blocks(self):
        r = self.record()
        r['no_ai_training'] = True
        self.assertIn('generative AI input use not approved', check_asset_policy.validate_record(r, 'ai_input', None))

    def test_shipping_source_blocked(self):
        self.assertIn('standalone source redistribution not approved', check_asset_policy.validate_record(self.record(), 'ship_creator', None))

    def test_empty_source_uri_blocks(self):
        r = self.record()
        r['source_uri'] = ''
        self.assertIn('source_uri must be a nonempty string', check_asset_policy.validate_record(r, 'private_inventory', None))


if __name__ == '__main__':
    unittest.main()
