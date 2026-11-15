"""Original-only CI wiring and artifact minimization, not real deformation proof."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RegionalCIContracts(unittest.TestCase):
    def test_original_gate_requires_three_bodies_all900frames_and_real_faults(self):
        from ci.verify_regional_skin import STATUS
        from ci.regional_sources import NAMES
        from ci.regional_fault_checks import EXPECTED
        self.assertEqual(len(NAMES), 3)
        self.assertIn('900_FRAMES_TEN_FAULTS', STATUS)
        self.assertEqual(len(EXPECTED), 8)
        source = (ROOT/'ci/verify_regional_skin.py').read_text(encoding='utf-8')
        calls = {n.func.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertTrue({'build_targets', 'preview_native_body', 'prepare_native_playback', 'verify_faults', 'hand_local_motion'} <= calls)
        for path in ('ci/verify_regional_skin.py', 'ci/regional_sources.py',
                     'tests/fixtures/blender_regional_checks.py', 'tests/fixtures/blender_regional_faults.py'):
            text = (ROOT/path).read_text(encoding='utf-8')
            self.assertNotIn('D:/', text)
            self.assertNotIn('Motifect', text)
            self.assertNotIn('pasted-text', text)

    def test_independent_reader_does_not_call_production_reopen_or_mask_solver(self):
        source = (ROOT/'tests/fixtures/blender_regional_checks.py').read_text(encoding='utf-8')
        self.assertNotIn('reopen_native', source)
        self.assertNotIn('native_region_mask', source)
        calls = {n.func.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertTrue({'strain', 'group_digest', 'groups', 'mesh_data', 'geometry'} <= calls)

    def test_only_aggregate_summary_is_retained_by_both_workflow_triggers(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text(encoding='utf-8')
        for path in ('ci/verify_regional_skin.py', 'ci/regional_*.py', 'tests/fixtures/blender_regional*.py'):
            self.assertEqual(text.count("- '"+path+"'"), 2)
        self.assertIn('symmetric-fit, regional-skin, source-references]', text)
        artifact = text.split('path: |', 1)[1].split('if-no-files-found:', 1)[0]
        self.assertEqual([p.strip() for p in artifact.splitlines() if 'ucc-regional-skin' in p],
                         ['${{ runner.temp }}/ucc-regional-skin/regional_skin_summary.json'])
        self.assertNotIn('*', artifact)
        source = ast.parse((ROOT/'ci/verify_regional_skin.py').read_text(encoding='utf-8'))
        summary = next(n.value for n in ast.walk(source) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)
                       and any(isinstance(k, ast.Constant) and k.value == 'original_source_only' for k in n.value.keys))
        refs = {n.id for n in ast.walk(summary) if isinstance(n, ast.Name)}
        self.assertFalse(refs & {'data', 'preview', 'cache', 'protected', 'installed', 'source'})
