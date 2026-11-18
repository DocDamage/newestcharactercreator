"""Private native Unreal animation import and fresh CPU playback admission."""
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export import unreal_animation_recipe as source_recipe
from ucc.export.unreal_animation_observation import ASSET_FIELDS, admit_unreal_animation
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import hash_file, read_bytes, read_metadata
from .target_action_context import operation_budget, protected
from .unreal_animation_source import PreparedUnrealAnimationSource
from .unreal_engine import _copy, _private_cache, _run, _tree, _write, check_selected_compiler
from .unreal_toolchain import UnrealToolchain
from .worker_resources import bundled_unreal_registered_paths


EDITOR_PLUGIN = 'UccNativeAnimation'
RUNTIME_PLUGIN = 'UccRegisteredPreview'
_MODULES = 'Binaries/Win64/UnrealEditor.modules'
PROJECT_FILE = 'AnimatedCharacter.uproject'
PROJECT_CONFIG = 'Config/DefaultEngine.ini'
NATIVE_RECEIPT = 'unreal-animation-native-receipt.json'
_RAW_SOURCE = 'unreal_animated_raw_positions.f32'
_BONE_SOURCE = 'unreal_animated_world_bones.f32'
_MAX_ASSET = 512 * 1024**2


@dataclass(frozen=True, slots=True)
class VerifiedUnrealNativeAnimation:
    directory: Path
    receipt_sha256: str


def _make_project(project: Path, cache: Path | None, *, preview: bool = False, observer: bool = True,
                  cache_archive: Path | None = None) -> None:
    project.mkdir(exist_ok=False)
    (project/'Content').mkdir()
    (project/'Config').mkdir()
    plugins = ('Cascade', 'ACLPlugin', 'ProceduralMeshComponent', RUNTIME_PLUGIN)
    if observer:
        plugins += (EDITOR_PLUGIN,)
    _write(project/PROJECT_FILE, dict(FileVersion=3, EngineAssociation='5.9',
        Category='UCC private animated character', DisableEnginePluginsByDefault=True,
        Plugins=[dict(Name=name, Enabled=True) for name in plugins]))
    config = (
        '[ConsoleVariables]\nr.TriangleOrderOptimization=2\nInterchange.FeatureFlags.Import.FBX=False\n'
        '\n[Analytics]\nProviderModuleName=\n'
        '\n[/Script/UnrealEd.AnalyticsPrivacySettings]\nbSendUsageData=False\n'
    )
    if preview:
        config += ('\n[/Script/EngineSettings.GameMapsSettings]\n'
                   'EditorStartupMap=/Game/UccAnimation/CharacterScene\n'
                   'GameDefaultMap=/Game/UccAnimation/CharacterScene\n')
    if cache is not None:
        if any(c in cache.as_posix() for c in ('"', '\n', '\r')):
            raise ValidationError('Unreal private cache needs a plain canonical path')
        archive = cache_archive.as_posix() if cache_archive is not None else None
        if archive is not None and any(c in archive for c in ('"', '%', '\n', '\r')):
            raise ValidationError('Unreal installed cache archive needs a plain canonical path')
        graph = '(UccInstalled,UccLocal)' if archive else '(UccLocal)'
        config += ('\n[DerivedDataCacheGraphs]\nUccPrivate='+graph+'\n[DerivedDataCacheStores]\n'
                   'UccLocal=(Type=FileSystem,ReadOnly=false,Path="'+cache.as_posix()+'")\n')
        if archive:
            config += 'UccInstalled=(Type=ReadPak,Filename="'+archive+'",Compressed=true)\n'
    elif preview:
        config += ('\n[DerivedDataCacheGraphs]\nDefault=(UccLocal)\nInstalled=(InstalledEnginePak,UccLocal)\n'
                   '[DerivedDataCacheStores]\n'
                   'UccLocal=(Type=FileSystem,ReadOnly=false,Path="%GAMEDIR%DerivedDataCache")\n')
    (project/PROJECT_CONFIG).write_bytes(config.encode('utf-8'))


def verify_unreal_native_animation(prepared: PreparedUnrealAnimationSource, *, toolchain: UnrealToolchain,
        work: Path, guard: Callable[[], None], cancel: Event | None = None, timeout_s: float = 1200,
        progress: Callable[[str], None] | None = None) -> VerifiedUnrealNativeAnimation:
    """Run the installed editor on private copies and require independent raw-skin/pose parity."""
    if (type(prepared) is not PreparedUnrealAnimationSource or type(toolchain) is not UnrealToolchain
            or prepared.fbx_path != prepared.directory/source_recipe.FBX):
        raise ValidationError('Unreal animation needs the independently reopened Blender source and installed toolchain')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        report_path = prepared.directory/source_recipe.VERIFY_REPORT
        report, _, proof_sha = read_metadata(report_path, 256 * 1024, budget,
                                              expected_sha256=prepared.verification_sha256)
        files = report.get('files')
        if (report.get('policy') != source_recipe.POLICY or report.get('target_binding_sha256') != prepared.binding_sha256
                or report.get('fbx_basis_model') != 'UccAnimationBasis'
                or report.get('engine_import_verified') is not False
                or report.get('blender_fbx_reimport_verified') is not True
                or report.get('recomputed_source_references') is not True
                or type(files) is not dict or set(files) != set(source_recipe.OUTPUT_LIMITS)):
            raise ValidationError('Unreal animation source report does not confirm the exact registered action')
        adapter = bundled_unreal_registered_paths()
        scripts = {name: hash_file(path, 256 * 1024, budget)[0] for name, path in adapter.items()}
        watched = {report_path: (proof_sha, 256 * 1024),
                   **{prepared.directory/name: (digest, source_recipe.OUTPUT_LIMITS[name]) for name, digest in files.items()},
                   **{adapter[name]: (digest, 256 * 1024) for name, digest in scripts.items()}}

        def unchanged() -> None:
            budget.check()
            guard()
            if identity(protected(work)) != owner:
                raise ProjectStorageError('Unreal animation workspace was replaced')
            toolchain.require_unchanged(budget.cancel)
            for path, (digest, maximum) in watched.items():
                if hash_file(path, maximum, budget)[0] != digest:
                    raise ProjectStorageError('Unreal animation source or first-party observer changed')

        work = Path(work)
        protected(work.parent)
        work.mkdir(exist_ok=False)
        owner = identity(work)
        scripts_anchor = work/'scripts'
        scripts_anchor.mkdir()
        cache = _private_cache(scripts_anchor)
        stage, fresh = work/'stage', work/'fresh'
        _make_project(stage, cache)
        stage_plugin = stage/'Plugins'
        for name, digest in scripts.items():
            _copy(adapter[name], stage_plugin/name, digest, budget.cancel)
            watched[stage_plugin/name] = (digest, 256 * 1024)
        fbx = stage/'DerivedSources'/source_recipe.FBX
        _copy(prepared.fbx_path, fbx, files[source_recipe.FBX], budget.cancel)
        watched[fbx] = (files[source_recipe.FBX], source_recipe.OUTPUT_LIMITS[source_recipe.FBX])
        project_file = stage/PROJECT_FILE
        for path in (project_file, stage/PROJECT_CONFIG):
            watched[path] = (hash_file(path, 128 * 1024, budget)[0], 128 * 1024)
        unchanged()
        if progress is not None:
            progress('UNREAL_ANIMATION_OBSERVER_BUILD')
        _run([str(toolchain.dotnet), str(toolchain.ubt), 'UnrealEditor', 'Win64', 'Development',
            '-Project='+str(project_file), '-Compiler=VisualStudio2022', '-CompilerVersion='+toolchain.compiler_version,
            '-WindowsSdkVersion='+toolchain.sdk_version, '-NoEngineChanges', '-NoHotReloadFromIDE', '-NoUBA',
            '-NoXGE', '-MaxParallelActions=2', '-WaitMutex', '-Log='+str(work/'build/UnrealBuildTool.log')],
            work/'build', budget.user, budget.deadline)
        check_selected_compiler((work/'build/stdout.log').read_text(encoding='utf-8-sig', errors='replace'), toolchain)
        engine_modules = toolchain.engine_root/_MODULES
        engine_module_data, _, engine_module_sha = read_metadata(engine_modules, 8 * 1024**2, budget)
        watched[engine_modules] = (engine_module_sha, 8 * 1024**2)
        binaries = {}
        for plugin in (EDITOR_PLUGIN, RUNTIME_PLUGIN):
            compiled_modules = read_metadata(stage_plugin/plugin/_MODULES, 2 * 1024**2, budget)[0]
            if compiled_modules.get('BuildId') != engine_module_data.get('BuildId') or not engine_module_data.get('BuildId'):
                raise ProjectStorageError('Unreal animation plugin BuildId differs from the selected editor')
            dll = f'Binaries/Win64/UnrealEditor-{plugin}.dll'
            for filename in (_MODULES, dll):
                name = f'{plugin}/{filename}'
                binaries[name] = hash_file(stage_plugin/name, _MAX_ASSET, budget)[0]
        watched.update({stage_plugin/name: (digest, _MAX_ASSET) for name, digest in binaries.items()})

        def capture(project: Path, phase: str, *, input_fbx: Path | None) -> Path:
            unchanged()
            if progress is not None:
                progress('UNREAL_ANIMATION_'+phase.upper())
            output = work/(phase+'-output')
            output.mkdir()
            log_path = work/(phase+'-UnrealEditor.log')
            command = [str(toolchain.editor_exe), str(project/PROJECT_FILE),
                '-run=UccNativeAnimation', '-UccPhase='+phase, '-UccOutput='+str(output),
                '-NullRHI', '-RenderOffscreen', '-Unattended', '-NoEpicPortal', '-NoP4', '-NoSound',
                '-NoAnalytics', '-NoSplash', '-DDC=UccPrivate', '-stdout', '-FullStdOutLogOutput',
                '-UTF8Output', '-abslog='+str(log_path)]
            if input_fbx is not None:
                command.append('-UccFbx='+str(input_fbx))
            _run(command, work/(phase+'-process'), budget.user, budget.deadline)
            log, log_sha = read_bytes(log_path, 64 * 1024**2, budget)
            if b"InternalLoadLibrary: 'NullDrv'" not in log or b'Success - 0 error(s)' not in log:
                raise ProjectStorageError('Unreal did not confirm the actual CPU-only native commandlet')
            watched[log_path] = (log_sha, 64 * 1024**2)
            unchanged()
            return output

        stage_output = capture(stage, 'Stage', input_fbx=fbx)
        stage_report, _, stage_sha = read_metadata(stage_output/'import.json', 128 * 1024, budget)
        watched[stage_output/'import.json'] = (stage_sha, 128 * 1024)
        content = _tree(stage/'Content', budget.cancel)
        if (len(content) != 3 or any(not name.startswith('UccAnimation/') or not name.endswith('.uasset')
                for name in content) or any(type(stage_report.get(key)) is not str for key in ASSET_FIELDS)):
            raise ValidationError('Unreal animation import did not save exactly one mesh, skeleton and clip')
        _make_project(fresh, cache)
        for path in (fresh/PROJECT_FILE, fresh/PROJECT_CONFIG):
            watched[path] = (hash_file(path, 128 * 1024, budget)[0], 128 * 1024)
        fresh_plugin = fresh/'Plugins'
        for name, digest in (scripts | binaries).items():
            _copy(stage_plugin/name, fresh_plugin/name, digest, budget.cancel)
            watched[fresh_plugin/name] = (digest, _MAX_ASSET)
        for name, digest in content.items():
            _copy(stage/'Content'/name, fresh/'Content'/name, digest, budget.cancel)
        fresh_output = capture(fresh, 'Verify', input_fbx=None)
        if _tree(fresh/'Content', budget.cancel) != content or _tree(stage/'Content', budget.cancel) != content:
            raise ProjectStorageError('Fresh Unreal native animation changed the saved content')
        observation, _, native_sha = read_metadata(fresh_output/'observation.json', 2 * 1024**2, budget)
        native_bind, _, bind_sha = read_metadata(fresh_output/'bind.json', 32 * 1024**2, budget)
        source_bind, _, _ = read_metadata(prepared.directory/source_recipe.BIND,
            source_recipe.OUTPUT_LIMITS[source_recipe.BIND], budget, expected_sha256=files[source_recipe.BIND])
        reference = {name: read_bytes(prepared.directory/name, source_recipe.OUTPUT_LIMITS[name], budget,
                                     expected_sha256=files[name])[0] for name in (_BONE_SOURCE, _RAW_SOURCE)}
        native_pose, pose_sha = read_bytes(fresh_output/'pose_world.f32', 16 * 1024**2, budget)
        native_skin, skin_sha = read_bytes(fresh_output/'raw_skin_world.f32', 384 * 1024**2, budget)
        for name, digest, maximum in (('observation.json', native_sha, 2 * 1024**2),
                ('bind.json', bind_sha, 32 * 1024**2), ('pose_world.f32', pose_sha, 16 * 1024**2),
                ('raw_skin_world.f32', skin_sha, 384 * 1024**2)):
            watched[fresh_output/name] = (digest, maximum)
        comparison = admit_unreal_animation(stage=stage_report, observation=observation, native_bind=native_bind,
            source_bind=source_bind, original_pose=reference[_BONE_SOURCE], original_skin=reference[_RAW_SOURCE],
            native_pose=native_pose, native_skin=native_skin, check=budget.check)
        unchanged()
        receipt = work/NATIVE_RECEIPT
        _write(receipt, dict(schema_version=1, policy='UCC_UNREAL_NATIVE_ANIMATION_ADMISSION_V1',
            toolchain_identity_sha256=toolchain.identity_sha256, blender_verification_sha256=proof_sha,
            stage_sha256=stage_sha, native_observation_sha256=native_sha, bind_sha256=bind_sha,
            native_pose_sha256=pose_sha, native_skin_sha256=skin_sha, content=content, plugins=scripts | binaries,
            result=asdict(comparison),
            native_import_verified=True, native_preview_loop_verified=True, corrective_runtime_verified=False,
            pie_verified=False, export_published=False))
        return VerifiedUnrealNativeAnimation(fresh, hash_file(receipt, 512 * 1024, budget)[0])
