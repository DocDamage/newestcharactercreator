"""Private installed-tool build, static import and independent fresh native admission."""
from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import json
import math
import os
import shutil
import subprocess
import time
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import UnrealExportRequest, ENGINE_VERSION, READINESS_FLAGS
from ucc.export.unreal_engine_profile import FBX_IMPORT_UI, FBX_IMPORT, LOD_BUILD, MESH_SETTINGS
from .unreal_preparation import PreparedUnrealSource
from .unreal_toolchain import UnrealToolchain
from .export_guards import bounded_paths, protected_file, cancel_context, failure_reason
from .godot_candidate_inputs import read_json, identity
from .master_preview import _digest
from .skin_material_preparation import _BudgetCancel
from .runner import _stop_tree
from .worker_resources import bundled_unreal_adapter_paths

CONTENT = frozenset({'Content/UCC/Character.uasset', 'Content/UCC/Character_Skeleton.uasset',
    'Content/UCC/SkinMaterial.uasset', 'Content/UCC/CharacterScene.umap'})
DELIVERY_FILES = CONTENT | {'Character.uproject', 'Config/DefaultEngine.ini', 'DerivedSources/character.fbx'}
CAPTURE_POLICY = 'UCC_UNREAL_NATIVE_BIND_CAPTURE_V1'
CAPTURE_FIELDS = frozenset({'schema_version', 'policy', 'mode', 'state', 'job_id',
    'request_sha256', 'toolchain_identity_sha256', 'engine_profile_sha256',
    'source_descriptor_path', 'source_descriptor_sha256', 'source_fbx_path', 'source_fbx_sha256',
    'observer_dll_sha256', 'observer_source_files', 'engine_exe_sha256', 'engine_build_sha256',
    'native_observation_path', 'native_observation_sha256', 'actual_import_settings',
    'actual_lod_build_settings', 'actual_mesh_settings', 'actual_triangle_order_optimization',
    'actual_assets', 'actual_material_graph', 'scene_actor_class', 'scene_actor_location',
    'scene_actor_rotation', 'scene_actor_scale', 'native_observation_captured'}) | READINESS_FLAGS
# Explicit settings are the installed, independently admitted legacy FBX profile.
IMPORT_PROFILE = {'fbx_import_ui': FBX_IMPORT_UI, 'skeletal_mesh_import_data': FBX_IMPORT,
    'stage_owned_lod0_build_settings': LOD_BUILD, 'stage_owned_mesh_settings': MESH_SETTINGS}


@dataclass(frozen=True, slots=True)
class PreparedUnrealEngine:
    project_directory: Path
    files: tuple[tuple[str, str], ...]
    request_sha256: str
    receipt_sha256: str
    workdir: Path
    maximum_source_position_error_m: float
    maximum_normal_angle_deg: float


def _write(path: Path, value) -> None:
    with path.open('xb') as stream:
        stream.write(canonical_bytes(value)); stream.flush(); os.fsync(stream.fileno())


def project_files(directory: Path, cancel=None) -> dict[str, str]:
    """Closed portable project, excluding every private observer and cache."""
    allowed = frozenset({'Content', 'Content/UCC', 'Config', 'DerivedSources'})
    result = {}
    for path in bounded_paths(directory, cancel, maximum_entries=128, allowed_directories=allowed):
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            if name not in DELIVERY_FILES:
                raise ProjectStorageError('Unreal delivery contains an unexpected file or private verification input')
            protected_file(path); result[name] = _digest(path, cancel)
    if set(result) != DELIVERY_FILES:
        raise ProjectStorageError('Unreal delivery is missing a required portable project asset')
    return result


def _tree(directory, cancel=None):
    return {p.relative_to(directory).as_posix(): _digest(p, cancel)
        for p in bounded_paths(directory, cancel, maximum_entries=16384) if p.is_file()}


def _copy(source, target, expected, cancel=None):
    protected_file(source)
    if _digest(source, cancel) != expected:
        raise ProjectStorageError('Unreal staged input changed before copying')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise ProjectStorageError('Unreal job refuses to replace an existing staged file')
    shutil.copyfile(source, target)
    if _digest(target, cancel) != expected:
        raise ProjectStorageError('Unreal staged copy differs from its sealed source')


def check_selected_compiler(build_log, toolchain):
    selected = [line for line in build_log.splitlines() if 'Using Visual Studio 2022' in line and 'toolchain' in line]
    if not selected or any(toolchain.compiler_version not in line or toolchain.sdk_version not in line for line in selected):
        raise ProjectStorageError('Unreal build did not prove the selected supported VS2022 compiler and Windows SDK')


def _private_cache(scripts: Path) -> Path:
    """Keep the stock Windows DDC root below its 119 UTF-16-unit limit."""
    if (not scripts.is_absolute() or not scripts.is_dir() or scripts.resolve() != scripts
            or any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
                   for path in (scripts, *scripts.parents))):
        raise ProjectStorageError('Unreal private scripts/cache parent is missing or redirected')
    cache = scripts.parent/'d'
    if len(cache.as_posix().encode('utf-16-le')) // 2 >= 119:
        raise ProjectStorageError('Unreal private cache root exceeds the installed 119-character limit; use a shorter saved project location')
    if cache.exists():
        if not cache.is_dir() or cache.is_symlink() or getattr(cache, 'is_junction', lambda: False)() or cache.resolve() != cache:
            raise ProjectStorageError('Unreal private cache directory was replaced or redirected')
    else:
        cache.mkdir(exist_ok=False)
    return cache


def _run(command, directory, budget, deadline):
    """Owned PID/tree only; no shell, raw engine diagnostics stay in private logs."""
    directory.mkdir(parents=True, exist_ok=True)
    reason, message = failure_reason(budget, deadline)
    if reason: raise ProjectStorageError(message)
    _write(directory/'command.json', {'command': command, 'shell': False})
    env = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONOPTIMIZE'): env.pop(name, None)
    env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1', DOTNET_NOLOGO='1')
    started = time.monotonic(); process = None
    with (directory/'stdout.log').open('xb') as stdout, (directory/'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, cwd=directory, env=env, shell=False, stdout=stdout, stderr=stderr,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        _write(directory/'owned-process.json', {'pid': process.pid, 'command': command})
        try:
            while process.poll() is None:
                reason, message = failure_reason(budget, deadline)
                if reason:
                    _stop_tree(process); break
                time.sleep(.04)
        except BaseException:
            _stop_tree(process); raise
    reason, message = failure_reason(budget, deadline)
    _write(directory/'process-result.json', {'pid': process.pid, 'return_code': process.returncode,
        'elapsed_seconds': time.monotonic()-started, 'failure_reason': reason})
    if reason: raise ProjectStorageError(message)
    if process.returncode:
        raise ProjectStorageError('Unreal private worker failed (exit '+str(process.returncode)+'); inspect retained logs at '+str(directory))


def _verification_project(directory, portable, resources, plugin_files, budget, scripts):
    directory.mkdir(parents=True, exist_ok=False)
    for name, expected in portable.items():
        _copy(resources['portable_root']/name, directory/name, expected, budget)
    plugin = directory/'Plugins/UccNativeObservation'
    for name, (source, expected) in plugin_files.items(): _copy(source, plugin/name, expected, budget)
    document = read_json(directory/'Character.uproject', 128*1024)
    document['Plugins'] = [{'Name': name, 'Enabled': True} for name in
        ('PythonScriptPlugin', 'EditorScriptingUtilities', 'SequencerScripting', 'Cascade', 'UccNativeObservation')]
    # Verification-only files are created in our new clone, never in delivered inputs.
    (directory/'Character.uproject').write_bytes(canonical_bytes(document))
    config = directory/'Config/DefaultEngine.ini'
    cache = _private_cache(scripts)
    config.write_text(config.read_text()+
        '\n[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\nbIsolateInterpreterEnvironment=True\n'
        '+AdditionalPaths=(Path="'+scripts.as_posix()+'")\n'
        '\n[DerivedDataCacheGraphs]\nUccPrivate=(UccLocal)\n[DerivedDataCacheStores]\n'
        'UccLocal=(Type=FileSystem,ReadOnly=false,Path="'+cache.as_posix()+'")\n', encoding='utf-8')


def _capture(project, output, mode, *, request, toolchain, profile_path, descriptor,
        material_spec, stage_receipt, scripts, budget, deadline):
    output.mkdir(parents=True, exist_ok=False)
    control = {'schema_version': 1, 'policy': 'UCC_UNREAL_EDITOR_JOB_V1', 'mode': mode,
        'export_request': request.to_dict(), 'request_sha256': request.sha256,
        'toolchain_identity_sha256': toolchain.identity_sha256,
        'engine_identity': {'editor_executable_sha256': request.unreal_executable_sha256,
            'build_version_sha256': request.unreal_build_version_sha256},
        'engine_profile_path': str(profile_path), 'engine_profile_sha256': _digest(profile_path, budget),
        'source_descriptor_path': str(descriptor), 'source_descriptor_sha256': _digest(descriptor, budget),
        'source_fbx_path': str(project/'DerivedSources/character.fbx'),
        'source_fbx_sha256': _digest(project/'DerivedSources/character.fbx', budget),
        'output_directory': str(output), 'material_spec': material_spec.to_dict(),
        'stage_receipt_path': str(stage_receipt) if stage_receipt else None,
        'stage_receipt_sha256': _digest(stage_receipt, budget) if stage_receipt else None}
    _write(project/'.ucc-job.json', control)
    before = _tree(project/'Content', budget)
    selected_script = 'stage.py' if mode == 'STAGE' else 'reopen.py'
    command = [str(toolchain.editor_exe), str(project/'Character.uproject'),
        '-ExecutePythonScript='+selected_script, '-NullRHI', '-RenderOffscreen', '-unattended',
        '-NoEpicPortal', '-nop4', '-nosound', '-NoAnalytics', '-NoSplash', '-DDC=UccPrivate',
        '-stdout', '-FullStdOutLogOutput', '-UTF8Output', '-abslog='+str(output/'UnrealEditor.log')]
    _run(command, output, budget, deadline)
    log = output/'UnrealEditor.log'; protected_file(log)
    if "InternalLoadLibrary: 'NullDrv'" not in log.read_text(encoding='utf-8-sig', errors='replace'):
        raise ProjectStorageError('Unreal worker did not prove actual NullDrv operation')
    if mode == 'FRESH' and before != _tree(project/'Content', budget):
        raise ProjectStorageError('Fresh Unreal verification changed saved assets')
    receipt = read_json(output/'capture-receipt.json', 2*1024*1024)
    expected = {'policy': CAPTURE_POLICY, 'state': 'CAPTURED_UNVERIFIED', 'mode': mode,
        'schema_version': 1, 'job_id': request.job_id, 'native_observation_captured': True,
        'request_sha256': request.sha256, 'toolchain_identity_sha256': toolchain.identity_sha256,
        'engine_profile_sha256': control['engine_profile_sha256'],
        'source_descriptor_path': str(descriptor), 'source_fbx_path': control['source_fbx_path'],
        'native_observation_path': str(output/'native-observation.json'),
        'engine_exe_sha256': request.unreal_executable_sha256,
        'engine_build_sha256': request.unreal_build_version_sha256,
        'source_descriptor_sha256': control['source_descriptor_sha256'],
        'source_fbx_sha256': control['source_fbx_sha256']}
    if set(receipt) != CAPTURE_FIELDS or any(receipt.get(k) != v for k, v in expected.items()) or any(receipt.get(k) is not False for k in READINESS_FLAGS):
        raise ProjectStorageError('Unreal capture receipt differs from its sealed job or claims premature readiness')
    native = output/'native-observation.json'; protected_file(native)
    if native.stat().st_size > 128*1024*1024 or _digest(native, budget) != receipt['native_observation_sha256']:
        raise ProjectStorageError('Unreal native observation changed or exceeds its output bound')
    return output/'capture-receipt.json'


def _admit(source, stage, reopened, request, toolchain, spec, budget, deadline):
    from ucc.export.unreal_bind_evidence import verify_unreal_bind
    files = dict(source.files)
    return verify_unreal_bind(source.directory/'source_reference.json', source.directory/'source_corner_normals.bin',
        stage/'native-observation.json', reopened_native_observation=reopened/'native-observation.json',
        stage_receipt=stage/'capture-receipt.json', stage_receipt_sha256=_digest(stage/'capture-receipt.json', budget),
        reopened_receipt=reopened/'capture-receipt.json', reopened_receipt_sha256=_digest(reopened/'capture-receipt.json', budget),
        request_sha256=request.sha256, toolchain_identity_sha256=toolchain.identity_sha256,
        source_reference_sha256=files['source_reference.json'], source_normals_sha256=files['source_corner_normals.bin'],
        native_observation_sha256=_digest(stage/'native-observation.json', budget),
        reopened_native_observation_sha256=_digest(reopened/'native-observation.json', budget),
        engine_version=ENGINE_VERSION, material_spec=spec,
        material_slot_name=source.expected_unreal_material_slot_name,
        imported_material_slot_name=source.expected_unreal_material_slot_name, cancel=budget, deadline=deadline)


def prepare_unreal_engine(source: PreparedUnrealSource, *, request: UnrealExportRequest,
        toolchain: UnrealToolchain, cancel=None, timeout_s=1800, progress=None) -> PreparedUnrealEngine:
    if (type(source) is not PreparedUnrealSource or type(request) is not UnrealExportRequest
            or type(toolchain) is not UnrealToolchain or source.request_sha256 != request.sha256
            or toolchain.identity_sha256 != request.toolchain_sha256
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Unreal engine preparation requires sealed matching source, request and installed toolchain')
    deadline, _ = cancel_context(cancel, time.monotonic()+timeout_s); budget = _BudgetCancel(cancel, deadline)
    work = source.workdir.parent/('ue-'+uuid4().hex[:16]); work.mkdir(exist_ok=False)
    try:
        return _prepare(source, request, toolchain, work, budget, deadline, progress)
    except BaseException as error:
        error.add_note('Unreal private work retained at '+str(work))
        raise


def _prepare(source, request, toolchain, work, budget, deadline, progress):
    toolchain.require_unchanged(budget)
    bound = dict(toolchain.files)
    if bound.get(str(toolchain.editor_exe)) != request.unreal_executable_sha256 or bound.get(str(toolchain.build_version)) != request.unreal_build_version_sha256:
        raise ValidationError('Unreal request names a different editor or engine build')
    protected = {source.directory/name: digest for name, digest in source.files}
    protected[source.directory/'unreal_source_verification.json'] = source.verification_sha256
    adapters = bundled_unreal_adapter_paths()
    protected.update({path: _digest(path, budget) for path in adapters.values()})
    def guard():
        toolchain.require_unchanged(budget)
        for path, digest in protected.items():
            protected_file(path)
            if _digest(path, budget) != digest: raise ProjectStorageError('Unreal protected source or adapter changed')
    guard()
    fbx_bytes = (source.directory/'character.fbx').read_bytes()
    for marker in (str(source.workdir), source.workdir.as_posix()):
        if marker.encode() in fbx_bytes or marker.encode('utf-16-le') in fbx_bytes:
            raise ProjectStorageError('Prepared Unreal FBX contains a private source work path')
    spec = SkinMaterialSpec.from_dict(read_json(source.directory/'source_reference.json', 64*1024*1024)['material_spec'])
    scripts = work/'scripts'; scripts.mkdir()
    for name in ('capture_common.py', 'stage.py', 'reopen.py'):
        _copy(adapters[name], scripts/name, protected[adapters[name]], budget)
        protected[scripts/name] = protected[adapters[name]]
    descriptor = work/'source-descriptor.json'
    _write(descriptor, {'schema_version': 1, 'policy': 'UCC_UNREAL_ENGINE_SOURCE_DESCRIPTOR_V1',
        'request_sha256': request.sha256, 'files': dict(source.files),
        'source_verification_sha256': source.verification_sha256, 'source_reference_supplied_to_engine': False})
    project = work/'p'; project.mkdir(); (project/'Content').mkdir()
    (project/'Config').mkdir(); (project/'DerivedSources').mkdir()
    for name, target in (('project.uproject', 'Character.uproject'), ('DefaultEngine.ini', 'Config/DefaultEngine.ini')):
        _copy(adapters[name], project/target, protected[adapters[name]], budget)
    plugin = project/'Plugins/UccNativeObservation'
    for name, path in adapters.items():
        if name.endswith('.uplugin') or name.startswith('Source/'):
            _copy(path, plugin/name, protected[path], budget)
            protected[plugin/name] = protected[path]
    document = read_json(project/'Character.uproject', 128*1024)
    document['Plugins'] = [{'Name': name, 'Enabled': True} for name in
        ('PythonScriptPlugin', 'EditorScriptingUtilities', 'SequencerScripting', 'Cascade', 'UccNativeObservation')]
    (project/'Character.uproject').write_bytes(canonical_bytes(document))
    config = project/'Config/DefaultEngine.ini'
    cache = _private_cache(scripts)
    initial_config = config.read_text().replace('EditorStartupMap=/Game/UCC/CharacterScene', '').replace('GameDefaultMap=/Game/UCC/CharacterScene', '')
    config.write_text(initial_config+'\n[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\nbIsolateInterpreterEnvironment=True\n'
        '+AdditionalPaths=(Path="'+scripts.as_posix()+'")\n\n[DerivedDataCacheGraphs]\nUccPrivate=(UccLocal)\n'
        '[DerivedDataCacheStores]\nUccLocal=(Type=FileSystem,ReadOnly=false,Path="'+cache.as_posix()+'")\n', encoding='utf-8')
    _copy(source.directory/'character.fbx', project/'DerivedSources/character.fbx', dict(source.files)['character.fbx'], budget)
    if progress: progress('OBSERVER_BUILD')
    command = [str(toolchain.dotnet), str(toolchain.ubt), 'UnrealEditor', 'Win64', 'Development',
        '-Project='+str(project/'Character.uproject'), '-Compiler=VisualStudio2022', '-CompilerVersion='+toolchain.compiler_version,
        '-WindowsSdkVersion='+toolchain.sdk_version, '-NoEngineChanges', '-NoHotReloadFromIDE', '-NoUBA', '-NoXGE', '-MaxParallelActions=2']
    _run(command, work/'build', budget, deadline)
    build_log = (work/'build/stdout.log').read_text(encoding='utf-8-sig', errors='replace')
    check_selected_compiler(build_log, toolchain)
    dll = plugin/'Binaries/Win64/UnrealEditor-UccNativeObservation.dll'; protected_file(dll)
    module = plugin/'Binaries/Win64/UnrealEditor.modules'
    if read_json(module, 2*1024*1024)['BuildId'] != read_json(toolchain.engine_root/'Binaries/Win64/UnrealEditor.modules', 8*1024*1024)['BuildId']:
        raise ProjectStorageError('Compiled observer BuildId differs from the selected installed engine')
    protected[dll] = _digest(dll, budget); protected[module] = _digest(module, budget)
    profile = dict(IMPORT_PROFILE); profile.update(observer_dll=str(dll), observer_dll_sha256=protected[dll],
        observer_source_sha256={name: protected[path] for name, path in adapters.items() if name.startswith('Source/') or name.endswith('.uplugin')})
    profile_path = work/'engine-profile.json'; _write(profile_path, profile)
    for path in (descriptor, profile_path, project/'Character.uproject', config):
        protected[path] = _digest(path, budget)
    if progress: progress('UNREAL_IMPORT')
    stage = work/'stage'; _capture(project, stage, 'STAGE', request=request, toolchain=toolchain,
        profile_path=profile_path, descriptor=descriptor, material_spec=spec, stage_receipt=None,
        scripts=scripts, budget=budget, deadline=deadline)
    for path in (stage/'capture-receipt.json', stage/'native-observation.json'):
        protected[path] = _digest(path, budget)
    guard()
    actual = _tree(project/'Content', budget)
    if {'Content/'+name for name in actual} != CONTENT:
        raise ProjectStorageError('Unreal produced an unexpected content asset inventory')
    # A source imported from inside this owned project must not serialize a private absolute job path.
    data = (project/'Content/UCC/Character.uasset').read_bytes()
    for marker in (str(project), project.as_posix(), str(source.workdir), source.workdir.as_posix()):
        if marker.encode() in data or marker.encode('utf-16-le') in data:
            raise ProjectStorageError('Unreal imported source metadata is absolute; portable provenance was not established')
    portable = work/'portable-project'; portable.mkdir()
    for name in CONTENT: _copy(project/name, portable/name, actual[name.removeprefix('Content/')], budget)
    for name, target in (('project.uproject', 'Character.uproject'), ('DefaultEngine.ini', 'Config/DefaultEngine.ini')):
        _copy(adapters[name], portable/target, protected[adapters[name]], budget)
    _copy(source.directory/'character.fbx', portable/'DerivedSources/character.fbx', dict(source.files)['character.fbx'], budget)
    files = project_files(portable, budget)
    plugin_files = {name: (plugin/name, digest) for name, digest in _tree(plugin, budget).items()
        if name.endswith('.uplugin') or name.startswith('Source/') or name in ('Binaries/Win64/UnrealEditor-UccNativeObservation.dll', 'Binaries/Win64/UnrealEditor.modules')}
    _verification_project(work/'reopened-project', files, {'portable_root': portable}, plugin_files, budget, scripts)
    if progress: progress('UNREAL_REOPEN')
    reopened = work/'reopened'; _capture(work/'reopened-project', reopened, 'FRESH', request=request, toolchain=toolchain,
        profile_path=profile_path, descriptor=descriptor, material_spec=spec, stage_receipt=stage/'capture-receipt.json',
        scripts=scripts, budget=budget, deadline=deadline)
    for path in (reopened/'capture-receipt.json', reopened/'native-observation.json'):
        protected[path] = _digest(path, budget)
    admission = _admit(source, stage, reopened, request, toolchain, spec, budget, deadline)
    guard()
    if files != project_files(portable, budget) or actual != _tree(project/'Content', budget):
        raise ProjectStorageError('Unreal saved project changed during native admission')
    receipt = {'schema_version': 1, 'policy': 'UCC_UNREAL_ENGINE_PREPARATION_V1', 'request_sha256': request.sha256,
        'toolchain_identity_sha256': toolchain.identity_sha256, 'source_descriptor_path': str(descriptor),
        'source_descriptor_sha256': _digest(descriptor, budget), 'engine_profile_path': str(profile_path),
        'engine_profile_sha256': _digest(profile_path, budget), 'source_fbx_sha256': dict(source.files)['character.fbx'],
        'stage_receipt_path': str(stage/'capture-receipt.json'), 'stage_receipt_sha256': _digest(stage/'capture-receipt.json', budget),
        'reopened_receipt_path': str(reopened/'capture-receipt.json'), 'reopened_receipt_sha256': _digest(reopened/'capture-receipt.json', budget),
        'files': files, 'observer_files': {name: {'path': str(path), 'sha256': digest} for name, (path, digest) in plugin_files.items()},
        'scripts_directory': str(scripts), 'admission': admission.to_dict(),
        **{name: name in ('engine_import_verified', 'source_parity_verified') for name in READINESS_FLAGS}}
    _write(work/'engine-receipt.json', receipt)
    return PreparedUnrealEngine(portable, tuple(sorted(files.items())), request.sha256,
        _digest(work/'engine-receipt.json', budget), work, admission.max_correspondence_error_cm/100,
        admission.max_normal_angle_degrees)
