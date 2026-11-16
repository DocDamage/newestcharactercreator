"""Closed Unity delivery inventory; private sampling/import evidence stays on host."""
from pathlib import Path
from hashlib import sha256
from collections.abc import Iterator
import shutil
import os
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_contract import UnityExportRequest
from .godot_candidate_inputs import regular_file, identity, read_json
from .master_preview import _digest
from .worker_resources import bundled_unity_adapter_paths

PRIVATE_INPUTS = frozenset('Assets/UCC/'+name+suffix for name in
    ('source_reference.json', 'source_weights.json') for suffix in ('', '.meta'))
SETTINGS = frozenset(('AudioManager.asset', 'ClusterInputManager.asset', 'DynamicsManager.asset',
    'EditorBuildSettings.asset', 'EditorSettings.asset', 'GraphicsSettings.asset', 'InputManager.asset',
    'MemorySettings.asset', 'MultiplayerManager.asset', 'NavMeshAreas.asset', 'Physics2DSettings.asset',
    'PresetManager.asset', 'ProjectSettings.asset', 'ProjectVersion.txt', 'QualitySettings.asset',
    'SceneTemplateSettings.json', 'TagManager.asset', 'TimeManager.asset', 'UnityConnectSettings.asset',
    'VFXManager.asset', 'VersionControlSettings.asset'))
GENERATED = ('Character.prefab', 'Character.unity', 'CharacterSkin.asset', 'CharacterSkin.mat',
             'character.fbx', 'source_quads.json')
ROOT_INPUTS = frozenset(('request.json', 'engine_recipe.json', 'README.txt'))
PAYLOAD_DIRECTORIES = frozenset(('Assets', 'Assets/UCC', 'Assets/UCC/Editor', 'Packages', 'ProjectSettings'))
RECEIPT = 'export_receipt.json'
POLICY = 'UCC_UNITY_EXPORT_TRANSACTION_V1'


def bounded_paths(root: Path, cancel=None, *, maximum_entries: int=8192,
        counter: list[int] | None=None, allowed_directories: frozenset[str] | None=None) -> Iterator[Path]:
    """Stream a canonical tree without queuing children or following redirects.

    The entry budget includes directories and missing selected roots. Shared
    counters bound a multi-root closure. Check before requesting each next entry,
    so reaching the hard limit rejects conservatively without probing further.
    """
    used = [0] if counter is None else counter

    def check() -> None:
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError('Unity input traversal cancelled or total deadline exceeded')
        if used[0] >= maximum_entries:
            raise ProjectStorageError('Unity input traversal reached its bounded entry limit')

    def canonical(path: Path) -> None:
        if path.is_symlink() or getattr(path, 'is_junction', lambda:False)() or path.resolve() != path:
            raise ProjectStorageError('Unity input traversal contains a redirected path')

    def visit(path: Path, depth: int) -> Iterator[Path]:
        check(); used[0] += 1
        canonical(path)
        directory = path.is_dir()
        if directory:
            if (path != root and allowed_directories is not None
                    and path.relative_to(root).as_posix() not in allowed_directories):
                raise ProjectStorageError('Unity export contains an unlisted directory or cache')
            if depth >= 128:
                raise ProjectStorageError('Unity input traversal exceeds its bounded directory depth')
        elif path.exists() and not path.is_file():
            raise ProjectStorageError('Unity input traversal contains an unsupported filesystem entry')
        yield path
        if directory:
            check(); canonical(path)
            with os.scandir(path) as children:
                while True:
                    check()
                    try:
                        entry = next(children)
                    except StopIteration:
                        break
                    yield from visit(path/entry.name, depth+1)

    yield from visit(root, 0)


def engine_payload() -> frozenset[str]:
    scripts = bundled_unity_adapter_paths()
    return frozenset({'Assets/UCC.meta', 'Assets/UCC/Editor.meta', 'Packages/manifest.json',
        *('ProjectSettings/'+name for name in SETTINGS),
        *('Assets/UCC/'+name+suffix for name in (*GENERATED, *scripts) for suffix in ('', '.meta'))})


def snapshot(root: Path, cancel=None) -> dict[str, str]:
    """Reject redirected paths and seal every file, including unexpected ones."""
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise ProjectStorageError('Unity export folder is missing or redirected')
    result = {}
    for path in bounded_paths(root, cancel, maximum_entries=1024, allowed_directories=PAYLOAD_DIRECTORIES):
        if path == root:
            continue
        if path.is_file():
            if len(result) >= 512:
                raise ProjectStorageError('Unity export exceeds its bounded file inventory')
            regular_file(path, root, 512*1024*1024)
            result[path.relative_to(root).as_posix()] = _digest(path, cancel)
    return result


def check_snapshot(root: Path, expected: dict[str, str], cancel=None) -> None:
    if snapshot(root, cancel) != expected:
        raise ProjectStorageError('Unity export payload was altered, added to or removed')


def stage_payload(engine, destination: Path, request: UnityExportRequest, cancel=None) -> dict[str, str]:
    receipt_path = regular_file(engine.directory.parent/'native-import-receipt.json', engine.directory.parent, 2*1024*1024)
    if _digest(receipt_path, cancel) != engine.receipt_sha256:
        raise ProjectStorageError('Unity native import receipt changed before delivery')
    receipt = read_json(receipt_path, 2*1024*1024)
    saved = receipt.get('saved_files')
    allowed = engine_payload()
    if (type(saved) is not dict or set(saved) != allowed | PRIVATE_INPUTS
            or any(not is_sha256(value) for value in saved.values())):
        raise ValidationError('Unity native import contains an unsupported or incomplete delivery inventory')
    reference_path = regular_file(engine.directory/'Assets/UCC/source_reference.json', engine.directory, 64*1024*1024)
    if _digest(reference_path, cancel) != saved['Assets/UCC/source_reference.json']:
        raise ProjectStorageError('Unity original import reference changed before delivery')
    spec = SkinMaterialSpec.from_dict(read_json(reference_path, 64*1024*1024).get('material_spec'))
    expected_recipe = {'schema_version':1, 'policy':'UCC_UNITY_EDITOR_JOB_V1',
        'request_sha256':request.sha256, 'master_sha256':dict(request.source_bindings)['master'],
        'weights_sha256':saved['Assets/UCC/source_weights.json'], 'fbx_sha256':saved['Assets/UCC/character.fbx'],
        'source_reference_sha256':saved['Assets/UCC/source_reference.json'],
        'native_mesh_sha256':engine.native_mesh_sha256, 'topology_sha256':engine.topology_sha256,
        'color_srgb':dict(zip('rgba', (*spec.base_color_srgb, 1.))), 'roughness':spec.roughness}
    recipe_path = regular_file(engine.directory/'engine_recipe.json', engine.directory, 256*1024)
    if recipe_path.read_bytes() != canonical_bytes(expected_recipe):
        raise ValidationError('Unity engine recipe differs from the exact reviewed import bindings')
    for name in sorted(allowed):
        source = regular_file(engine.directory/name, engine.directory, 512*1024*1024)
        if _digest(source, cancel) != saved[name]:
            raise ProjectStorageError('Unity saved native payload changed before delivery')
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for name in ('request.json', 'engine_recipe.json'):
        source = regular_file(engine.directory/name, engine.directory, 256*1024)
        shutil.copy2(source, destination/name)
    if (destination/'request.json').read_bytes() != canonical_bytes(request.to_dict()):
        raise ProjectStorageError('Unity payload request differs from the reviewed sources and permissions')
    readme = (
        'Private Unity character export\n\n'
        'Open this folder in Unity 6000.4.5f1. Open Assets/UCC/Character.unity, or use Character.prefab.\n'
        'Requires Built-in Forward, Direct3D11, Linear color and Unlimited skin weights.\n'
        'Retain the saved native mesh, source_quads and runtime shader/component references.\n'
        'The derived character FBX is a prefab dependency; it is not the original Blender master.\n'
        'No animation clips, original Blender files, purchased sources or private diagnostic vectors are included.\n'
        'Runtime diagnostics cover 178 finite states and two cameras; they are not artist approval,\n'
        'general animation compatibility, player-build acceptance or permission to redistribute assets.\n'
        'Per-input permissions and NoAI/source restrictions are in request.json.\n'
        'Completion requires export_receipt.json with export_published and final_payload_verified true.\n')
    (destination/'README.txt').write_bytes(readme.encode('utf-8'))
    # Seal known producer bytes, not whatever a racing copy happens to contain.
    expected = {name:saved[name] for name in allowed}
    expected.update({'request.json':request.sha256,
        'engine_recipe.json':sha256(canonical_bytes(expected_recipe)).hexdigest(),
        'README.txt':sha256(readme.encode('utf-8')).hexdigest()})
    check_snapshot(destination, expected, cancel)
    return expected


def verify_unity_export_result(result, cancel=None) -> dict:
    """Read-only completion check used by the desktop before reporting success."""
    root = Path(result.destination)
    receipt_file = regular_file(root/RECEIPT, root, 2*1024*1024)
    if _digest(receipt_file, cancel) != result.receipt_sha256:
        raise ProjectStorageError('Unity final export receipt changed')
    receipt = read_json(receipt_file, 2*1024*1024)
    if (receipt.get('policy') != POLICY or receipt.get('schema_version') != 1
            or receipt.get('request_sha256') != result.request_sha256
            or receipt.get('master_sha256') != result.master_sha256
            or receipt.get('export_published') is not True or receipt.get('final_payload_verified') is not True
            or receipt.get('animation_clips_verified') is not False
            or receipt.get('visual_quality_approved') is not False
            or receipt.get('distribution_license_review_complete') is not False):
        raise ValidationError('Unity final receipt lacks truthful bound publication evidence')
    files = receipt.get('files')
    if (type(files) is not dict or set(files) != engine_payload() | ROOT_INPUTS
            or any(not is_sha256(value) for value in files.values())):
        raise ValidationError('Unity final receipt has an unsupported payload inventory')
    check_snapshot(root, files | {RECEIPT: result.receipt_sha256}, cancel)
    request = UnityExportRequest.from_bytes((root/'request.json').read_bytes())
    if request.sha256 != result.request_sha256 or dict(request.source_bindings)['master'] != result.master_sha256:
        raise ValidationError('Unity final permissions/source request changed')
    return receipt
