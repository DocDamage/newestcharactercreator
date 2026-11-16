"""CI integration wiring and explicit data-minimization contracts, not deformation proof."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExpressionCIContracts(unittest.TestCase):
    def test_source_gate_covers_preparation_composition_and_complete_private_cache(self):
        from ci.verify_expressions import NAMES, STATUS
        self.assertEqual(NAMES, ('short-light-narrow', 'middle-neutral', 'tall-muscular-wide'))
        self.assertIn('THIRTEEN_FAULTS', STATUS)
        source = (ROOT/'ci/verify_expressions.py').read_text()
        calls = {node.func.id for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertTrue({'prepare_saved_expressions', 'preview_saved_expressions', 'apply_hand_revision',
            'apply_saved_customized_body_revision', 'generate_customized_humanoid', 'apply_saved_face_revision',
            'verify_faults', 'verify_guards'} <= calls)
        self.assertNotIn('owner-hand', source)
        self.assertNotIn('D:/', source)

    def test_summary_does_not_include_raw_worker_proofs_meshes_or_buffers(self):
        source = ast.parse((ROOT/'ci/verify_expressions.py').read_text())
        returns = [n for n in ast.walk(source) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]
        summary = next(n.value for n in returns if any(isinstance(k, ast.Constant) and k.value == 'original_source_only'
                                                      for k in n.value.keys))
        keys = {k.value for k in summary.keys if isinstance(k, ast.Constant)}
        self.assertEqual(keys, {'status', 'cases', 'mutations', 'faults', 'guards', 'original_source_only',
            'original_inputs_unchanged', 'installed_assets_unchanged', 'visual_quality_approved',
            'engine_import_verified', 'elapsed_seconds'})
        names = {n.id for n in ast.walk(summary) if isinstance(n, ast.Name)}
        self.assertFalse(names & {'preview', 'buffers', 'cache', 'report', 'protected'})

    def test_both_workflow_triggers_include_expression_boundaries(self):
        text = (ROOT/'.github/workflows/mpfb-cloud-smoke.yml').read_text()
        for path in ('ci/verify_expressions.py', 'ci/expression_*_checks.py', 'tests/fixtures/blender_expression*.py',
                     'src/ucc/core/expression*.py', 'src/ucc/jobs/expression_*.py', 'src/ucc/preview/expression_cache.py'):
            self.assertEqual(text.count("- '"+path+"'"), 2)
