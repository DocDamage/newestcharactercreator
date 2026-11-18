"""Source-checkout import regression; fake bpy/handlers, no Blender or assets."""
import json
from pathlib import Path
import subprocess
import sys
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[1]/'blender_bridge/entrypoint.py'


def entrypoint_source():
    return ENTRYPOINT.read_text(encoding='utf8')


PROBE = r'''
import ast, json, sys, types
data = json.load(sys.stdin)
tree = ast.parse(data['source'])
prefix = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        break
    prefix.append(node)
sys.modules['bpy'] = types.ModuleType('bpy')
# Isolate unrelated bridge integrations while retaining the real bootstrap,
# allowlist and ucc import behavior. The isolated interpreter has no site path.
for node in prefix:
    if isinstance(node, ast.ImportFrom) and node.module.startswith('blender_bridge.'):
        module = types.ModuleType(node.module)
        for item in node.names:
            setattr(module, item.name, set() if item.name == 'OPERATIONS' else object())
        sys.modules[node.module] = module
ns = {'__file__': data['entrypoint'], '__name__': 'isolated_entrypoint_probe'}
exec(compile(ast.Module(body=prefix, type_ignores=[]), '<isolated entrypoint prologue>', 'exec'), ns)
operations = {'inspect_authored_idle_target', 'author_original_idle_source', 'verify_authored_idle_source'}
assert operations <= ns['OPERATIONS']
assert 'ucc' not in sys.modules, 'Checkout bootstrap must not require ucc before activation'
assert str(ns['REPO_ROOT']/'src') not in sys.path
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {'activate_material_contract', 'authored_idle'}]
assert len(functions) == 2
exec(compile(ast.Module(body=functions, type_ignores=[]), '<isolated entrypoint handlers>', 'exec'), ns)
handler = types.ModuleType('blender_bridge.authored_idle')
calls = []
def called(bpy, root, job):
    assert bpy is sys.modules['bpy']
    calls.append(job['operation'])
    return {'operation': job['operation'], 'synthetic_handler_only': True}
for name in ('inspect_target', 'author_source', 'verify_source'):
    setattr(handler, name, called)
sys.modules[handler.__name__] = handler
for operation in sorted(operations):
    options = {'request_sha256': 'a'*64}
    if operation == 'verify_authored_idle_source':
        options.update({key: 'b'*64 for key in ('review_sha256','source_sha256','recipe_sha256')})
    job = {'operation': operation, 'input_project': 'candidate.blend', 'options': options}
    assert ns['authored_idle'](job, ns['REPO_ROOT'],) == {
        'operation': operation, 'synthetic_handler_only': True}
assert len(calls) == 3
assert str(ns['REPO_ROOT']/'src') in sys.path
assert str(sys.modules['ucc.core.authored_idle_job'].__file__).startswith(str(ns['REPO_ROOT']/'src'))
# The actual pure validator must reject before any fake native handler runs.
from ucc.core.errors import ValidationError
try:
    ns['authored_idle']({'operation': 'author_original_idle_source',
        'input_project': '../master.blend', 'options': {'request_sha256': 'a'*64}}, ns['REPO_ROOT'])
except ValidationError:
    pass
else:
    raise AssertionError('Actual phase validator was bypassed')
assert len(calls) == 3
print('CHECKOUT_BOOTSTRAP_AND_THREE_DEFERRED_DISPATCHES_PASS_NO_NATIVE')
'''


class AuthoredIdleBootstrapTests(unittest.TestCase):
    def test_checkout_bootstraps_without_installed_core_then_activates_before_idle_dispatch(self):
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', PROBE],
            input=json.dumps({'source': entrypoint_source(), 'entrypoint': str(ENTRYPOINT)}),
            capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(),
            'CHECKOUT_BOOTSTRAP_AND_THREE_DEFERRED_DISPATCHES_PASS_NO_NATIVE')


if __name__ == '__main__':
    unittest.main()
