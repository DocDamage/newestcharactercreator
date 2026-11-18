"""Build the live correction operands from the independently admitted native mesh."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from struct import Struct

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import checked_sha
from ucc.export import unreal_animation_recipe as recipe
from ucc.export.unreal_bind_math import expected_position_cm, unique_correspondence
from .godot_registered_runtime_files import read_bytes, read_metadata
from .target_action_context import Budget, protected
from .unreal_animation_engine import VerifiedUnrealNativeAnimation
from .unreal_animation_source import PreparedUnrealAnimationSource


CORRECTION_PACKET = 'ucc-registered-correction.bin'
OPERANDS = ('neighbor_ranges.u32', 'neighbors.u32', 'corners.u32',
            'offsets_vec4.f32', 'corner_ranges.u32', 'corner_indices.u32')
_HEADER = Struct('<8s6I')
_INDEX = Struct('<I')
_MAX_NATIVE = 100000
_CORNERS = recipe.CORRECTION_INPUTS['corner_indices.u32']//4
_FACES = _CORNERS//4
PACKET_LIMIT = _HEADER.size + _INDEX.size*_MAX_NATIVE + sum(recipe.CORRECTION_INPUTS.values())


@dataclass(frozen=True, slots=True)
class UnrealCorrectionInputs:
    sha256: str
    native_to_source: tuple[int, ...]


def build_unreal_correction_packet(source: PreparedUnrealAnimationSource, native: VerifiedUnrealNativeAnimation,
                                   target: Path, budget: Budget) -> UnrealCorrectionInputs:
    """Supply original topology and indexing, without any expected playback frames."""
    if type(source) is not PreparedUnrealAnimationSource or type(native) is not VerifiedUnrealNativeAnimation:
        raise ValidationError('Unreal correction requires independently verified Blender and native input receipts')
    source_report = read_metadata(source.directory/recipe.VERIFY_REPORT, 256 * 1024, budget,
                                  expected_sha256=source.verification_sha256)[0]
    native_report = read_metadata(native.directory.parent/'unreal-animation-native-receipt.json', 512 * 1024, budget,
                                  expected_sha256=native.receipt_sha256)[0]
    if (source_report.get('policy') != recipe.POLICY
            or source_report.get('target_binding_sha256') != source.binding_sha256
            or source_report.get('recomputed_source_references') is not True
            or native_report.get('policy') != 'UCC_UNREAL_NATIVE_ANIMATION_ADMISSION_V1'
            or native_report.get('blender_verification_sha256') != source.verification_sha256
            or native_report.get('native_import_verified') is not True
            or native_report.get('native_preview_loop_verified') is not True):
        raise ValidationError('Unreal corrective operands require the same registered Blender and native lineage')
    files = source_report.get('files')
    if type(files) is not dict or set(files) != set(recipe.OUTPUT_LIMITS):
        raise ValidationError('Unreal Blender source report has an incomplete output inventory')
    original = read_metadata(source.directory/recipe.BIND, recipe.OUTPUT_LIMITS[recipe.BIND], budget,
                             expected_sha256=checked_sha(files[recipe.BIND]))[0]
    observed = read_metadata(native.directory.parent/'Verify-output/bind.json', 32 * 1024**2, budget,
                             expected_sha256=checked_sha(native_report.get('bind_sha256')))[0]
    positions, native_positions = original.get('vertices'), observed.get('positions_cm')
    if (type(positions) is not list or len(positions) != recipe.VERTICES
            or type(native_positions) is not list or not recipe.VERTICES <= len(native_positions) <= _MAX_NATIVE):
        raise ValidationError('Unreal corrective source and native render vertex domains differ')
    mapping, _ = unique_correspondence([expected_position_cm(point) for point in positions], native_positions,
                                       check=budget.check)
    return _write_packet(target, mapping, source.directory, files, budget)


def _write_packet(target: Path, mapping: list[int], source_directory: Path, files: dict,
                  budget: Budget) -> UnrealCorrectionInputs:
    if (not recipe.VERTICES <= len(mapping) <= _MAX_NATIVE
            or any(type(index) is not int or not 0 <= index < recipe.VERTICES for index in mapping)
            or len(set(mapping)) != recipe.VERTICES):
        raise ValidationError('Unreal corrective correspondence needs every original vertex')
    payload = bytearray(_HEADER.pack(b'UCCRCOR1', recipe.VERTICES, len(mapping),
        recipe.CORRECTION_INPUTS['neighbors.u32']//4, _CORNERS, _FACES, 0))
    for index in mapping:
        payload.extend(_INDEX.pack(index))
    for name in OPERANDS:
        maximum = recipe.CORRECTION_INPUTS[name]
        values, _ = read_bytes(source_directory/name, maximum, budget, expected_sha256=checked_sha(files[name]))
        if len(values) != maximum:
            raise ProjectStorageError('Unreal corrective source operand has an invalid exact length')
        payload.extend(values)
    budget.check()
    target = Path(target)
    protected(target.parent)
    with target.open('xb') as stream:
        stream.write(payload)
    return UnrealCorrectionInputs(sha256(payload).hexdigest(), tuple(mapping))
