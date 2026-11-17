"""Cold bootstrap logic only; fake bpy never executes Blender or native code."""
import ast
import builtins
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


class _FirstServiceImport(Exception):
    pass


class ColdWorkerBootstrapTests(unittest.TestCase):
    def bootstrap(self, packaged):
        tree = ast.parse((ROOT / "blender_bridge/entrypoint.py").read_text(encoding="utf-8"))
        prefix = []
        for node in tree.body:
            prefix.append(node)
            if isinstance(node, ast.ImportFrom) and node.module == "blender_bridge.mpfb_service":
                break
        else:
            self.fail("Worker bootstrap service boundary not found")
        observations = []
        fake_sys = SimpleNamespace(dont_write_bytecode=False, path=[], modules={})
        def import_module(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "sys":
                return fake_sys
            if name == "bpy":
                observations.append((name, fake_sys.dont_write_bytecode))
                return SimpleNamespace()
            if name.startswith("blender_bridge"):
                observations.append((name, fake_sys.dont_write_bytecode))
                if name == "blender_bridge.payload_contract":
                    def activate(root):
                        observations.append(("activate_worker_payload", fake_sys.dont_write_bytecode))
                    return SimpleNamespace(activate_worker_payload=activate)
                raise _FirstServiceImport()
            return builtins.__import__(name, globals, locals, fromlist, level)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "blender_bridge").mkdir()
            if packaged:
                (root / "worker_support").mkdir()
            namespace = {"__file__": str(root / "blender_bridge/entrypoint.py"),
                         "__builtins__": {**vars(builtins), "__import__": import_module}}
            with self.assertRaises(_FirstServiceImport):
                exec(compile(ast.Module(body=prefix, type_ignores=[]), "actual-worker-bootstrap", "exec"), namespace)
            self.assertIn("blender_bridge.mpfb_service", [name for name, _ in observations])
            self.assertTrue(all(flag is True for _, flag in observations), observations)
            if packaged:
                self.assertIn("activate_worker_payload", [name for name, _ in observations])
                self.assertEqual(fake_sys.modules["blender_bridge"].__path__, [str(root / "blender_bridge")])
            else:
                self.assertEqual(fake_sys.path[0], str(root))
                self.assertNotIn("activate_worker_payload", [name for name, _ in observations])

    def test_cold_source_disables_bytecode_before_bpy_and_local_package_imports(self):
        self.bootstrap(packaged=False)

    def test_cold_packaged_worker_disables_bytecode_before_payload_activation(self):
        self.bootstrap(packaged=True)
