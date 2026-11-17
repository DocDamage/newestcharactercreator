"""Private source-bone segment cache; no skin, target mapping or quality approval."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import struct
from typing import Callable

from ucc.animations.fbx_snapshot import MAX_SNAPSHOT_BYTES, validate_snapshot
from ucc.animations.native_math import inverse, point, product, rows
from ucc.animations.source_clip_clock import SourceClipClock
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError


@dataclass(frozen=True, slots=True)
class SourceSkeletonCache:
    clock: SourceClipClock
    bone_names: tuple[str, ...] = field(repr=False)
    parent_indices: tuple[int | None, ...] = field(repr=False)
    frames: tuple[bytes, ...] = field(repr=False)
    source_sha256: str
    snapshot_sha256: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    radius: float
    coordinate_space: str = 'BLENDER_WORLD_Z_UP'

    @property
    def frame_count(self) -> int:
        return self.clock.frame_count

    @property
    def fps(self) -> float:
        return self.clock.fps

    @property
    def source_first_frame(self) -> int:
        return self.clock.source_first_frame

    @property
    def bone_count(self) -> int:
        return len(self.bone_names)

    def frame(self, index: int) -> bytes:
        """Little-endian float32 XYZ head, XYZ tail for every ordered bone."""
        if type(index) is not int or not 0 <= index < self.frame_count:
            raise ValidationError('Source skeleton frame is outside the complete clip')
        return self.frames[index]


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValidationError('Duplicate source skeleton snapshot field')
        value[key] = item
    return value


def _nonfinite(_):
    raise ValidationError('Nonfinite source skeleton snapshot number')


def build_source_skeleton_cache(snapshot_bytes: bytes, *, source_sha256: str,
        snapshot_sha256: str, cancel_check: Callable[[], None] = lambda: None
        ) -> SourceSkeletonCache:
    """Validate one captured buffer, then derive all measured bone endpoints.

    Endpoint transform is armature_world @ pose @ inverse(rest) @ rest_endpoint.
    No source file, catalog, executable, image or target character is opened.
    Caller cancellation exceptions propagate unchanged. Float32 segments are
    rendering data; source matrices stay unmodified and are not retained here.
    """
    cancel_check()
    if (type(snapshot_bytes) is not bytes or not 0 < len(snapshot_bytes) <= MAX_SNAPSHOT_BYTES
            or not is_sha256(source_sha256) or not is_sha256(snapshot_sha256)):
        raise ValidationError('Source skeleton requires bounded captured bytes and exact SHA256 identities')
    checksum = sha256()
    for offset in range(0, len(snapshot_bytes), 1024*1024):
        cancel_check()
        checksum.update(snapshot_bytes[offset:offset+1024*1024])
    if checksum.hexdigest() != snapshot_sha256:
        raise ValidationError('Source skeleton captured snapshot SHA256 differs')
    try:
        data = json.loads(snapshot_bytes, object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Invalid captured source skeleton JSON') from error
    cancel_check()
    try:
        observed = validate_snapshot(data, source_sha256, cancel_check=cancel_check)
    except (OverflowError, ZeroDivisionError) as error:
        raise ValidationError('Source skeleton snapshot numeric range is invalid') from error
    clock = SourceClipClock(observed['first_frame'], observed['last_frame'],
                            observed['frame_count'], observed['fps'])
    names = tuple(bone['name'] for bone in data['bones'])
    indices = {name: i for i, name in enumerate(names)}
    parents = tuple(None if bone['parent'] is None else indices[bone['parent']]
                    for bone in data['bones'])
    local_endpoints = []
    for bone in data['bones']:
        cancel_check()
        rest = rows(bone['matrix'])
        # Normalize each validated nonzero axis before inversion. This preserves
        # exact affine inversion while avoiding a determinant cutoff on tiny scale.
        lengths = [math.sqrt(sum(rest[r][c]**2 for r in range(3))) for c in range(3)]
        normalized = [row[:] for row in rest]
        for r in range(3):
            for c in range(3):normalized[r][c] /= lengths[c]
        rest_inverse = inverse(normalized)
        for r in range(3):
            for c in range(4):rest_inverse[r][c] /= lengths[r]
        local_endpoints.append((point(rest_inverse, bone['head']),
                                point(rest_inverse, bone['tail'])))
    minimum = [math.inf]*3
    maximum = [-math.inf]*3
    frames = []
    for sample in data['frames']:
        cancel_check()
        world = rows(sample['armature_world'])
        packed = bytearray()
        for pose, endpoints in zip(sample['poses'], local_endpoints):
            cancel_check()
            transform = product(world, rows(pose))
            values = tuple(component for endpoint in endpoints for component in point(transform, endpoint))
            try:
                encoded = struct.pack('<6f', *values)
            except (OverflowError, struct.error) as error:
                raise ValidationError('Source skeleton endpoint exceeds float32 bounds') from error
            displayed = struct.unpack('<6f', encoded)
            if not all(math.isfinite(v) for v in displayed):
                raise ValidationError('Nonfinite source skeleton endpoint')
            for offset in (0, 3):
                for axis in range(3):
                    minimum[axis] = min(minimum[axis], displayed[offset+axis])
                    maximum[axis] = max(maximum[axis], displayed[offset+axis])
            packed.extend(encoded)
        frames.append(bytes(packed))
    cancel_check()
    radius = math.sqrt(sum((high-low)**2 for low, high in zip(minimum, maximum)))/2
    if not math.isfinite(radius) or radius <= 0:
        raise ValidationError('Degenerate source skeleton world bounds')
    return SourceSkeletonCache(clock, names, parents, tuple(frames), source_sha256,
                               snapshot_sha256, tuple(minimum), tuple(maximum), radius)
