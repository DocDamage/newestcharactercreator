"""Closed, cache-free inventory for the private animated Unity scene."""
from pathlib import Path

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.export.unity_animation_recipe import CORRECTION_INPUTS, FBX
from .export_guards import bounded_paths
from .godot_registered_runtime_files import hash_file
from .unity_export_payload import SETTINGS


_RUNTIME_ASSETS = ('AnimatedCharacter.unity', FBX, 'CharacterSkin.asset', 'RegisteredLoop.controller',
    'NeutralPreview.mat', 'RegisteredCorrection.asset', 'source_quads.json', 'UccNativeNormals.cs',
    'UccNativeMeshIdentity.cs', 'UccQuadSourceData.cs', 'UccNativeSkinWarmup.shader',
    'UccRegisteredNormalsCorrectionBinding.cs', 'UccRegisteredCorrection.cs',
    'UccRegisteredCorrection.compute', 'UccRegisteredQuadNormals.compute',
    *('CorrectionData/' + name + '.bytes' for name in CORRECTION_INPUTS))
PORTABLE_FILES = frozenset({'Assets/UCC.meta', 'Assets/UCC/CorrectionData.meta', 'Packages/manifest.json',
    *('ProjectSettings/'+name for name in SETTINGS),
    *('Assets/UCC/'+name+suffix for name in _RUNTIME_ASSETS for suffix in ('', '.meta'))})
VERIFIER_FILES = frozenset({'Assets/UCC/Editor.meta',
    *('Assets/UCC/'+name+suffix for name in ('Editor/UccRegisteredCorrectionVerify.cs',
        'UccRegisteredCorrectionObserver.cs', 'UccRegisteredAnimatorSampler.cs') for suffix in ('', '.meta'))})
_STAGING_FILES = frozenset('Assets/UCC/'+name+suffix
    for name in ('source_weights.json', 'Editor/UccRegisteredAnimationJob.cs', 'Editor/UccSourceWeights.cs',
                 'UccRegisteredAnimationObserver.cs', 'Editor/UccRegisteredCorrectionJob.cs')
    for suffix in ('', '.meta'))
PAYLOAD_DIRECTORIES = frozenset({'Assets', 'Assets/UCC', 'Assets/UCC/CorrectionData', 'Packages', 'ProjectSettings'})


def split_animated_unity_inputs(saved: object) -> tuple[dict[str, str], dict[str, str]]:
    """Return the exact scene inputs and the isolated verification additions."""
    if (type(saved) is not dict or set(saved) != PORTABLE_FILES | VERIFIER_FILES | _STAGING_FILES
            or any(not is_sha256(value) for value in saved.values())):
        raise ValidationError('Unity animated project has a missing or unlisted saved input')
    return ({name: saved[name] for name in sorted(PORTABLE_FILES)},
            {name: saved[name] for name in sorted(VERIFIER_FILES)})


def verify_unity_animation_payload(root: Path, expected: dict[str, str], budget) -> None:
    observed = {}
    for path in bounded_paths(root, budget.cancel, maximum_entries=128, allowed_directories=PAYLOAD_DIRECTORIES):
        budget.check()
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative not in expected:
                raise ProjectStorageError('Unity animated export contains an unlisted file')
            observed[relative] = hash_file(path, 512 * 1024**2, budget)[0]
    if observed != expected:
        raise ProjectStorageError('Unity private animated export payload changed or is incomplete')
