"""Nonshipping worker-boundary doubles; never Blender or engine evidence."""
import ast
from pathlib import Path
from types import SimpleNamespace


def source_functions(**dependencies):
    """Load the actual boundary functions without importing Blender/NumPy."""
    root = Path(__file__).resolve().parents[2]
    source = root / "blender_bridge/godot_runtime_source.py"
    names = {"checked_recipe", "require_registered_material_state", "admitted_source"}
    tree = ast.parse(source.read_text(encoding="utf-8"))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in body} == names
    namespace = {"Path": Path, "Any": object, **dependencies}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


def material_scene(*, slots=(), images=(), libraries=()):
    human = SimpleNamespace(data=SimpleNamespace(materials=list(slots)))
    bpy = SimpleNamespace(data=SimpleNamespace(images=list(images), libraries=list(libraries)))
    return bpy, human


def image(*, source="VIEWER", filepath="", packed_file=None):
    return SimpleNamespace(source=source, filepath=filepath, packed_file=packed_file)
