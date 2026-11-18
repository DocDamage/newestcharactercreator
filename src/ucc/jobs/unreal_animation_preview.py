"""Stage a saved Unreal preview and admit corrected live Play in Editor evidence."""
from dataclasses import asdict, dataclass
from pathlib import Path
from stat import FILE_ATTRIBUTE_REPARSE_POINT, S_ISREG
from threading import Event
from typing import Callable

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import checked_sha
from ucc.export import unreal_animation_recipe as source_recipe
from ucc.export.unreal_corrected_animation_evidence import compare_unreal_corrected_animation
from .godot_candidate_inputs import identity
from .godot_registered_runtime_files import hash_file, read_bytes, read_metadata
from .target_action_context import operation_budget, protected
from .unreal_animation_correction_inputs import CORRECTION_PACKET, PACKET_LIMIT, build_unreal_correction_packet
from .unreal_animation_engine import (
    EDITOR_PLUGIN, NATIVE_RECEIPT, PROJECT_CONFIG, PROJECT_FILE, RUNTIME_PLUGIN,
    VerifiedUnrealNativeAnimation, _make_project,
)
from .unreal_animation_source import PreparedUnrealAnimationSource
from .unreal_engine import _copy, _private_cache, _run, _tree, _write
from .unreal_toolchain import UnrealToolchain
from .worker_resources import bundled_unreal_registered_paths


PLAYBACK_RECEIPT = 'unreal-animation-corrected-receipt.json'
PLAYBACK_POLICY = 'UCC_UNREAL_CORRECTED_ANIMATION_ADMISSION_V1'
SCENE = '/Game/UccAnimation/CharacterScene'
MAP = 'UccAnimation/CharacterScene.umap'
NATIVE_ASSETS = frozenset(f'UccAnimation/{name}.uasset' for name in ('Character', 'Character_Skeleton', 'Character_Anim'))
_POS = 'unreal_animated_corrected_positions.f32'
_NORMALS = 'unreal_animated_corrected_normals.f32'
_MAX = 512 * 1024**2
_MAX_LOG = 64 * 1024**2
_MAX_SHADER_ARCHIVE = 8 * 1024**3
_RASTER_WITNESSES = ('preview-frame-075.png', 'preview-frame-225.png')
_RASTER_HEADER = bytes.fromhex('89504e470d0a1a0a0000000d494844520000010000000100')


@dataclass(frozen=True, slots=True)
class VerifiedUnrealPreview:
    directory: Path
    receipt_sha256: str


def expected_plugin_files(source_names) -> set[str]:
    return set(source_names) | {
        f'{plugin}/Binaries/Win64/{name}'
        for plugin in (EDITOR_PLUGIN, RUNTIME_PLUGIN)
        for name in ('UnrealEditor.modules', f'UnrealEditor-{plugin}.dll')
    }


def _project_files(project: Path, budget) -> dict[str, str]:
    groups = {f'{name}/{relative}': digest
              for name in ('Content', 'Plugins', 'Config')
              for relative, digest in _tree(project/name, budget.cancel).items()}
    groups[PROJECT_FILE] = hash_file(project/PROJECT_FILE, 128 * 1024, budget)[0]
    return groups


def _require_observation(observation: dict, expected: dict, *, raster: bool) -> None:
    raster_fields = {'raster_foreground_pixels', 'raster_changed_pixels'} if raster else set()
    if (set(observation) != set(expected) | raster_fields
            or any(type(observation[key]) is not type(value) or observation[key] != value for key, value in expected.items())):
        raise ValidationError('Unreal preview observation differs from the exact saved scene, packet or playback scope')
    if raster:
        foreground, changed = (observation[key] for key in ('raster_foreground_pixels', 'raster_changed_pixels'))
        if (type(foreground) is not int or type(changed) is not int
                or not 64 < foreground <= 256**2 or not 16 < changed <= 256**2):
            raise ValidationError('Unreal did not rasterize a changing lit preview')


def _shader_archive_stamp(path: Path, budget) -> tuple[tuple[int, int, int, int], int, str]:
    info = protected(path).stat()
    if (not S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT):
        raise ProjectStorageError('Unreal installed shader cache archive is redirected or shared')
    return identity(path), info.st_ctime_ns, hash_file(path, _MAX_SHADER_ARCHIVE, budget)[0]


def verify_unreal_preview(source: PreparedUnrealAnimationSource, native: VerifiedUnrealNativeAnimation, *,
        toolchain: UnrealToolchain, work: Path, guard: Callable[[], None], cancel: Event | None = None,
        timeout_s: float = 1200, progress: Callable[[str], None] | None = None) -> VerifiedUnrealPreview:
    if (type(source) is not PreparedUnrealAnimationSource or type(native) is not VerifiedUnrealNativeAnimation
            or type(toolchain) is not UnrealToolchain):
        raise ValidationError('Unreal preview requires the admitted Blender input, native scene and installed toolchain')
    with operation_budget(cancel, timeout_s) as budget:
        guard()
        raw_receipt = native.directory.parent/NATIVE_RECEIPT
        raw, _, _ = read_metadata(raw_receipt, 512 * 1024, budget, expected_sha256=native.receipt_sha256)
        proof_path = source.directory/source_recipe.VERIFY_REPORT
        proof, _, _ = read_metadata(proof_path, 256 * 1024, budget, expected_sha256=source.verification_sha256)
        content, plugins = raw.get('content'), raw.get('plugins')
        resources = bundled_unreal_registered_paths()
        if (raw.get('toolchain_identity_sha256') != toolchain.identity_sha256 or type(content) is not dict
                or set(content) != NATIVE_ASSETS or type(plugins) is not dict
                or set(plugins) != expected_plugin_files(resources)):
            raise ValidationError('Unreal preview input is missing its exact native project and first-party plugin inventory')
        if any(hash_file(path, 256 * 1024, budget)[0] != checked_sha(plugins[name])
               for name, path in resources.items()):
            raise ProjectStorageError('Unreal preview plugin source differs from the compiled native input')
        work = Path(work)
        protected(work.parent)
        work.mkdir()
        owner = identity(work)
        scripts_anchor = work/'scripts'
        scripts_anchor.mkdir()
        cache = _private_cache(scripts_anchor)
        packet = work/CORRECTION_PACKET
        correction = build_unreal_correction_packet(source, native, packet, budget)
        native_paths = {f'Content/{name}': checked_sha(digest) for name, digest in content.items()}
        plugin_paths = {f'Plugins/{name}': checked_sha(digest) for name, digest in plugins.items()}
        persistent = {raw_receipt: native.receipt_sha256, proof_path: source.verification_sha256, packet: correction.sha256}

        def unchanged() -> None:
            budget.check()
            guard()
            toolchain.require_unchanged(budget.cancel)
            if identity(protected(work)) != owner or any(
                    hash_file(path, _MAX, budget)[0] != digest for path, digest in persistent.items()):
                raise ProjectStorageError('Unreal preview proof or workspace changed')
            if (_tree(native.directory/'Content', budget.cancel) != content
                    or any(hash_file(native.directory/name, _MAX, budget)[0] != digest
                           for name, digest in plugin_paths.items())):
                raise ProjectStorageError('Unreal preview native input changed')

        stage = work/'stage'
        _make_project(stage, cache)
        for name, digest in (native_paths | plugin_paths).items():
            _copy(native.directory/name, stage/name, digest, budget.cancel)
        initial = _project_files(stage, budget)
        options = ['-RenderOffscreen', '-Unattended', '-NoEpicPortal', '-NoAnalytics', '-NoP4', '-NoSound',
                   '-NoSplash', '-DDC=UccPrivate', '-stdout', '-FullStdOutLogOutput', '-UTF8Output']
        stage_output = work/'stage-output'
        stage_output.mkdir()
        unchanged()
        if progress:
            progress('UNREAL_STAGE_CORRECTED_PREVIEW')
        stage_log = work/'StagePreview-UnrealEditor.log'
        _run([str(toolchain.editor_exe), str(stage/PROJECT_FILE), '-run=UccNativeAnimation', '-UccPhase=StagePreview',
              '-UccPreviewPacket='+str(packet), '-UccOutput='+str(stage_output), '-NullRHI',
              '-abslog='+str(stage_log), *options], work/'stage-process', budget.user, budget.deadline)
        stage_log_bytes, _ = read_bytes(stage_log, _MAX_LOG, budget)
        if b'Success - 0 error(s)' not in stage_log_bytes:
            raise ProjectStorageError('Unreal preview staging did not complete its native commandlet')
        actual = _project_files(stage, budget)
        map_relative = 'Content/'+MAP
        if actual != initial | {map_relative: actual.get(map_relative)} or not actual.get(map_relative):
            raise ProjectStorageError('Unreal preview staging changed saved inputs or produced unexpected assets')
        staged, _, stage_sha = read_metadata(stage_output/'preview-stage.json', 128 * 1024, budget)
        fixed = dict(schema_version=1, scene=SCENE, packet_sha256=correction.sha256,
                     native_vertices=len(correction.native_to_source))
        _require_observation(staged, fixed | {'policy': 'UCC_UNREAL_REGISTERED_PREVIEW_STAGE_V1'}, raster=False)
        persistent[stage_output/'preview-stage.json'] = stage_sha
        preview_content = native_paths | {map_relative: actual[map_relative]}
        runtime = {name: digest for name, digest in plugin_paths.items() if name.startswith(f'Plugins/{RUNTIME_PLUGIN}/')}
        portable, fresh = work/'portable', work/'fresh'
        shader_archive = toolchain.engine_root/'DerivedDataCache/Compressed.ddp'
        try:
            shader_stamp = _shader_archive_stamp(shader_archive, budget)
        except FileNotFoundError:
            shader_stamp = None
        for project, project_cache, observer, scripts in ((portable, None, False, runtime),
                (fresh, cache, True, plugin_paths)):
            _make_project(project, project_cache, preview=True, observer=observer,
                          cache_archive=shader_archive if observer and shader_stamp is not None else None)
            for name, digest in (preview_content | scripts).items():
                _copy(stage/name, project/name, digest, budget.cancel)
        portable_files, fresh_files = _project_files(portable, budget), _project_files(fresh, budget)
        output = work/'pie-output'
        output.mkdir()
        pie_log = work/'Preview-UnrealEditor.log'
        unchanged()
        if progress:
            progress('UNREAL_VERIFY_CORRECTED_PIE')
        _run([str(toolchain.editor_exe), str(fresh/PROJECT_FILE), '-d3d12', '-UccPreviewVerify='+str(output),
              '-abslog='+str(pie_log), *options], work/'pie-process', budget.user, budget.deadline)
        log, log_sha = read_bytes(pie_log, _MAX_LOG, budget)
        if b'LogD3D12RHI:' not in log or b"InternalLoadLibrary: 'NullDrv'" in log:
            raise ProjectStorageError('Unreal corrected PIE did not run on the installed Direct3D renderer')
        archive_opened = (shader_archive.as_posix()+': Opened pak cache for reading.').encode('utf-8')
        if shader_stamp is not None and (archive_opened not in log
                or _shader_archive_stamp(shader_archive, budget) != shader_stamp):
            raise ProjectStorageError('Unreal did not use the unchanged installed read-only shader archive')
        observation, _, observed_sha = read_metadata(output/'preview-observation.json', 128 * 1024, budget)
        _require_observation(observation, fixed | dict(policy='UCC_UNREAL_REGISTERED_PREVIEW_OBSERVATION_V1',
            frames=300, fps=30, corrected_submit_verified=True, normal_loop_wrap_verified=True,
            lit_motion_verified=True), raster=True)
        raster_sha = {}
        for name in _RASTER_WITNESSES:
            raster, raster_sha[name] = read_bytes(output/name, 512 * 1024, budget)
            if not raster.startswith(_RASTER_HEADER):
                raise ValidationError('Unreal PIE raster witness is missing its exact 256-pixel PNG header')
            persistent[output/name] = raster_sha[name]
        sample_path = output/'corrected_skin_world.f32'
        samples, samples_sha = read_bytes(sample_path, 300*len(correction.native_to_source)*24, budget)
        originals = {name: read_bytes(source.directory/name, source_recipe.OUTPUT_LIMITS[name], budget,
            expected_sha256=checked_sha(proof['files'][name]))[0] for name in (_POS, _NORMALS)}
        result = compare_unreal_corrected_animation(source_positions=originals[_POS], source_normals=originals[_NORMALS],
            native_samples=samples, native_to_source=correction.native_to_source, check=budget.check)
        persistent.update({pie_log: log_sha, output/'preview-observation.json': observed_sha, sample_path: samples_sha,
                           source.directory/_POS: proof['files'][_POS], source.directory/_NORMALS: proof['files'][_NORMALS]})
        unchanged()
        if (_project_files(stage, budget) != actual or _project_files(fresh, budget) != fresh_files
                or _project_files(portable, budget) != portable_files):
            raise ProjectStorageError('Unreal corrected preview changed the sealed scene or runtime')
        receipt = work/PLAYBACK_RECEIPT
        _write(receipt, dict(schema_version=1, policy=PLAYBACK_POLICY, source_binding_sha256=source.binding_sha256,
            blender_verification_sha256=source.verification_sha256, native_receipt_sha256=native.receipt_sha256,
            toolchain_identity_sha256=toolchain.identity_sha256, packet_sha256=correction.sha256,
            observation_sha256=observed_sha, samples_sha256=samples_sha, raster_sha256=raster_sha,
            installed_shader_archive_sha256=shader_stamp[-1] if shader_stamp is not None else None,
            comparison=asdict(result),
            corrected_runtime_verified=True, pie_verified=True, normal_loop_wrap_verified=True,
            lit_motion_verified=True, portable_files=portable_files, export_published=False))
        return VerifiedUnrealPreview(portable, hash_file(receipt, 512 * 1024, budget)[0])
