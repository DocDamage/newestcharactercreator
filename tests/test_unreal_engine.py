"""Portable project and owned worker guards; no engine/import is simulated as accepted."""
from pathlib import Path
from threading import Event
import ast
import json
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs.unreal_engine import project_files, DELIVERY_FILES, _run, prepare_unreal_engine, check_selected_compiler, CAPTURE_FIELDS
from ucc.export.unreal_contract import READINESS_FLAGS


class UnrealEngineTests(unittest.TestCase):
    def test_delivery_inventory_excludes_private_inputs_and_caches(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in DELIVERY_FILES:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'FILE_INVENTORY_FIXTURE')
            before = project_files(root)
            self.assertEqual(set(before), DELIVERY_FILES)
            for name in ('source_reference.json', 'Plugins/Observer.uplugin', 'Saved/cache.dat'):
                extra = root/name; extra.parent.mkdir(parents=True, exist_ok=True); extra.write_bytes(b'PRIVATE')
                with self.assertRaises(ProjectStorageError): project_files(root)
                extra.unlink()
                if extra.parent != root: extra.parent.rmdir()
            (root/'Content/UCC/Character.uasset').write_bytes(b'CHANGED')
            self.assertNotEqual(before, project_files(root))

    def test_cancelled_job_never_launches_or_replaces_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); cancel = Event(); cancel.set()
            with self.assertRaises(ProjectStorageError):
                _run([sys.executable, '-c', 'raise Exception()'], root, cancel, time.monotonic()+2)
            self.assertFalse((root/'owned-process.json').exists())

    def test_owned_python_deadline_is_retained_as_deadline_not_user_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with self.assertRaises(ProjectStorageError):
                _run([sys.executable, '-c', 'import time;time.sleep(5)'], root, None, time.monotonic()+.15)
            result = json.loads((root/'process-result.json').read_text())
            self.assertEqual(result['failure_reason'], 'total_deadline')
            self.assertGreater(result['pid'], 0)
            self.assertLess(result['elapsed_seconds'], 4)

    def test_missing_reviewed_source_never_starts_engine(self):
        with self.assertRaises(ValidationError): prepare_unreal_engine(None, request=None, toolchain=None)

    def test_adapter_remains_scalar_free_and_reopen_has_no_mutators(self):
        root = Path(__file__).resolve().parents[1]/'engine_adapters/unreal'
        source = (root/'Source/UccNativeObservation/Private/UccNativeObservationLibrary.cpp').read_text()
        self.assertNotIn('ProbeScalarFbxUnits', source)
        self.assertNotIn('FbxImporter.h', source)
        self.assertNotIn('SavePackage', source)
        tree = ast.parse((root/'reopen.py').read_text())
        calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        self.assertFalse(any(name.startswith(('set_', 'save_', 'import_', 'build_')) for name in calls))
        common = ast.parse((root/'capture_common.py').read_text())
        control_keys = {node.slice.value for node in ast.walk(common) if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name) and node.value.id == 'control' and isinstance(node.slice, ast.Constant)}
        self.assertNotIn('job_id', control_keys)  # job identity comes from the hash-bound export request.
        envelope = next(node.value for node in ast.walk(common) if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == 'envelope' for target in node.targets))
        keys = {key.value for key in envelope.keys if isinstance(key, ast.Constant)}
        self.assertEqual(keys | READINESS_FLAGS, CAPTURE_FIELDS)

    def test_compiler_selection_checks_actual_using_line_not_available_tool_list(self):
        toolchain = SimpleNamespace(compiler_version='14.44.35227', sdk_version='10.0.26100.0')
        check_selected_compiler('Available compiler: 14.51.36231\nUsing Visual Studio 2022 14.44.35227 toolchain and Windows 10.0.26100.0 SDK', toolchain)
        for log in ('Available 14.44.35227 SDK10.0.26100.0',
            'Using Visual Studio 2022 14.51.36231 toolchain and Windows 10.0.26100.0 SDK'):
            with self.assertRaises(ProjectStorageError): check_selected_compiler(log, toolchain)
