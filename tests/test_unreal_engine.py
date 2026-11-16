"""Portable project and owned worker guards; no engine/import is simulated as accepted."""
from pathlib import Path
from threading import Event
import ast
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs.unreal_engine import (project_files, DELIVERY_FILES, _run, prepare_unreal_engine,
    check_selected_compiler, CAPTURE_FIELDS, _private_cache, _verification_project)
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

    def test_private_ddc_uses_owned_short_root_without_changing_portable_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); portable = root/'portable'; portable.mkdir()
            for name in DELIVERY_FILES:
                path = portable/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{}' if name.endswith('.uproject') else 'HOST_METADATA_FIXTURE')
            scripts = root/'engine/scripts'; scripts.mkdir(parents=True)
            before = project_files(portable)
            clone = root/'fresh'
            _verification_project(clone, before, {'portable_root': portable}, {}, None, scripts)
            cache = scripts.parent/'d'
            self.assertTrue(cache.is_dir())
            self.assertLess(len(cache.as_posix().encode('utf-16-le'))//2, 119)
            self.assertIn('Path="'+cache.as_posix()+'"', (clone/'Config/DefaultEngine.ini').read_text())
            self.assertNotIn('%GAMEDIR%DerivedDataCache', (clone/'Config/DefaultEngine.ini').read_text())
            self.assertEqual(before, project_files(portable))

    def test_private_ddc_bound_counts_encoded_windows_characters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            padding = 120 - len(root.as_posix().encode('utf-16-le'))//2 - 11
            self.assertGreater(padding, 0)
            work = root/('x'*padding+'\U00010400'*4)
            scripts = work/'scripts'; scripts.mkdir(parents=True)
            self.assertLess(len((work/'d').as_posix()), 119)
            self.assertGreaterEqual(len((work/'d').as_posix().encode('utf-16-le'))//2, 119)
            with self.assertRaisesRegex(ProjectStorageError, '119-character'):
                _private_cache(scripts)
            self.assertFalse((work/'d').exists())

    def test_capture_rejects_other_clone_path_even_when_fbx_bytes_match(self):
        from fixtures.unreal_contract_logic import request
        from ucc.core.skin_material import SkinMaterialSpec
        from ucc.jobs.unreal_engine import _capture, _write, CAPTURE_POLICY
        from ucc.jobs.master_preview import _digest
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve(); project = root/'project'; (project/'Content').mkdir(parents=True)
            fbx = project/'DerivedSources/character.fbx'; fbx.parent.mkdir()
            fbx.write_bytes(b'HOST_ONLY_METADATA_FIXTURE_NOT_FBX')
            other = root/'other-clone/DerivedSources/character.fbx'; other.parent.mkdir(parents=True)
            other.write_bytes(fbx.read_bytes())
            descriptor = root/'descriptor.json'; descriptor.write_text('{}')
            profile = root/'profile.json'; profile.write_text('{}')
            stage = root/'stage-receipt.json'; stage.write_text('{}')
            req = request(); output = root/'reopened'
            toolchain = SimpleNamespace(identity_sha256=req.toolchain_sha256, editor_exe=root/'UNIT_NO_EXECUTABLE.exe')
            def rejected_worker_fixture(*_):
                (output/'UnrealEditor.log').write_text("UNIT_TEST_ONLY_NOT_REAL_ENGINE\nInternalLoadLibrary: 'NullDrv'\n")
                native = output/'native-observation.json'; native.write_text('{"UNIT_NOT_NATIVE_DATA":true}')
                record = {name: None for name in CAPTURE_FIELDS}
                record.update(schema_version=1, policy=CAPTURE_POLICY, state='CAPTURED_UNVERIFIED', mode='FRESH',
                    job_id=req.job_id, native_observation_captured=True, request_sha256=req.sha256,
                    toolchain_identity_sha256=req.toolchain_sha256, engine_profile_sha256=_digest(profile, None),
                    source_descriptor_path=str(descriptor), source_descriptor_sha256=_digest(descriptor, None),
                    source_fbx_path=str(other), source_fbx_sha256=_digest(other, None),
                    native_observation_path=str(native), native_observation_sha256=_digest(native, None),
                    engine_exe_sha256=req.unreal_executable_sha256, engine_build_sha256=req.unreal_build_version_sha256)
                record.update({name: False for name in READINESS_FLAGS})
                _write(output/'capture-receipt.json', record)
            self.assertEqual(_digest(fbx, None), _digest(other, None))
            with patch('ucc.jobs.unreal_engine._run', side_effect=rejected_worker_fixture) as run:
                with self.assertRaisesRegex(ProjectStorageError, 'capture receipt differs'):
                    _capture(project, output, 'FRESH', request=req, toolchain=toolchain,
                        profile_path=profile, descriptor=descriptor, material_spec=SkinMaterialSpec((.4,.3,.2),.6),
                        stage_receipt=stage, scripts=root, budget=None, deadline=time.monotonic()+10)
                run.assert_called_once()
