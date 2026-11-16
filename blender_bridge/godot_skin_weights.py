"""Explicit glTF linear-skin conversion; never prune source influences."""
import math
import struct

MAX_INFLUENCES = 8
POLICY = 'NORMALIZE_ALL_ORIGINAL_POSITIVE_INFLUENCES_V1'
SERIALIZATION_POLICY = 'UNIFORM_MAX_ONE_STAGING_BEFORE_GLTF_NORMALIZATION_V1'


def normalize_weights(rows: tuple[tuple[str, float], ...]) -> tuple[tuple[tuple[str, float], ...], float]:
    """Preserve all positive relative contributions, as Blender's LBS does.

    This is a representation conversion, not source-weight repair. Admission
    still has to bind the exact source, and actual posed output must agree.
    """
    if type(rows) is not tuple or not rows or len(rows) > 512:
        raise ValueError('A skin vertex requires a bounded original influence list')
    seen = set(); positive = []
    for row in rows:
        if type(row) is not tuple or len(row) != 2:
            raise ValueError('Skin influences require original bone/weight pairs')
        name, weight = row
        if type(name) is not str or not name or len(name) > 128 or name in seen:
            raise ValueError('Skin influences require distinct original bone identities')
        seen.add(name)
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0 <= weight <= 1.00001:
            raise ValueError('Invalid original skin influence')
        if weight > 0:
            positive.append((name, float(weight)))
    if not 1 <= len(positive) <= MAX_INFLUENCES:
        raise ValueError('Unsupported skin influence count; truncation is forbidden')
    total = math.fsum(weight for _, weight in positive)
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Skin influence total must be finite and positive')
    return tuple((name, weight/total) for name, weight in positive), total


def serialization_weights(rows: tuple[tuple[str, float], ...]) -> tuple[tuple[str, float], ...]:
    """Keep ratios while avoiding the installed exporter's 0.0001 cutoff.

    Blender's armature and glTF exporter both normalize the whole row. Scaling
    every contribution equally is equivalent; changing or dropping one is not.
    Extremely small ratios remain unsupported and fail before serialization.
    """
    normalized, _ = normalize_weights(rows)
    largest = max(weight for _, weight in normalized)
    result = tuple((name, struct.unpack('<f', struct.pack('<f', weight/largest))[0])
                   for name, weight in normalized)
    if any(weight <= .0001 for _, weight in result):
        raise ValueError('Source influence ratio is below the installed exporter floor; no pruning allowed')
    return result
