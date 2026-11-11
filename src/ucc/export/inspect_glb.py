"""Safe, bounded offline glTF/GLB 2.0 structure inspection.

Checks container headers and JSON relationships, not vertex deformation,
visual quality or whether Godot/Unity/Unreal can import an asset correctly.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

from ucc.core.errors import UCCError

MAX_GLB_BYTES = 512 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
GLB_MAGIC = b"glTF"
JSON_CHUNK = b"JSON"
BIN_CHUNK = b"BIN\0"


class GLBInspectionError(UCCError):
    pass


@dataclass(frozen=True, slots=True)
class GLBReport:
    file_name: str
    sha256: str
    vertex_accessor_count: int
    mesh_count: int
    mesh_primitive_count: int
    skin_count: int
    joint_count: int
    skinned_mesh_nodes: int
    morph_target_count: int
    animation_count: int
    material_count: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"status": "OFFLINE_STRUCTURE_CHECKED", "engine_validated": False,
                **{k: (list(v) if k == "warnings" else v)
                   for k, v in ((field, getattr(self, field)) for field in self.__dataclass_fields__)}}


def _array(doc: dict[str, Any], key: str) -> list:
    result = doc.get(key, [])
    if not isinstance(result, list):
        raise GLBInspectionError(f"glTF.{key} must be an array")
    return result


def _index(value: Any, size: int, label: str) -> int:
    if type(value) is not int or value < 0 or value >= size:
        raise GLBInspectionError(f"Invalid {label} index: {value!r}")
    return value


def _parse_glb(path: Path) -> tuple[dict[str, Any], int]:
    if not path.is_file() or path.is_symlink():
        raise GLBInspectionError("GLB source must be an existing regular file")
    size = path.stat().st_size
    if size < 20 or size > MAX_GLB_BYTES:
        raise GLBInspectionError("GLB file size is outside safe container limits")
    with path.open("rb") as stream:
        raw = stream.read(12)
        magic, version, declared = struct.unpack("<4sII", raw)
        if magic != GLB_MAGIC or version != 2 or declared != size:
            raise GLBInspectionError("Not a complete glTF 2.0 GLB container")
        json_doc = None
        bin_bytes = 0
        seen_bin = False
        chunk_index = 0
        while stream.tell() < size:
            remaining = size - stream.tell()
            if remaining < 8:
                raise GLBInspectionError("Incomplete GLB chunk header")
            count, kind = struct.unpack("<I4s", stream.read(8))
            if count % 4 or count > size - stream.tell():
                raise GLBInspectionError("Invalid GLB chunk alignment/size")
            if chunk_index == 0:
                if kind != JSON_CHUNK or count > MAX_JSON_BYTES:
                    raise GLBInspectionError("GLB requires a bounded first JSON chunk")
                raw_json = stream.read(count).rstrip(b" \t\n\r\0")
                try:
                    json_doc = json.loads(raw_json.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise GLBInspectionError("Malformed glTF JSON chunk") from exc
            else:
                if kind == JSON_CHUNK:
                    raise GLBInspectionError("Unexpected second JSON chunk")
                if kind == BIN_CHUNK:
                    if seen_bin:
                        raise GLBInspectionError("Duplicate BIN chunk")
                    seen_bin = True
                    bin_bytes = count
                stream.seek(count, 1)
            chunk_index += 1
        if not isinstance(json_doc, dict):
            raise GLBInspectionError("GLB JSON root must be an object")
        return json_doc, bin_bytes


def inspect_glb(path: str | Path) -> GLBReport:
    source = Path(path)
    doc, bin_bytes = _parse_glb(source)
    asset = doc.get("asset", {})
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise GLBInspectionError("GLB JSON must declare glTF asset version 2.x")
    nodes = _array(doc, "nodes")
    meshes = _array(doc, "meshes")
    skins = _array(doc, "skins")
    animations = _array(doc, "animations")
    accessors = _array(doc, "accessors")
    images = _array(doc, "images")
    buffers = _array(doc, "buffers")
    materials = _array(doc, "materials")
    warnings: list[str] = []
    if len(buffers) > 1:
        warnings.append("GLB references multiple buffers; check external resources")
    if buffers:
        first = buffers[0]
        if not isinstance(first, dict) or type(first.get("byteLength")) is not int:
            raise GLBInspectionError("Buffer 0 has invalid byteLength")
        if "uri" not in first and first["byteLength"] > bin_bytes:
            raise GLBInspectionError("Embedded binary buffer is too small")
        if "uri" in first:
            warnings.append("Buffer 0 references an external URI")
    if any(isinstance(image, dict) and "uri" in image for image in images):
        warnings.append("Some textures reference external images")
    joint_count = 0
    for i, skin in enumerate(skins):
        if not isinstance(skin, dict) or not isinstance(skin.get("joints"), list) or not skin["joints"]:
            raise GLBInspectionError(f"Skin {i} missing joints")
        for joint in skin["joints"]:
            _index(joint, len(nodes), f"skin {i} joint")
        if "inverseBindMatrices" in skin:
            _index(skin["inverseBindMatrices"], len(accessors), "inverse bind accessor")
        joint_count += len(skin["joints"])
    primitive_count = 0
    morphs = 0
    skin_attribute_meshes: set[int] = set()
    for mesh_id, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise GLBInspectionError("Mesh entry must be object")
        primitives = mesh.get("primitives")
        if not isinstance(primitives, list) or not primitives:
            raise GLBInspectionError(f"Mesh {mesh_id} missing primitives")
        for primitive in primitives:
            if not isinstance(primitive, dict) or not isinstance(primitive.get("attributes"), dict):
                raise GLBInspectionError("Primitive attributes missing")
            attrs = primitive["attributes"]
            if "POSITION" not in attrs:
                raise GLBInspectionError("Primitive missing POSITION accessor")
            for semantic, index in attrs.items():
                _index(index, len(accessors), f"attribute {semantic}")
            if "indices" in primitive:
                _index(primitive["indices"], len(accessors), "primitive indices")
            if "material" in primitive:
                _index(primitive["material"], len(materials), "primitive material")
            if "JOINTS_0" in attrs and "WEIGHTS_0" in attrs:
                skin_attribute_meshes.add(mesh_id)
            elif "JOINTS_0" in attrs or "WEIGHTS_0" in attrs:
                warnings.append(f"Mesh {mesh_id}: partial skin attribute pair")
            targets = primitive.get("targets", [])
            if not isinstance(targets, list):
                raise GLBInspectionError("Morph targets must be an array")
            for target in targets:
                if not isinstance(target, dict):
                    raise GLBInspectionError("Morph target must be an object")
                for key, accessor in target.items():
                    _index(accessor, len(accessors), f"morph attribute {key}")
            morphs += len(targets)
            primitive_count += 1
    skinned_nodes = 0
    adjacency: list[list[int]] = []
    for node_id, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GLBInspectionError("Node entry must be object")
        if "mesh" in node:
            mesh_id = _index(node["mesh"], len(meshes), f"node {node_id} mesh")
            if "skin" in node:
                _index(node["skin"], len(skins), f"node {node_id} skin")
                skinned_nodes += 1
                if mesh_id not in skin_attribute_meshes:
                    warnings.append(f"Skinned node {node_id} references mesh lacking JOINTS_0/WEIGHTS_0")
        children = node.get("children", [])
        if not isinstance(children, list):
            raise GLBInspectionError("Node children must be an array")
        for child in children:
            _index(child, len(nodes), f"node {node_id} child")
        if len(set(children)) != len(children):
            raise GLBInspectionError("Repeated node child reference")
        adjacency.append(children)
    # A cycle in scene graph transforms can break or hang downstream importers.
    colors = [0] * len(nodes)
    for start in range(len(nodes)):
        if colors[start]:
            continue
        stack = [(start, False)]
        while stack:
            idx, closing = stack.pop()
            if closing:
                colors[idx] = 2
                continue
            if colors[idx] == 1:
                raise GLBInspectionError("Cycle in glTF node graph")
            if colors[idx] == 2:
                continue
            colors[idx] = 1
            stack.append((idx, True))
            for child in reversed(adjacency[idx]):
                if colors[child] == 1:
                    raise GLBInspectionError("Cycle in glTF node graph")
                if colors[child] == 0:
                    stack.append((child, False))
    for anim_id, animation in enumerate(animations):
        if not isinstance(animation, dict):
            raise GLBInspectionError("Animation entry must be an object")
        samplers = animation.get("samplers", [])
        channels = animation.get("channels", [])
        if not isinstance(samplers, list) or not isinstance(channels, list):
            raise GLBInspectionError(f"Animation {anim_id} channels/samplers invalid")
        for sampler in samplers:
            if not isinstance(sampler, dict):
                raise GLBInspectionError("Animation sampler must be an object")
            _index(sampler.get("input"), len(accessors), "sampler input")
            _index(sampler.get("output"), len(accessors), "sampler output")
        for channel in channels:
            if not isinstance(channel, dict):
                raise GLBInspectionError("Animation channel must be an object")
            _index(channel.get("sampler"), len(samplers), "channel sampler")
            target = channel.get("target", {})
            if not isinstance(target, dict):
                raise GLBInspectionError("Animation target invalid")
            if "node" in target:
                _index(target["node"], len(nodes), "animation target node")
    if not meshes:
        warnings.append("No mesh geometry declared")
    if not skins or not skinned_nodes:
        warnings.append("No complete skinned character node detected")
    if not animations:
        warnings.append("No animations declared")
    if morphs == 0:
        warnings.append("No mesh morph targets declared")
    with source.open("rb") as f:
        checksum = hashlib.file_digest(f, "sha256").hexdigest()
    return GLBReport(source.name, checksum, len(accessors), len(meshes), primitive_count,
                     len(skins), joint_count, skinned_nodes, morphs, len(animations),
                     len(materials), tuple(warnings))
