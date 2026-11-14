"""Actual full GLB triangles in immutable static GPU buffers; no animation data."""
from dataclasses import dataclass, replace
import math
import struct

from ucc.core.errors import ValidationError
from .glb_mesh import PreviewMesh


@dataclass(frozen=True, slots=True)
class StaticSurface:
    vertices: bytes
    indices: bytes
    triangle_count: int
    hips: tuple[tuple[float, float, float], ...]  # Shared renderer's view center.
    radius: float
    face_center: tuple[float, float, float]
    face_radius: float
    world_matrix: tuple[float, ...] = (1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
    surface_review: None = None

    def frame(self, index: int) -> tuple[bytes, bytes]:
        if type(index) is not int or index != 0:
            raise ValidationError('Static geometry has no animation frames')
        return self.vertices, self.indices

    def focused(self):
        return replace(self, hips=(self.face_center,), radius=self.face_radius)


def from_full_mesh(mesh: PreviewMesh) -> StaticSurface:
    if mesh.sample_count != mesh.source_face_count or not 1 <= mesh.source_face_count <= 100_000:
        raise ValidationError('Facial GPU preview requires a complete bounded static mesh')
    points = [(x, -z, y) for face in mesh.triangles for x, y, z in face]  # glTF Y-up -> Blender Z-up.
    if any(not math.isfinite(v) or abs(v) > 1e6 for p in points for v in p):
        raise ValidationError('Invalid static GPU coordinates')
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    center = tuple((a+b)/2 for a, b in zip(low, high))
    radius = max(.001, math.dist(low, high)/2)
    height = high[2]-low[2]
    face = [p for p in points if p[2] >= high[2]-.14*height and abs(p[0]-center[0]) <= height*.12]
    if not face or height <= 0:
        raise ValidationError('No supported upright humanoid head region in static preview')
    face_low = [min(p[i] for p in face) for i in range(3)]
    face_high = [max(p[i] for p in face) for i in range(3)]
    face_center = tuple((a+b)/2 for a, b in zip(face_low, face_high))
    vertices = b''.join(struct.pack('<3f', *p) for p in points)
    indices = struct.pack('<'+'I'*len(points), *range(len(points)))
    return StaticSurface(vertices, indices, mesh.source_face_count, (center,), radius,
                         face_center, max(.001, math.dist(face_low, face_high)*.6))
