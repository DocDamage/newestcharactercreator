"""Bounded, offline GLB 2.0 vertex/triangle reader for a static geometry preview.

Does not execute embedded content, resolve URIs, import materials, skin, run
animations, modify sources or claim compatibility with any game engine.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import struct
from typing import Any

from ucc.export.inspect_glb import GLBInspectionError, _parse_glb, inspect_glb

Vec3 = tuple[float, float, float]
Face = tuple[Vec3, Vec3, Vec3]
IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.)
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_VERTICES = 250_000
MAX_INDICES = 1_500_000
MAX_FACES_DRAWN = 2_000
MAX_MESH_INSTANCES = 256


class PreviewError(ValueError):
    """Selected GLB cannot be safely displayed by the limited static previewer."""


@dataclass(frozen=True, slots=True)
class PreviewMesh:
    triangles: tuple[Face, ...]
    bounds: tuple[Vec3, Vec3]
    source_face_count: int
    skin_count: int
    animation_count: int
    warnings: tuple[str, ...]

    @property
    def sample_count(self) -> int:
        return len(self.triangles)


def _number(value: Any, label: str, *, integral: bool = False) -> float | int:
    if integral:
        if type(value) is not int or value < 0:
            raise PreviewError(f"Invalid {label}: expected nonnegative integer")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e7:
        raise PreviewError(f"Invalid {label}: finite coordinate required")
    return float(value)


def _index(value: Any, size: int, label: str) -> int:
    if type(value) is not int or not (0 <= value < size):
        raise PreviewError(f"Invalid {label} index")
    return value


def _array(doc: dict[str, Any], key: str, limit: int = 10_000) -> list:
    value = doc.get(key, [])
    if not isinstance(value, list) or len(value) > limit:
        raise PreviewError(f"glTF {key} must be a bounded array")
    return value


def _read_binary(path: Path) -> bytes:
    with path.open("rb") as stream:
        stream.seek(12)
        length, kind = struct.unpack("<I4s", stream.read(8))
        if kind != b"JSON" or length > 16 * 1024 * 1024:
            raise PreviewError("Invalid glTF JSON chunk")
        stream.seek(length, 1)
        header = stream.read(8)
        if len(header) != 8:
            raise PreviewError("GLB has no embedded BIN chunk")
        count, kind = struct.unpack("<I4s", header)
        if kind != b"BIN\0" or count > MAX_SOURCE_BYTES:
            raise PreviewError("GLB must use one bounded embedded BIN chunk")
        data = stream.read(count)
        if len(data) != count or stream.read(1):
            raise PreviewError("Missing, truncated or additional GLB binary chunks")
        return data


def _accessor_values(doc: dict[str, Any], binary: bytes, index: int, *, position: bool) -> list:
    accessors = _array(doc, "accessors")
    views = _array(doc, "bufferViews")
    acc = accessors[_index(index, len(accessors), "accessor")]
    if not isinstance(acc, dict) or "sparse" in acc or "bufferView" not in acc:
        raise PreviewError("Sparse or missing-buffer accessors are not supported by static preview")
    view = views[_index(acc["bufferView"], len(views), "bufferView")]
    if not isinstance(view, dict) or view.get("buffer") != 0:
        raise PreviewError("Only embedded GLB buffer 0 is supported")
    component = acc.get("componentType")
    if position:
        if component != 5126 or acc.get("type") != "VEC3":
            raise PreviewError("POSITION must be float32 VEC3")
        fmt, component_bytes, element_size = "<fff", 4, 12
    else:
        if acc.get("type") != "SCALAR" or component not in (5121, 5123, 5125):
            raise PreviewError("Triangle indices must be unsigned integer SCALAR")
        fmt, component_bytes, element_size = {5121: ("<B", 1, 1), 5123: ("<H", 2, 2), 5125: ("<I", 4, 4)}[component]
    count = _number(acc.get("count"), "accessor count", integral=True)
    limit = MAX_VERTICES if position else MAX_INDICES
    if not 1 <= count <= limit:
        raise PreviewError("Accessor has invalid or excessive element count")
    start = _number(view.get("byteOffset", 0), "bufferView offset", integral=True)
    view_size = _number(view.get("byteLength"), "bufferView size", integral=True)
    local = _number(acc.get("byteOffset", 0), "accessor offset", integral=True)
    stride = _number(view.get("byteStride", element_size), "bufferView stride", integral=True)
    if stride < element_size or stride > 252 or stride % component_bytes != 0:
        raise PreviewError("Unsupported or misaligned accessor stride")
    if start + view_size > len(binary) or local + (count - 1) * stride + element_size > view_size:
        raise PreviewError("Accessor reads past its embedded buffer view")
    base = start + local
    result = []
    for i in range(count):
        values = struct.unpack_from(fmt, binary, base + i * stride)
        if position:
            if any(not math.isfinite(x) or abs(x) > 1e6 for x in values):
                raise PreviewError("GLB POSITION contains nonfinite or extreme coordinates")
            result.append((values[0], values[1], values[2]))
        else:
            result.append(values[0])
    return result


def _multiply(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(sum(a[k * 4 + row] * b[col * 4 + k] for k in range(4))
                 for col in range(4) for row in range(4))


def _node_transform(node: dict[str, Any]) -> tuple[float, ...]:
    if "matrix" in node:
        if any(k in node for k in ("translation", "rotation", "scale")):
            raise PreviewError("glTF node cannot mix matrix and TRS transforms")
        arr = node["matrix"]
        if not isinstance(arr, list) or len(arr) != 16:
            raise PreviewError("Invalid 4x4 node transform")
        return tuple(_number(x, "matrix element") for x in arr)
    def values(key: str, default: list[float]) -> list[float]:
        raw = node.get(key, default)
        if not isinstance(raw, list) or len(raw) != len(default):
            raise PreviewError(f"Invalid glTF {key} transform")
        return [float(_number(x, key)) for x in raw]
    tx, ty, tz = values("translation", [0., 0., 0.])
    sx, sy, sz = values("scale", [1., 1., 1.])
    x, y, z, w = values("rotation", [0., 0., 0., 1.])
    norm = math.sqrt(x*x + y*y + z*z + w*w)
    if norm < 1e-9:
        raise PreviewError("Zero-length node rotation quaternion")
    x, y, z, w = (v / norm for v in (x, y, z, w))
    return (
        (1-2*(y*y+z*z))*sx, (2*(x*y+z*w))*sx, (2*(x*z-y*w))*sx, 0.,
        (2*(x*y-z*w))*sy, (1-2*(x*x+z*z))*sy, (2*(y*z+x*w))*sy, 0.,
        (2*(x*z+y*w))*sz, (2*(y*z-x*w))*sz, (1-2*(x*x+y*y))*sz, 0.,
        tx, ty, tz, 1.,
    )


def _transform(matrix: tuple[float, ...], point: Vec3) -> Vec3:
    x, y, z = point
    w = matrix[3]*x + matrix[7]*y + matrix[11]*z + matrix[15]
    if abs(w) < 1e-9:
        raise PreviewError("Mesh transform produces invalid homogeneous coordinate")
    out = tuple((matrix[row]*x + matrix[4+row]*y + matrix[8+row]*z + matrix[12+row]) / w
                for row in range(3))
    if any(not math.isfinite(v) or abs(v) > 1e7 for v in out):
        raise PreviewError("Mesh transform produces nonfinite or extreme coordinates")
    return out  # type: ignore[return-value]


def _instances(doc: dict[str, Any], meshes: list) -> list[tuple[int, tuple[float, ...]]]:
    nodes = _array(doc, "nodes", 20_000)
    if not nodes:
        return [(i, IDENTITY) for i in range(len(meshes))]
    parents = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise PreviewError("Malformed scene node")
        parents.update(node.get("children", []))
    scenes = _array(doc, "scenes")
    if scenes:
        scene = scenes[_index(doc.get("scene", 0), len(scenes), "scene")]
        if not isinstance(scene, dict) or not isinstance(scene.get("nodes", []), list):
            raise PreviewError("Invalid active glTF scene")
        roots = scene.get("nodes", [])
    else:
        roots = [i for i in range(len(nodes)) if i not in parents]
    out: list[tuple[int, tuple[float, ...]]] = []
    queue = [(root, IDENTITY) for root in roots]
    visited = 0
    while queue:
        idx, parent = queue.pop()
        node = nodes[_index(idx, len(nodes), "scene node")]
        transform = _multiply(parent, _node_transform(node))
        if "mesh" in node:
            out.append((_index(node["mesh"], len(meshes), "mesh"), transform))
            if len(out) > MAX_MESH_INSTANCES:
                raise PreviewError("Too many mesh instances for the software preview")
        for child in node.get("children", []):
            queue.append((child, transform))
        visited += 1
        if visited > 20_000:
            raise PreviewError("Scene graph too large for preview")
    return out


def load_glb_preview(path: Path | str) -> PreviewMesh:
    """Read-only sampled flat triangle geometry; never verify animation or rigging."""
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".glb":
        raise PreviewError("Select an existing regular .glb file")
    if not 20 < source.stat().st_size <= MAX_SOURCE_BYTES:
        raise PreviewError("GLB is too small or too large for bounded preview")
    try:
        report = inspect_glb(source)
        doc, _ = _parse_glb(source)
    except GLBInspectionError as exc:
        raise PreviewError(str(exc)) from exc
    buffers = _array(doc, "buffers", 8)
    if not buffers or not isinstance(buffers[0], dict) or "uri" in buffers[0]:
        raise PreviewError("GLB static preview requires an embedded binary buffer")
    bin_data = _read_binary(source)
    meshes = _array(doc, "meshes")
    instances = _instances(doc, meshes)
    cache: dict[tuple[int, int], tuple[list[Vec3], list[int]]] = {}
    total = 0
    warnings: list[str] = []
    for mesh_id, _ in instances:
        mesh = meshes[mesh_id]
        if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives"), list):
            raise PreviewError("Malformed mesh primitives")
        for primitive_id, primitive in enumerate(mesh["primitives"]):
            if not isinstance(primitive, dict):
                raise PreviewError("Malformed primitive")
            if primitive.get("mode", 4) != 4:
                warnings.append("Skipped non-TRIANGLES primitive")
                continue
            key = (mesh_id, primitive_id)
            if key not in cache:
                attrs = primitive.get("attributes", {})
                if not isinstance(attrs, dict) or "POSITION" not in attrs:
                    raise PreviewError("Mesh primitive lacks POSITION data")
                positions = _accessor_values(doc, bin_data, attrs["POSITION"], position=True)
                indices = (_accessor_values(doc, bin_data, primitive["indices"], position=False)
                           if "indices" in primitive else list(range(len(positions))))
                if len(indices) % 3:
                    raise PreviewError("Triangles require a multiple of three vertex indices")
                if any(i >= len(positions) for i in indices):
                    raise PreviewError("Triangle index references an absent vertex")
                cache[key] = (positions, indices)
            total += len(cache[key][1]) // 3
    if not total:
        raise PreviewError("No displayable triangular geometry found")
    skip = max(1, math.ceil(total / MAX_FACES_DRAWN))
    faces: list[Face] = []
    k = 0
    for mesh_id, transform in instances:
        for primitive_id, primitive in enumerate(meshes[mesh_id]["primitives"]):
            key = (mesh_id, primitive_id)
            if key not in cache:
                continue
            positions, indices = cache[key]
            for at in range(0, len(indices), 3):
                if k % skip == 0:
                    tri = tuple(_transform(transform, positions[indices[at+j]]) for j in range(3))
                    faces.append(tri)  # type: ignore[arg-type]
                k += 1
    vertices = [vertex for face in faces for vertex in face]
    lower = tuple(min(p[d] for p in vertices) for d in range(3))
    upper = tuple(max(p[d] for p in vertices) for d in range(3))
    if total > MAX_FACES_DRAWN:
        warnings.append(f"Sampled {len(faces)} of {total} triangles for responsiveness")
    if report.skin_count or report.animation_count or report.morph_target_count:
        warnings.append("Skinning, animations and morphs are NOT evaluated; bind/static geometry only")
    if not doc.get("nodes"):
        warnings.append("Model has no scene nodes; showing raw mesh primitives")
    return PreviewMesh(tuple(faces), (lower, upper), total, report.skin_count,
                       report.animation_count, tuple(warnings))
