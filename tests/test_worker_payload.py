"""Real first-party source packaging tests; no model or engine success fixtures."""
from importlib.util import module_from_spec, spec_from_file_location
import ast
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ValidationError
from ucc.core.worker_payload import validate_worker_payload, WorkerPayloadError, ADAPTER
from ucc.core.worker_payload import STATIC_ADAPTER, STATIC_ADAPTER_FILES
from ucc.jobs.worker_resources import worker_dependency_files, bundled_native_adapter_path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('ucc_payload_builder_for_tests', ROOT/'ci/build_worker_payload.py')
builder = module_from_spec(spec); spec.loader.exec_module(builder)


class WorkerPayloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.payload = self.root/'payload'
        self.manifest = builder.build_payload(ROOT, self.payload)

    def write_manifest(self, value):
        (self.payload/'worker_support/payload.v1.json').write_text(json.dumps(value))

    def test_complete_first_party_sources_and_checked_adapter_resolution(self):
        paths = validate_worker_payload(self.payload)
        self.assertGreaterEqual(len(self.manifest['modules']), 50)
        self.assertEqual(set(paths), worker_dependency_files(self.payload/'blender_bridge/entrypoint.py'))
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(self.payload), create=True):
            self.assertEqual(bundled_native_adapter_path(), self.payload/ADAPTER)
            from ucc.desktop.generation import bundled_worker_path
            self.assertEqual(bundled_worker_path(), self.payload/'blender_bridge/entrypoint.py')

    def test_isolated_python_imports_every_contract_without_source_path_or_optional_runtime(self):
        code = '''import sys,importlib,json
from pathlib import Path
base=Path(sys.argv[1]);sys.path.insert(0,str(base))
from blender_bridge.payload_contract import activate_worker_payload
activate_worker_payload(base)
manifest=json.loads((base/'worker_support/payload.v1.json').read_text())
for name in manifest['modules']:importlib.import_module(name)
assert all(Path(module.__file__).resolve().is_relative_to(base/'worker_support') for name,module in sys.modules.items() if name=='ucc' or name.startswith('ucc.'))
assert not any(name.split('.')[0] in {'bpy','PySide6','numpy','torch','tensorflow'} for name in sys.modules)
print('ISOLATED_PURE_CONTRACT_IMPORTS_OK')
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(self.payload)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ISOLATED_PURE_CONTRACT_IMPORTS_OK', result.stdout)
        validate_worker_payload(self.payload)

    def test_static_adapter_matches_checkout_and_frozen_resolution_requires_manifest(self):
        from ucc.jobs.static_godot_engine import scripts
        source = scripts()
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(self.payload), create=True):
            frozen = scripts()
            self.assertEqual(set(frozen), set(source))
            for name in source:
                self.assertEqual(frozen[name].read_bytes(), source[name].read_bytes())
                self.assertEqual(frozen[name].parent, self.payload/STATIC_ADAPTER)
            (self.payload/STATIC_ADAPTER/'inspect.gd').write_text('# UNIT_CORRUPTION_NOT_ENGINE_PROOF\n')
            with self.assertRaisesRegex(Exception, 'incomplete or changed'): scripts()

    def test_missing_static_resource_is_rejected_even_with_rehashed_manifest(self):
        value = json.loads(json.dumps(self.manifest))
        name = STATIC_ADAPTER + '/' + sorted(STATIC_ADAPTER_FILES)[0]
        (self.payload/name).unlink();value['files'].pop(name);self.write_manifest(value)
        with self.assertRaisesRegex(WorkerPayloadError, 'incomplete'):validate_worker_payload(self.payload)

    def test_registered_godot_adapters_resolve_exact_first_party_source_bytes(self):
        from ucc.core.worker_payload import REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES
        from ucc.core.worker_payload import REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES
        from ucc.core.worker_payload import REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES
        from ucc.jobs.godot_registered_body_inputs import body_adapter_paths
        from ucc.jobs.worker_resources import bundled_registered_body_paths, bundled_registered_correction_paths
        from ucc.jobs.worker_resources import bundled_registered_playback_paths

        correction_names = {
            'runtime_kernel.gd', 'ucc_skin_adapter.gd', 'smooth.glsl', 'corners.glsl',
            'normal_faces.glsl', 'normal_vertices.glsl', 'combine.glsl',
        }
        body_names = {'project.godot', 'configure.gd', 'validate.gd'}
        playback_names = {'project.godot', 'pack.gd', 'playback.gd', 'verify.gd'}
        self.assertEqual(REGISTERED_CORRECTION_FILES, correction_names)
        self.assertEqual(REGISTERED_BODY_FILES, body_names)
        self.assertEqual(REGISTERED_PLAYBACK_FILES, playback_names)
        self.assertEqual(self.manifest['schema_version'], 4)
        source_root = ROOT/'engine_adapters/godot'
        cases = (
            ('registered_correction', REGISTERED_CORRECTION_ADAPTER, correction_names,
             bundled_registered_correction_paths),
            ('registered_body300', REGISTERED_BODY_ADAPTER, body_names, bundled_registered_body_paths),
            ('registered_playback', REGISTERED_PLAYBACK_ADAPTER, playback_names, bundled_registered_playback_paths),
        )
        for source_name, payload_relative, names, locator in cases:
            with self.subTest(adapter=source_name):
                source = locator()
                with patch.object(sys, 'frozen', True, create=True), patch.object(
                    sys, '_MEIPASS', str(self.payload), create=True,
                ):
                    frozen = locator()
                    if source_name == 'registered_body300':
                        self.assertEqual(body_adapter_paths(), frozen)
                self.assertEqual(set(frozen), names)
                self.assertEqual(set(source), names)
                for name in sorted(names):
                    original = (source_root/name if name == 'ucc_skin_adapter.gd'
                                else source_root/source_name/name)
                    self.assertEqual(source[name], original)
                    self.assertEqual(frozen[name], self.payload/payload_relative/name)
                    data = original.read_bytes()
                    self.assertTrue(data)
                    self.assertEqual(frozen[name].read_bytes(), data)
                    self.assertEqual(self.manifest['files'][f'{payload_relative}/{name}'],
                                     {'bytes': len(data), 'sha256': sha256(data).hexdigest()})

    def test_every_new_godot_resource_is_required_even_if_removed_from_manifest(self):
        from ucc.core.worker_payload import REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES
        from ucc.core.worker_payload import REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES
        from ucc.core.worker_payload import REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES

        groups = ((REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES),
                  (REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES),
                  (REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES))
        for directory, names in groups:
            for name in sorted(names):
                relative = f'{directory}/{name}'
                path = self.payload/relative
                original = path.read_bytes()
                with self.subTest(resource=relative):
                    altered = json.loads(json.dumps(self.manifest))
                    del altered['files'][relative]
                    path.unlink()
                    self.write_manifest(altered)
                    try:
                        with self.assertRaisesRegex(WorkerPayloadError, 'incomplete'):
                            validate_worker_payload(self.payload)
                    finally:
                        path.write_bytes(original)
                        self.write_manifest(self.manifest)

    def test_frozen_registered_locators_reject_changed_bytes_and_legacy_payload(self):
        from ucc.core.worker_payload import REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES
        from ucc.core.worker_payload import REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES
        from ucc.core.worker_payload import REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES
        from ucc.core.worker_payload import UNITY_REGISTERED_ANIMATION_ADAPTER, UNITY_REGISTERED_ANIMATION_FILES
        from ucc.core.worker_payload import (UNITY_REGISTERED_CORRECTION_ADAPTER, UNITY_REGISTERED_CORRECTION_FILES,
            UNITY_REGISTERED_CORRECTION_BINDING)
        from ucc.jobs.worker_resources import bundled_registered_body_paths, bundled_registered_correction_paths
        from ucc.jobs.worker_resources import bundled_registered_playback_paths
        from ucc.jobs.worker_resources import bundled_unity_registered_animation_paths
        from ucc.jobs.worker_resources import bundled_unity_registered_correction_paths
        from ucc.core.worker_payload import (UNREAL_REGISTERED_ANIMATION, UNREAL_REGISTERED_ANIMATION_FILES,
            UNREAL_REGISTERED_PREVIEW, UNREAL_REGISTERED_PREVIEW_FILES)
        from ucc.jobs.worker_resources import bundled_unreal_registered_paths

        groups = (
            (REGISTERED_BODY_ADAPTER, REGISTERED_BODY_FILES, bundled_registered_body_paths),
            (REGISTERED_CORRECTION_ADAPTER, REGISTERED_CORRECTION_FILES, bundled_registered_correction_paths),
            (REGISTERED_PLAYBACK_ADAPTER, REGISTERED_PLAYBACK_FILES, bundled_registered_playback_paths),
            (UNITY_REGISTERED_ANIMATION_ADAPTER, UNITY_REGISTERED_ANIMATION_FILES, bundled_unity_registered_animation_paths),
            (UNITY_REGISTERED_ANIMATION_ADAPTER, {UNITY_REGISTERED_CORRECTION_BINDING}, bundled_unity_registered_correction_paths),
            (UNITY_REGISTERED_CORRECTION_ADAPTER, UNITY_REGISTERED_CORRECTION_FILES, bundled_unity_registered_correction_paths),
            (UNREAL_REGISTERED_ANIMATION, UNREAL_REGISTERED_ANIMATION_FILES, bundled_unreal_registered_paths),
            (UNREAL_REGISTERED_PREVIEW, UNREAL_REGISTERED_PREVIEW_FILES, bundled_unreal_registered_paths),
        )
        with patch.object(sys, 'frozen', True, create=True), patch.object(
            sys, '_MEIPASS', str(self.payload), create=True,
        ):
            for root, names, locator in groups:
                target = self.payload/root/sorted(names)[0]
                original = target.read_bytes()
                with self.subTest(resource=target.name):
                    target.write_bytes(b'UNIT_DAMAGED_NOT_ENGINE_PROOF')
                    try:
                        with self.assertRaises(ValidationError):
                            locator()
                    finally:
                        target.write_bytes(original)

            unity = bundled_unity_registered_animation_paths()
            for name in UNITY_REGISTERED_ANIMATION_FILES:
                self.assertEqual(unity[name], self.payload/UNITY_REGISTERED_ANIMATION_ADAPTER/name)
                self.assertEqual(unity[name].read_bytes(), (ROOT/'engine_adapters/unity/registered_animation'/name).read_bytes())
            unreal = bundled_unreal_registered_paths()
            for name in UNREAL_REGISTERED_PREVIEW_FILES:
                self.assertEqual(unreal['UccRegisteredPreview/'+name], self.payload/UNREAL_REGISTERED_PREVIEW/name)

            legacy = json.loads(json.dumps(self.manifest))
            legacy.update(schema_version=1, policy='UCC_WORKER_PAYLOAD_V1')
            for root, names, _ in groups:
                for name in names:
                    relative = f'{root}/{name}'
                    del legacy['files'][relative]
                    (self.payload/relative).unlink()
            self.write_manifest(legacy)
            validate_worker_payload(self.payload)
            self.assertEqual(bundled_native_adapter_path(), self.payload/ADAPTER)
            for _, _, locator in groups:
                with self.subTest(locator=locator.__name__), self.assertRaises(ValidationError):
                    locator()

    def test_unity_editor_and_shader_resources_resolve_and_tampering_rejects(self):
        from ucc.jobs.worker_resources import bundled_unity_adapter_paths
        source=bundled_unity_adapter_paths()
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(self.payload),create=True):
            frozen=bundled_unity_adapter_paths()
            self.assertEqual(set(source),set(frozen));self.assertIn('Editor/UccUnityExportJobs.cs',frozen)
            for name in source:self.assertEqual(source[name].read_bytes(),frozen[name].read_bytes())
            frozen['UccQuadNormals.compute'].write_text('// UNIT_DAMAGE_NOT_ENGINE_PROOF\n')
            with self.assertRaisesRegex(Exception,'incomplete or changed'):bundled_unity_adapter_paths()

    def test_missing_unity_resource_rejects_even_if_removed_from_manifest(self):
        from ucc.core.worker_payload import UNITY_ADAPTER
        value=json.loads(json.dumps(self.manifest));name=UNITY_ADAPTER+'/Editor/UccUnityObservation.cs'
        (self.payload/name).unlink();value['files'].pop(name);self.write_manifest(value)
        with self.assertRaisesRegex(WorkerPayloadError,'incomplete'):validate_worker_payload(self.payload)

    def test_modified_missing_and_unlisted_import_data_reject(self):
        path = self.payload/'worker_support/ucc/core/errors.py'; original = path.read_bytes()
        path.write_bytes(original+b'\n# unit corruption\n')
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)
        path.write_bytes(original); path.unlink()
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)
        path.write_bytes(original)
        cache = self.payload/'worker_support/ucc/unchecked.pyc'; cache.write_bytes(b'UNIT_NOT_EXECUTABLE')
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)

    def test_activation_refuses_an_already_imported_foreign_package(self):
        code = '''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[2]);import ucc
base=Path(sys.argv[1]);sys.path.insert(0,str(base))
from blender_bridge.payload_contract import activate_worker_payload,WorkerPayloadError
try:activate_worker_payload(base)
except WorkerPayloadError:print('FOREIGN_UCC_REJECTED')
else:raise AssertionError('Foreign package accepted')
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(self.payload), str(ROOT/'src')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('FOREIGN_UCC_REJECTED', result.stdout)

    def test_native_source_fallback_requires_local_contract_files(self):
        tree=ast.parse((ROOT/'blender_bridge/entrypoint.py').read_text())
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='native_godot_runtime')
        namespace={'REPO_ROOT':self.root,'sys':sys,'Path':Path}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'native_worker_fallback','exec'),namespace)
        before=list(sys.path)
        with self.assertRaisesRegex(RuntimeError,'contract sources are missing'):
            namespace['native_godot_runtime']({},self.root)
        self.assertEqual(sys.path,before)

    def test_packaged_bootstrap_does_not_expose_host_root_to_blender_imports(self):
        (self.payload/'fractions.py').write_text('raise RuntimeError("HOST_ROOT_MODULE_MUST_NOT_LOAD")\n')
        code='''import ast,sys
from pathlib import Path
base=Path(sys.argv[1]);source=base/'blender_bridge/entrypoint.py'
tree=ast.parse(source.read_text());body=[]
for node in tree.body:
 if isinstance(node,ast.ImportFrom) and node.module=='blender_bridge.mpfb_service':break
 if isinstance(node,ast.Import) and any(alias.name=='bpy' for alias in node.names):continue
 body.append(node)
exec(compile(ast.Module(body=body,type_ignores=[]),str(source),'exec'),{'__file__':str(source)})
assert str(base) not in sys.path
import fractions
assert not Path(fractions.__file__).is_relative_to(base)
assert sys.modules['blender_bridge'].__path__==[str(base/'blender_bridge')]
print('HOST_ROOT_IMPORT_ISOLATION_OK')
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(self.payload)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('HOST_ROOT_IMPORT_ISOLATION_OK',result.stdout)

    def test_traversal_duplicate_fields_and_readiness_forgery_reject(self):
        value = json.loads(json.dumps(self.manifest)); record = value['files'].pop('blender_bridge/entrypoint.py')
        value['files']['../outside.py'] = record; self.write_manifest(value)
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)
        self.write_manifest(self.manifest); path = self.payload/'worker_support/payload.v1.json'
        path.write_text('{"policy":"UCC_WORKER_PAYLOAD_V1",'+path.read_text()[1:])
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)
        value = json.loads(json.dumps(self.manifest)); value['engine_import_verified'] = True; self.write_manifest(value)
        with self.assertRaises(WorkerPayloadError): validate_worker_payload(self.payload)

    def test_changed_or_missing_payload_does_not_fall_back_to_checkout(self):
        (self.payload/'worker_support/payload.v1.json').unlink()
        with self.assertRaisesRegex(Exception, 'incomplete or changed'):
            worker_dependency_files(self.payload/'blender_bridge/entrypoint.py')
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', str(self.payload), create=True):
            with self.assertRaisesRegex(Exception, 'incomplete or changed'): bundled_native_adapter_path()

    def test_existing_destination_is_preserved_and_nonstdlib_closure_refused(self):
        before = (self.payload/'worker_support/payload.v1.json').read_bytes()
        with self.assertRaises(ValueError): builder.build_payload(ROOT, self.payload)
        self.assertEqual((self.payload/'worker_support/payload.v1.json').read_bytes(), before)
        # The isolated test checkout contains only first-party Python sources.
        source = self.root/'source'; shutil.copytree(ROOT/'src', source/'src', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT/'blender_bridge', source/'blender_bridge', ignore=shutil.ignore_patterns('__pycache__'))
        with (source/'src/ucc/core/worker_payload.py').open('a') as stream: stream.write('\nimport numpy\n')
        with self.assertRaisesRegex(ValueError, 'non-stdlib'): builder.build_payload(source, self.root/'rejected')
        self.assertFalse((self.root/'rejected').exists())


if __name__ == '__main__': unittest.main()
