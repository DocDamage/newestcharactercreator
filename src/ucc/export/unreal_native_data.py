"""Bounded closed native V2 decoding; structural data is not source admission."""
from collections.abc import Callable
import base64
import binascii
import hashlib
import math
import struct
from ucc.core.errors import ValidationError
from .unreal_contract import ENGINE_VERSION

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValidationError(reason)


def finite(value: object) -> float:
    require(type(value) in (int, float), 'numeric field must be finite')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValidationError('Numeric field must be finite') from error
    require(math.isfinite(result), 'numeric field must be finite')
    return result


def integer(value: object, low: int, high: int) -> int:
    require(type(value) is int and low <= value <= high, "integer field outside contract")
    return value


def buffer(value: object, encoding: str, fmt: str, max_count: int, *, check=None) -> tuple[list[tuple], str]:
    require(type(value) is dict and set(value) == {"encoding", "count", "bytes", "base64"},
            "native buffer fields differ")
    require(value["encoding"] == encoding, "native buffer encoding differs")
    count = integer(value["count"], 0, max_count)
    size = struct.calcsize("<" + fmt)
    require(type(value["base64"]) is str and len(value["base64"]) <= ((count * size + 2) // 3) * 4,
            "native base64 exceeds declared length")
    require(type(value["bytes"]) is int and value["bytes"] == count * size, "native byte count differs")
    try:
        raw = base64.b64decode(value["base64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("invalid native base64") from exc
    require(len(raw) == count * size, "native decoded byte count differs")
    require(base64.b64encode(raw).decode("ascii") == value["base64"], "noncanonical native base64")
    rows = list(struct.iter_unpack("<" + fmt, raw))
    for index, row in enumerate(rows):
        if check is not None and index % 4096 == 0: check()
        for component in row:
            if isinstance(component, float):
                finite(component)
    return rows, hashlib.sha256(raw).hexdigest()


def byte_buffer(value: object, encoding: str, max_bytes: int) -> tuple[bytes, str]:
    require(type(value) is dict and set(value) == {"encoding", "count", "bytes", "base64"},
            "native raw buffer fields differ")
    require(value["encoding"] == encoding, "native raw buffer encoding differs")
    count = integer(value["count"], 0, max_bytes)
    require(type(value["bytes"]) is int and value["bytes"] == count, "native raw buffer count differs")
    require(type(value["base64"]) is str and len(value["base64"]) == ((count + 2) // 3) * 4,
            "native raw base64 size differs")
    try:
        raw = base64.b64decode(value["base64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("invalid native raw base64") from exc
    require(len(raw) == count and base64.b64encode(raw).decode("ascii") == value["base64"],
            "native raw decoded/canonical bytes differ")
    return raw, hashlib.sha256(raw).hexdigest()


def f32(value: object) -> float:
    return struct.unpack("<f", struct.pack("<f", finite(value)))[0]

ROOT_FIELDS = {"schema_version", "policy", "engine_version", "observer_module", "status", "reason",
               "native_data_observed", "source_parity_verified", "runtime_gpu_verified",
               "asset_modified_or_saved", "readback"}


READBACK_FIELDS = {'mesh_package','mesh_object','unit','positions','normals','uv0','triangle_indices',
                  'positive_influence_counts','positive_influences','native_weight_storage_bytes',
                  'native_bone_index_storage_bytes','native_variable_influences','native_unified_bone_map',
                  'api_weight_normalization','inverse_bind_matrices','bones','morphs',
                  'native_uv_storage_full_precision','native_high_precision_tangent_basis',
                  'native_max_bone_influences','native_constant_influences_stride',
                  'native_constant_influences_bone_weights_offset','native_weight_data','native_weight_lookup',
                  'unified_bone_map','sections','materials','bounds'}


def decode_native(root: dict, *, engine_version: str = ENGINE_VERSION, check: Callable[[], None] | None = None) -> dict:
    guard = check or (lambda: None)
    guard()
    require(type(root) is dict, "native observation root must be an object")
    require(engine_version == ENGINE_VERSION and root.get("engine_version") == engine_version, "native engine version differs")
    require(type(root.get("observer_module")) is str and 0 < len(root["observer_module"]) <= 4096
            and not any(ord(c) < 32 for c in root["observer_module"]), "native observer module identity malformed")
    require(set(root) == ROOT_FIELDS, "observer root fields differ")
    require(root["schema_version"] == 2 and type(root["schema_version"]) is int, "observer version differs")
    require(root["policy"] == "UCC_PRIVATE_UNREAL_CONST_OBSERVATION_V2", "observer policy differs")
    require(root["status"] == "CAPTURED_UNVERIFIED" and root["reason"] == "HOST_SOURCE_PARITY_REQUIRED",
            "observer did not capture an unverified native mesh")
    require(root["native_data_observed"] is True, "observer native flag differs")
    for key in ("source_parity_verified", "runtime_gpu_verified", "asset_modified_or_saved"):
        require(root[key] is False, "observer asserted forbidden parity/runtime/save claim")
    rb = root["readback"]
    require(type(rb) is dict and set(rb)==READBACK_FIELDS, 'native readback fields differ')
    require(rb["unit"] == "native_unreal_centimeter", "native unit differs")
    require(rb['api_weight_normalization']=='uint16_div65535; stored8bit_expands257_per_engine_accessor',
            'native API weight normalization convention differs')
    data, digests = {}, {}
    specs = {
        "positions": ("float32x3_le", "fff", 200000),
        "normals": ("float32x3_le", "fff", 200000),
        "uv0": ("float32x2_le", "ff", 200000),
        "triangle_indices": ("uint32_le", "I", 1200000),
        "positive_influence_counts": ("uint32_le", "I", 200000),
        "positive_influences": ("uint32_vertex_uint32_bone_uint16_apiweight_le", "IIH", 1600000),
        "inverse_bind_matrices": ("float32x16_rowmajor_le", "16f", 1024),
    }
    for key, (encoding, fmt, limit) in specs.items():
        data[key], digests[key] = buffer(rb[key], encoding, fmt, limit, check=guard)
    count = len(data["positions"])
    require(0 < count <= 200000, "empty native geometry")
    for key in ("normals", "uv0", "positive_influence_counts"):
        require(len(data[key]) == count, "native vertex buffer counts differ")
    indices = [r[0] for r in data["triangle_indices"]]
    require(len(indices) > 0 and len(indices) % 3 == 0, "native index count is not triangles")
    require(all(0 <= i < count for i in indices), "native index outside vertex domain")
    require(set(indices) == set(range(count)), "native vertices not covered by triangles")
    bones = rb["bones"]
    require(type(bones) is list and 0 < len(bones) <= 1024, "native bone count outside contract")
    require(len(data["inverse_bind_matrices"]) == len(bones), "native inverse-bind count differs")
    names = set()
    for index, bone in enumerate(bones):
        if index % 128 == 0: guard()
        require(set(bone) == {"name", "parent", "local_trs_float64_quaternion_xyzw_translation_scale"},
                "native bone fields differ")
        require(type(bone["name"]) is str and bone["name"] and bone["name"] not in names,
                "native bone name empty or duplicate")
        names.add(bone["name"])
        require(type(bone["parent"]) is int and (-1 if index == 0 else 0) <= bone["parent"] < index,
                "native bone parent violates ordered single-root hierarchy")
        trs = bone["local_trs_float64_quaternion_xyzw_translation_scale"]
        require(type(trs) is list and len(trs) == 10, "native bone TRS dimensions differ")
        list(map(finite, trs))
        require(abs(sum(x*x for x in trs[:4]) - 1) <= 1e-5, "native bone quaternion is not normalized")
        require(all(abs(s) > 1e-12 for s in trs[7:]), "native bone scale is singular")
    integer(rb['native_weight_storage_bytes'],2,2)
    integer(rb['native_bone_index_storage_bytes'],1,2)
    counts = [0] * count
    sums = [0] * count
    identities = set()
    influences = [[] for _ in range(count)]
    for vertex, bone, weight in data["positive_influences"]:
        require(vertex < count and bone < len(bones) and weight > 0, "native influence outside positive domain")
        require((vertex, bone) not in identities, "duplicate native influence identity")
        identities.add((vertex, bone))
        counts[vertex] += 1
        sums[vertex] += weight
        influences[vertex].append((bone, weight))
    require(all(1 <= c <= 8 for c in counts), "native influence count outside source profile")
    require(counts == [r[0] for r in data["positive_influence_counts"]], "native positive influence counts differ")
    require(all(s == 65535 for s in sums), "native integer skin weights do not sum65535")
    require(rb["native_uv_storage_full_precision"] is True, "native UVs are not full precision")
    require(rb["native_high_precision_tangent_basis"] is True, "native tangent basis is not high precision")
    morphs = rb["morphs"]
    require(type(morphs) is list and len(morphs) <= 256, "native morph count outside contract")
    for row in morphs:
        require(type(row) is dict and set(row) == {"name", "deltas"} and type(row["deltas"]) is dict, "native morph fields differ")
    require(sum(integer(row["deltas"].get("count"), 0, 2000000) for row in morphs) <= 2000000, "native total morph delta cap exceeded")
    morph_names, morph_data = set(), {}
    for morph in morphs:
        guard()
        require(set(morph) == {"name", "deltas"}, "native morph fields differ")
        name = morph["name"]
        require(type(name) is str and name and name not in morph_names, "native morph name empty or duplicate")
        morph_names.add(name)
        rows, digest = buffer(morph["deltas"],
                              "uint32_native_index_float32x3_position_float32x3_tangent_le", "I6f", 2000000, check=guard)
        native_ids = [r[0] for r in rows]
        require(all(i < count for i in native_ids) and len(set(native_ids)) == len(native_ids),
                "native morph index duplicate or outside domain")
        morph_data[name] = {r[0]: r[1:4] for r in rows}
        digests["morph:" + name] = digest
    data.update(bones=bones, influences=influences, morphs=morph_data, digests=digests,
                readback=rb, indices=indices)
    data["raw_weight_evidence"] = verify_raw_weights(data, check=guard)
    digests["native_weight_data"] = data["raw_weight_evidence"]["native_raw_weight_sha256"]
    digests["native_weight_lookup"] = data["raw_weight_evidence"]["native_raw_lookup_sha256"]
    guard()
    return data

def verify_raw_weights(native: dict, *, check: Callable[[], None] | None = None) -> dict:
    guard = check or (lambda: None)
    guard()
    rb = native["readback"]
    count = len(native["positions"])
    maximum = integer(rb["native_max_bone_influences"], 1, 8)
    index_bytes = integer(rb["native_bone_index_storage_bytes"], 1, 2)
    require(rb["native_weight_storage_bytes"] == 2, "native raw weight storage not16bit")
    stride = (index_bytes + 2) * maximum
    require(rb["native_constant_influences_stride"] == stride,
            "native constant weight stride differs")
    require(rb["native_constant_influences_bone_weights_offset"] == index_bytes * maximum,
            "native constant weight offset differs")
    require(type(rb["native_variable_influences"]) is bool and type(rb["native_unified_bone_map"]) is bool,
            "native weight representation flags differ")
    raw, raw_sha = byte_buffer(rb["native_weight_data"], "uint8_native_skin_weight_storage", count * 32)
    lookup, lookup_sha = byte_buffer(rb["native_weight_lookup"], "uint8_native_skin_weight_lookup_storage", count * 4)
    variable = rb["native_variable_influences"]
    require(len(lookup) == (count * 4 if variable else 0), "native lookup byte count differs")
    require(variable or len(raw) == count * stride, "native constant raw data byte count differs")
    sections = rb["sections"]
    require(type(sections) is list and 0 < len(sections) <= 1024, "native section count differs")
    vertex_sections = [None] * count
    index_coverage = [False] * len(native["indices"])
    for section in sections:
        require(set(section) == {"material_index", "base_index", "num_triangles", "base_vertex_index",
                                 "num_vertices", "max_bone_influences", "bone_map", "has_unified_bone_map"},
                "native section fields differ")
        base = integer(section["base_vertex_index"], 0, count - 1)
        vertices = integer(section["num_vertices"], 1, count - base)
        first = integer(section["base_index"], 0, len(native["indices"]) - 1)
        triangles = integer(section["num_triangles"], 1, len(native["indices"]) // 3)
        require(first % 3 == 0 and first + 3 * triangles <= len(index_coverage), "native section index extent differs")
        require(type(section["has_unified_bone_map"]) is bool, "native section unified flag differs")
        integer(section["max_bone_influences"], 1, maximum)
        integer(section["material_index"], 0, len(rb["materials"]) - 1)
        for vertex in range(base, base + vertices):
            require(vertex_sections[vertex] is None, "native vertex sections overlap")
            vertex_sections[vertex] = section
        for index in range(first, first + triangles * 3):
            require(not index_coverage[index], "native triangle sections overlap")
            index_coverage[index] = True
            require(base <= native["indices"][index] < base + vertices, "native triangle escapes section vertices")
        require(type(section["bone_map"]) is list, "native section bone map differs")
        for bone in section["bone_map"]:
            integer(bone, 0, len(native["bones"]) - 1)
    require(all(index_coverage) and all(s is not None for s in vertex_sections), "native section domain incomplete")
    unified = rb["unified_bone_map"]
    require(type(unified) is list, "native unified bone map differs")
    for bone in unified:
        integer(bone, 0, len(native["bones"]) - 1)
    used_ranges = []
    for vertex in range(count):
        if vertex % 256 == 0: guard()
        if variable:
            packed = struct.unpack_from("<I", lookup, vertex * 4)[0]
            offset, influences = packed >> 8, packed & 255
            integer(influences, 1, maximum)
        else:
            offset, influences = vertex * stride, maximum
        end = offset + influences * (index_bytes + 2)
        require(end <= len(raw), "native raw weight slice exceeds storage")
        used_ranges.append((offset, end))
        bone_map = unified if rb["native_unified_bone_map"] else vertex_sections[vertex]["bone_map"]
        actual = {}
        for slot in range(influences):
            weight = struct.unpack_from("<H", raw, offset + index_bytes * influences + 2 * slot)[0]
            if not weight:
                continue
            bone = int.from_bytes(raw[offset + index_bytes * slot:offset + index_bytes * (slot + 1)], "little")
            require(bone < len(bone_map), "native raw bone map index exceeds domain")
            bone = bone_map[bone]
            require(bone not in actual, "native raw positive bone identity duplicated")
            actual[bone] = weight
        require(actual == dict(native["influences"][vertex]), "native raw storage disagrees with API positive weights")
    cursor = 0
    for start, end in sorted(used_ranges):
        require(start == cursor, "native raw data has overlap or unowned bytes")
        cursor = end
    require(cursor == len(raw), "native raw storage has unowned suffix")
    return {"native_raw_api_positive_weights_exact": True, "native_raw_weight_sha256": raw_sha,
            "native_raw_lookup_sha256": lookup_sha, "native_section_domain_complete": True}
