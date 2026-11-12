"""Bounded numerical motion guards, not anatomical or visual approval.

Blender bones' longitudinal axis is local Y. Swing/twist is measured in each
target's actual rest-local quaternion frame; no arbitrary source roll is inferred.
Callers supply an explicit edge reference. Enforced neutral strain and optional
posed-shape observations are distinct; neither changes actual geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import math
import struct
from typing import Sequence

Quaternion = tuple[float, float, float, float]
MAX_TWIST = 90.0
MAX_SWING = 150.0
MAX_STEP = 80.0
MAX_STRETCH = 4.0
MIN_EDGE_RATIO = .05


class MotionQualityError(RuntimeError):
    """Numerical motion is ambiguous, discontinuous, or severely deformed."""


def checked_quaternion(value: Sequence[float]) -> Quaternion:
    if len(value) != 4 or any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise MotionQualityError("Rotation requires a finite WXYZ quaternion")
    size = math.sqrt(sum(x*x for x in value))
    if abs(size - 1) > 1e-4:
        raise MotionQualityError("Rotation quaternion is not unit length")
    return tuple(float(x)/size for x in value)  # type: ignore[return-value]


def swing_twist_degrees(value: Sequence[float]) -> tuple[float, float]:
    w, _, y, _ = checked_quaternion(value)
    twist_norm = math.hypot(w, y)
    if twist_norm < 1e-8:
        raise MotionQualityError("180-degree swing has ambiguous longitudinal twist")
    swing = math.degrees(2 * math.acos(min(1., twist_norm)))
    twist = math.degrees(2 * math.atan2(abs(y), abs(w)))
    return swing, twist


@dataclass
class JointMotion:
    bone: str
    previous: Quaternion | None = None
    samples: int = 0
    maxima: dict[str, float | int] = field(default_factory=lambda: {
        "max_swing_degrees": 0., "max_swing_frame": 1,
        "max_twist_degrees": 0., "max_twist_frame": 1,
        "max_step_degrees": 0., "max_step_frame": 1,
    })

    def add(self, value: Sequence[float], frame: int) -> Quaternion:
        if type(frame) is not int or frame != self.samples + 1:
            raise MotionQualityError("Joint frames must be complete and sequential")
        q = checked_quaternion(value)
        dot = sum(a*b for a, b in zip(self.previous, q)) if self.previous is not None else q[0]
        if dot < 0:
            q = tuple(-x for x in q)
        step = (math.degrees(2 * math.acos(min(1., abs(dot))))
                if self.previous is not None else 0.)
        swing, twist = swing_twist_degrees(q)
        if swing > MAX_SWING or twist > MAX_TWIST or step > MAX_STEP:
            raise MotionQualityError(
                f"Bone {self.bone}, frame {frame}: swing={swing:.3f}, "
                f"twist={twist:.3f}, step={step:.3f} degrees exceed generic safety bounds")
        for metric, angle in (("swing", swing), ("twist", twist), ("step", step)):
            if angle > self.maxima[f"max_{metric}_degrees"]:
                self.maxima[f"max_{metric}_degrees"] = angle
                self.maxima[f"max_{metric}_frame"] = frame
        self.samples += 1
        self.previous = q
        return q

    def report(self) -> dict[str, float | int | str]:
        return {"bone": self.bone, "frames_measured": self.samples, **self.maxima}


def _points(values: Sequence[Sequence[float]]) -> None:
    if not 2 <= len(values) <= 250000 or any(
        len(p) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e6
                           for x in p) for p in values
    ):
        raise MotionQualityError("Invalid evaluated skin coordinates")


def _edges(values: Sequence[Sequence[int]], vertices: int) -> tuple[tuple[int, int], ...]:
    if not 1 <= len(values) <= 750000:
        raise MotionQualityError("Evaluated edge count is outside safe bounds")
    checked = []
    for edge in values:
        if (len(edge) != 2 or any(type(i) is not int or not 0 <= i < vertices for i in edge)
                or edge[0] == edge[1]):
            raise MotionQualityError("Invalid evaluated edge indices")
        checked.append(tuple(sorted(edge)))
    ordered = tuple(sorted(checked))
    if len(set(ordered)) != len(ordered):
        raise MotionQualityError("Duplicate evaluated edges")
    return ordered


class EdgeStrain:
    def __init__(self, points: Sequence[Sequence[float]], edges: Sequence[Sequence[int]]):
        _points(points)
        self.vertex_count = len(points)
        self.edges = _edges(edges, len(points))
        self.lengths = tuple(math.dist(points[a], points[b]) for a, b in self.edges)
        self.active = tuple(i for i, length in enumerate(self.lengths) if length > 1e-9)
        if not self.active:
            raise MotionQualityError("No non-degenerate evaluated skin edges")
        digest = sha256(struct.pack("<I", len(points)))
        for edge in self.edges:
            digest.update(struct.pack("<II", *edge))
        self.topology_sha256 = digest.hexdigest()

    def measure(self, points: Sequence[Sequence[float]], edges: Sequence[Sequence[int]],
                frame: int) -> dict[str, float]:
        return self._measure(points,edges,frame,enforce=True)

    def observe(self, points: Sequence[Sequence[float]], edges: Sequence[Sequence[int]],
                frame: int) -> dict[str,float]:
        """Compare posed shapes for information; this is not a safety verdict."""
        return self._measure(points,edges,frame,enforce=False)

    def _measure(self, points, edges, frame, *, enforce):
        _points(points)
        if len(points) != self.vertex_count or _edges(edges, len(points)) != self.edges:
            raise MotionQualityError(f"Evaluated edge topology changed on frame {frame}")
        minimum, maximum = math.inf, 0.
        for i in self.active:
            a, b = self.edges[i]
            ratio = math.dist(points[a], points[b]) / self.lengths[i]
            if enforce and (ratio < MIN_EDGE_RATIO or ratio > MAX_STRETCH):
                raise MotionQualityError(
                    f"Extreme local edge strain on frame {frame}, edge {a}-{b}: {ratio:.6f}x")
            minimum, maximum = min(minimum, ratio), max(maximum, ratio)
        return {"max_edge_stretch_ratio": maximum, "min_edge_length_ratio": minimum}

    def report(self) -> dict[str, int | str]:
        return {"evaluated_edge_count": len(self.edges), "measured_edge_count": len(self.active),
                "degenerate_baseline_edges_excluded": len(self.edges) - len(self.active),
                "evaluated_topology_sha256": self.topology_sha256}
