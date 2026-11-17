"""Bounded position-only measurements of already admitted captured clip inputs.

This module does no filesystem IO, source admission, engine invocation, angle
analysis or gait classification. Root-head and source-hip motion stay distinct.
"""
import math
import struct
from hashlib import sha256
from typing import Callable

from ucc.core.errors import ValidationError
from .target_action_diagnostic_contract import (
    APPROVAL_FLAGS, PROFILE, DiagnosticClock, DiagnosticSamples, EndpointMeshGap,
    JointPositionEndpoints, JointPositionGap, TargetActionDiagnostics,
    TargetActionDiagnosticSelection, TrajectoryMetrics,
)

MAX_VERTICES = 100_000
FRAME_COUNT = 300
MAX_COORDINATE = 10_000


def _number(value) -> bool:
    return type(value) in (int, float) and abs(value) <= MAX_COORDINATE and math.isfinite(value)


def _vector(value):
    if type(value) is not tuple or len(value) != 3 or not all(_number(x) for x in value):
        raise ValidationError('Diagnostic positions must be bounded finite immutable XYZ triples')
    return value


def _delta(last, first):
    return tuple(a-b for a, b in zip(last, first))


def _length(vector):
    return math.sqrt(sum(x*x for x in vector))


def _trajectory(points, fps, cancel_check):
    if type(points) is not tuple or len(points) != FRAME_COUNT:
        raise ValidationError('Diagnostic trajectory must cover all 300 measured frames')
    previous = None
    distances = []
    for point in points:
        cancel_check()
        _vector(point)
        if previous is not None:
            distances.append(_length(_delta(point, previous)))
        previous = point
    net = _delta(points[-1], points[0])
    path = math.fsum(distances)
    step = max(distances)
    return TrajectoryMetrics(net, _length(net), path, step,
        step*fps, path/((FRAME_COUNT-1)/fps))


def _world_matrix(matrix):
    if (type(matrix) is not tuple or len(matrix) != 16
            or not all(_number(x) for x in matrix) or matrix[12:] != (0, 0, 0, 1)):
        raise ValidationError('Diagnostic cache requires its bounded affine world matrix')
    columns = [matrix[i:12:4] for i in range(3)]
    lengths = [_length(c) for c in columns]
    determinant = (matrix[0]*(matrix[5]*matrix[10]-matrix[6]*matrix[9])
        - matrix[1]*(matrix[4]*matrix[10]-matrix[6]*matrix[8])
        + matrix[2]*(matrix[4]*matrix[9]-matrix[5]*matrix[8]))
    if (min(lengths) < 1e-5 or determinant <= 0
            or any(abs(sum(a*b for a, b in zip(columns[i], columns[j])))
                > 1e-5*lengths[i]*lengths[j] for i in range(3) for j in range(i))):
        raise ValidationError('Diagnostic cache world matrix has unsupported scale, shear or reflection')
    return matrix


def _world(matrix, xyz):
    if not all(_number(x) for x in xyz):
        raise ValidationError('Diagnostic vertex contains nonfinite or oversized coordinates')
    value = tuple(sum(matrix[4*i+j]*xyz[j] for j in range(3))+matrix[4*i+3]
        for i in range(3))
    _vector(value)
    return value


def _mesh(samples, hip_delta, cancel_check):
    first, last = samples.first_vertices, samples.last_vertices
    if (type(first) is not bytes or type(last) is not bytes or len(first) != len(last)
            or not 12 <= len(first) <= MAX_VERTICES*12 or len(first) % 12):
        raise ValidationError('Diagnostic endpoint buffers must contain matching bounded float32 XYZ vertices')
    matrix = _world_matrix(samples.world_matrix)
    count = len(first)//12
    raw_sum = compensated_sum = raw_max = compensated_max = 0.0
    for index, (a, b) in enumerate(zip(struct.iter_unpack('<fff', first), struct.iter_unpack('<fff', last))):
        if index % 128 == 0:
            cancel_check()
        delta = _delta(_world(matrix, b), _world(matrix, a))
        compensated = _delta(delta, hip_delta)
        raw_squared = sum(x*x for x in delta)
        compensated_squared = sum(x*x for x in compensated)
        raw_sum += raw_squared
        compensated_sum += compensated_squared
        raw_max = max(raw_max, raw_squared)
        compensated_max = max(compensated_max, compensated_squared)
    cancel_check()
    return EndpointMeshGap(count, math.sqrt(raw_sum/count), math.sqrt(raw_max),
        math.sqrt(compensated_sum/count), math.sqrt(compensated_max))


def _joints(rows, hip_delta, cancel_check):
    if type(rows) is not tuple or len(rows) > 64:
        raise ValidationError('Diagnostic mapped position endpoints exceed the explicit mapping bound')
    result, names = [], set()
    for row in rows:
        cancel_check()
        if (type(row) is not JointPositionEndpoints or type(row.name) is not str
                or not 0 < len(row.name) <= 128 or not row.name.isprintable()
                or row.name.casefold() in names):
            raise ValidationError('Diagnostic joint endpoint name is missing, duplicated or invalid')
        names.add(row.name.casefold())
        delta = _delta(_vector(row.last_world), _vector(row.first_world))
        result.append(JointPositionGap(row.name, _length(delta), _length(_delta(delta, hip_delta))))
    return tuple(result)


def measure_target_action_diagnostic(selection: TargetActionDiagnosticSelection,
        samples: DiagnosticSamples, *, cancel_check: Callable[[], None] = lambda: None
        ) -> TargetActionDiagnostics:
    """Measure admitted captured data without judging loop, gait or animation quality.

    Endpoint RMS is sqrt(mean(per-vertex Euclidean distance squared)) in world
    metres. Compensation subtracts only last-minus-first SOURCE_HIP_MIDPOINT_V1
    translation; it does not remove rotations, align bodies or certify a loop.
    """
    cancel_check()
    if type(selection) is not TargetActionDiagnosticSelection or type(samples) is not DiagnosticSamples:
        raise ValidationError('Typed current selection and immutable diagnostic samples required')
    if (type(samples.fps) not in (int, float) or samples.fps != 30 or not math.isfinite(samples.fps)
            or type(samples.source_first_frame) is not int or samples.source_first_frame != 2
            or type(samples.target_first_frame) is not int or samples.target_first_frame != 1
            or samples.root_motion_policy != 'SOURCE_HIP_MIDPOINT_V1'):
        raise ValidationError('Diagnostic requires source2-301/target1-300 at30fps and the explicit source-hip policy')
    root = _trajectory(samples.root_world_heads, 30.0, cancel_check)
    hip = _trajectory(samples.hip_midpoints_world, 30.0, cancel_check)
    mesh = _mesh(samples, hip.net_displacement_m, cancel_check)
    joints = _joints(samples.mapped_joint_endpoints, hip.net_displacement_m, cancel_check)
    cancel_check()
    return TargetActionDiagnostics(selection,
        DiagnosticClock(2, 301, 1, 300, FRAME_COUNT, 30.0, 299/30, 10.0),
        root, hip, mesh,
        (('cache_sha256', samples.cache_sha256), ('timeline_sha256', samples.timeline_sha256),
         ('first_endpoint_vertices_sha256', sha256(samples.first_vertices).hexdigest()),
         ('last_endpoint_vertices_sha256', sha256(samples.last_vertices).hexdigest())), joints)
