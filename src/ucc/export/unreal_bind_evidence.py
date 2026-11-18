"""Independent finite static bind admission; no engine or source-process imports."""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import UUID
import json
import math
import re
import stat
import time

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from .godot_candidate_contract import canonical_bytes
from .unreal_contract import ENGINE_VERSION, PROFILE, READINESS_FLAGS
from .unreal_engine_profile import FBX_IMPORT, LOD_BUILD, MESH_SETTINGS, TRIANGLE_ORDER_OPTIMIZATION
from .unreal_native_data import decode_native, finite, integer, require
from .unreal_bind_math import (geometry, bone_identities, verify_bind, morphs,
    expected_bone_name, positive_weight_identities, verify_numeric_weights, verify_corner_normals)
from .unreal_material_bounds import verify_material, verify_bounds, verify_graph

SOURCE_FIELDS = frozenset({'schema_version','policy','profile','master_sha256','request_sha256',
    'blender_version','blender_build','material_spec','vertices','quads','triangles','corners',
    'weights','morphs','bones','candidate_observation','source_bind_local_vertices',
    'source_bind_object_world','source_to_unreal_bone_names','original_rig_world',
    'original_rig_object_scale','source_material_name','rig_basis_policy',
    'engine_import_verified','expected_unreal_bone_order'})
RECEIPT_FIELDS = frozenset({'schema_version','policy','mode','state','job_id','request_sha256',
    'toolchain_identity_sha256','engine_profile_sha256','source_descriptor_path','source_descriptor_sha256',
    'source_fbx_path','source_fbx_sha256','observer_dll_sha256','observer_source_files',
    'engine_exe_sha256','engine_build_sha256','native_observation_path','native_observation_sha256',
    'actual_import_settings','actual_lod_build_settings','actual_mesh_settings',
    'actual_triangle_order_optimization','actual_assets','actual_material_graph','scene_actor_class',
    'scene_actor_location','scene_actor_rotation','scene_actor_scale','native_observation_captured'}) | READINESS_FLAGS
ASSETS = {'mesh':'/Game/UCC/Character.Character','skeleton':'/Game/UCC/Character_Skeleton.Character_Skeleton',
          'material':'/Game/UCC/SkinMaterial.SkinMaterial','scene':'/Game/UCC/CharacterScene'}


@dataclass(frozen=True, slots=True)
class UnrealBindAdmission:
    request_sha256: str
    toolchain_identity_sha256: str
    source_reference_sha256: str
    source_normals_sha256: str
    native_observation_sha256: str
    reopened_native_observation_sha256: str
    stage_receipt_sha256: str
    reopened_receipt_sha256: str
    source_vertices: int
    native_vertices: int
    triangles: int
    bones: int
    morphs: int
    source_positive_influences: int
    native_positive_influences: int
    max_correspondence_error_cm: float
    max_bone_head_error_cm: float
    max_bone_basis_error_cm: float
    max_inverse_bind_error_cm: float
    max_morph_error_cm: float
    max_normal_angle_degrees: float
    max_normalized_weight_error: float
    readback_sha256: str
    native_buffer_sha256: tuple[tuple[str, str], ...]
    profile: str = PROFILE
    engine_version: str = ENGINE_VERSION
    native_bind_verified: bool = True
    saved_reopened_bind_verified: bool = True

    def to_dict(self) -> dict:
        result = asdict(self)
        result['native_buffer_sha256'] = dict(self.native_buffer_sha256)
        return {'schema_version':1,'policy':'UCC_UNREAL_FINITE_STATIC_BIND_ADMISSION_V1',
                **result, **{name:False for name in READINESS_FLAGS},
                'sdk_bind_pose_selection_verified':False,'arbitrary_fastmath_guaranteed':False,
                'scope':'DECLARED_STOCK_UE59_PRECISE_CPU_NATIVE_LOD0_BIND_AND_READONLY_REOPEN'}


def _json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate evidence JSON field')
            result[key] = value
        return result
    def nonfinite(value):
        raise ValidationError('Unreal bind evidence JSON contains a nonfinite number')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
        raise ValidationError('Malformed bounded Unreal bind evidence JSON') from error
    require(type(value) is dict, 'evidence JSON root must be an object')
    return value


def _regular(path: Path) -> tuple[int, int, int, int]:
    require(isinstance(path, Path) and path.is_absolute(), 'evidence input must be an absolute file path')
    try:
        for ancestor in (*path.parents, path):
            info = ancestor.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not (getattr(info,'st_file_attributes',0) & 0x400),
                    'evidence input contains a redirected path')
        require(path.resolve() == path and stat.S_ISREG(info.st_mode), 'evidence input is not canonical and regular')
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    except OSError as error:
        raise ValidationError('Unreal bind evidence input is missing or unreadable') from error


def _read(path: Path, expected: str, maximum: int, check) -> tuple[bytes, tuple]:
    require(is_sha256(expected), 'evidence input requires its sealed SHA256')
    check(); identity = _regular(path)
    require(0 < identity[2] <= maximum, 'evidence input exceeds its bounded size')
    result = bytearray(); digest = sha256()
    try:
        with path.open('rb') as stream:
            while True:
                check(); block = stream.read(1024*1024)
                if not block: break
                require(len(result)+len(block) <= maximum, 'evidence input grew past its size cap')
                result.extend(block); digest.update(block)
    except OSError as error:
        raise ValidationError('Unreal bind evidence input could not be read') from error
    require(_regular(path) == identity and len(result) == identity[2] and digest.hexdigest() == expected,
            'evidence input identity or sealed bytes changed')
    return bytes(result), identity


def _vector(value: object, count: int) -> None:
    require(type(value) is list and len(value) == count, 'source vector dimension differs')
    for number in value: finite(number)


def _source(value: dict, request: str, spec: SkinMaterialSpec, check) -> None:
    require(set(value) == SOURCE_FIELDS, 'source reference fields differ from the closed profile')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['policy'] == 'UCC_UNREAL_ORIGINAL_BIND_REFERENCE_V1'
            and value['profile'] == PROFILE and value['request_sha256'] == request
            and is_sha256(value['master_sha256']) and value['engine_import_verified'] is False,
            'source reference request, identity or profile differs')
    require(canonical_bytes(value['material_spec']) == canonical_bytes(spec.to_dict()), 'source material differs from reviewed parameters')
    require(value['source_material_name'] == 'UCC_BODY_MAT_V1_'+spec.sha256[:24]
            and value['rig_basis_policy'] == 'ORIGINAL_OBJECT_AND_REST_DATA_NO_TRANSFORM_APPLICATION_OR_BONE_NORMALIZATION',
            'source material identity or raw rig basis policy differs')
    for name in ('blender_version','blender_build'):
        require(type(value[name]) is str and 0 < len(value[name]) <= 160, 'source tool version metadata malformed')
    points = value['vertices']; triangles = value['triangles']; bones = value['bones']; controls = value['morphs']
    require(type(points) is list and 0 < len(points) <= 200000 and type(triangles) is list
            and 0 < len(triangles) <= 400000 and type(bones) is list and 0 < len(bones) <= 1024
            and type(controls) is dict and len(controls) <= 256, 'source domain exceeds the bounded native profile')
    for index, point in enumerate(points):
        if index % 256 == 0: check()
        _vector(point,3)
    require(type(value['source_bind_local_vertices']) is list and len(value['source_bind_local_vertices']) == len(points)
            and type(value['weights']) is list and len(value['weights']) == len(points), 'source bind/weight domain differs')
    for index,row in enumerate(value['source_bind_local_vertices']):
        if index % 256 == 0: check()
        _vector(row,3)
    for name in ('source_bind_object_world','original_rig_world'): _vector(value[name],16)
    _vector(value['original_rig_object_scale'],3)
    require(all(number > 0 for number in value['original_rig_object_scale']), 'source rig scale is nonpositive')
    require(type(value['candidate_observation']) is dict and type(value['quads']) is list,
            'source original topology metadata malformed')
    require(len(value['quads']) <= len(triangles), 'source quad domain exceeds triangulation')
    for index,row in enumerate(value['quads'] + triangles):
        if index % 256 == 0: check()
        require(type(row) is list and len(row) == (4 if index < len(value['quads']) else 3) and all(type(i) is int and 0 <= i < len(points) for i in row)
                and len(set(row)) == len(row), 'source topology contains invalid/repeated vertex identities')
    require(type(value['corners']) is list and len(value['corners']) == len(triangles), 'source corner coverage differs')
    for index, row in enumerate(value['corners']):
        if index % 256 == 0: check()
        require(type(row) is dict and set(row) == {'vertices','uv'} and row['vertices'] == triangles[index]
                and type(row['uv']) is list and len(row['uv']) == 3, 'source triangle corner identity differs')
        for uv in row['uv']: _vector(uv,2)
    names = set()
    for row in bones:
        require(type(row) is dict and set(row) == {'name','parent','world'} and type(row['name']) is str
                and 0 < len(row['name']) <= 160 and row['name'] not in names, 'source bone identity malformed')
        names.add(row['name']); _vector(row['world'],16)
    require(all(row['parent'] is None or row['parent'] in names for row in bones), 'source bone parent missing')
    mapping = value['source_to_unreal_bone_names']
    require(type(mapping) is dict and set(mapping) == names and all(type(name) is str for name in mapping.values())
            and len({name.casefold() for name in mapping.values()}) == len(names),
            'source canonical bone naming is not bijective')
    for name,target in mapping.items():
        require(type(target) is str and target == expected_bone_name(name), 'source bone canonicalization differs')
    require(type(value['expected_unreal_bone_order']) is list and len(value['expected_unreal_bone_order']) == len(bones)
            and set(value['expected_unreal_bone_order']) == set(mapping.values()), 'source declared bone order differs')
    for index,row in enumerate(value['weights']):
        if index % 256 == 0: check()
        require(type(row) is list and 1 <= len(row) <= 8, 'source positive influence count unsupported')
        identities = set()
        for influence in row:
            require(type(influence) is list and len(influence) == 2 and influence[0] in names
                    and influence[0] not in identities and 0 < finite(influence[1]) <= 1, 'source positive influence identity malformed')
            identities.add(influence[0])
    for name,rows in controls.items():
        check(); require(type(name) is str and 0 < len(name) <= 160 and type(rows) is list and len(rows) == len(points),
                         'source morph identity or coverage differs')
        for index,row in enumerate(rows):
            if index % 256 == 0: check()
            _vector(row,3)


def _settings(actual: object, expected: dict) -> None:
    require(type(actual) is dict and set(actual) == set(expected), 'actual native option domain differs')
    for name,value in expected.items():
        observed = actual[name]
        if type(value) is bool: require(observed is value, 'actual native boolean option differs')
        elif type(value) is str:
            require(type(observed) is str and (observed == value or re.fullmatch(r'<'+re.escape(value)+r': [0-9]+>',observed)),
                    'actual native enum option differs')
        elif type(value) is list:
            require(type(observed) is list and len(observed) == len(value)
                    and all(finite(a) == b for a,b in zip(observed,value)), 'actual native vector option differs')
        else: require(finite(observed) == value, 'actual native numeric option differs')


def _receipt(value: dict, mode: str, path: Path, observation_sha: str, request: str, toolchain: str) -> None:
    require(set(value) == RECEIPT_FIELDS and type(value['schema_version']) is int and value['schema_version'] == 1
            and value['policy'] == 'UCC_UNREAL_NATIVE_BIND_CAPTURE_V1' and value['mode'] == mode
            and value['state'] == 'CAPTURED_UNVERIFIED' and value['native_observation_captured'] is True,
            'native receipt mode or closed policy differs')
    require(value['request_sha256'] == request and value['toolchain_identity_sha256'] == toolchain
            and value['native_observation_sha256'] == observation_sha
            and type(value['native_observation_path']) is str and Path(value['native_observation_path']) == path,
            'native receipt names different sealed request, toolchain or observation')
    require(all(value[name] is False for name in READINESS_FLAGS), 'raw receipt asserts unverified readiness')
    try: require(str(UUID(value['job_id'])) == value['job_id'], 'native receipt job identity noncanonical')
    except (ValueError,TypeError,AttributeError) as error: raise ValidationError('Malformed native receipt job identity') from error
    for name in ('engine_profile_sha256','source_descriptor_sha256','source_fbx_sha256',
                 'observer_dll_sha256','engine_exe_sha256','engine_build_sha256'):
        require(is_sha256(value[name]), 'native receipt identity SHA malformed')
    for name in ('source_descriptor_path','source_fbx_path'):
        require(type(value[name]) is str and 0 < len(value[name]) <= 4096
                and not any(ord(c) < 32 for c in value[name]), 'native receipt source path metadata malformed')
    files = value['observer_source_files']
    require(type(files) is dict and 0 < len(files) <= 64 and all(type(name) is str
            and 0 < len(name) <= 240 and is_sha256(sha) for name,sha in files.items()), 'native observer source manifest malformed')
    _settings(value['actual_import_settings'], FBX_IMPORT); _settings(value['actual_lod_build_settings'], LOD_BUILD)
    _settings(value['actual_mesh_settings'], MESH_SETTINGS)
    require(type(value['actual_triangle_order_optimization']) is int
            and value['actual_triangle_order_optimization'] == TRIANGLE_ORDER_OPTIMIZATION, 'native triangle optimization policy differs')
    require(value['actual_assets'] == ASSETS and value['scene_actor_class'] == 'SkeletalMeshActor', 'native asset/scene identity differs')
    for name,target in [('scene_actor_location',[0,0,0]),('scene_actor_rotation',[0,0,0]),('scene_actor_scale',[1,1,1])]:
        require(type(value[name]) is list and len(value[name]) == 3 and all(finite(a) == b for a,b in zip(value[name],target)),
                'native saved actor transform differs from the declared identity')


def verify_unreal_bind(source_reference: Path, source_normals: Path, native_observation: Path, *,
        reopened_native_observation: Path, stage_receipt: Path, stage_receipt_sha256: str,
        reopened_receipt: Path, reopened_receipt_sha256: str, request_sha256: str,
        toolchain_identity_sha256: str, source_reference_sha256: str, source_normals_sha256: str,
        native_observation_sha256: str, reopened_native_observation_sha256: str, engine_version: str,
        material_spec: SkinMaterialSpec, material_slot_name: str, imported_material_slot_name: str,
        cancel: Event | None = None, deadline: float | None = None) -> UnrealBindAdmission:
    """Admit all finite bind fields; caller separately verifies engine/source job provenance."""
    require(is_sha256(request_sha256) and is_sha256(toolchain_identity_sha256) and engine_version == ENGINE_VERSION
            and type(material_spec) is SkinMaterialSpec, 'bind admission needs exact reviewed request/toolchain/profile/material')
    require(deadline is None or type(deadline) in (int,float) and math.isfinite(deadline), 'bind deadline malformed')
    def check():
        if deadline is not None and time.monotonic() >= deadline: raise ProjectStorageError('Unreal bind verification total deadline exceeded')
        if cancel is not None and cancel.is_set(): raise ProjectStorageError('Unreal bind verification cancelled or deadline exceeded')
    inputs = [(source_reference,source_reference_sha256,64*1024*1024),
              (source_normals,source_normals_sha256,1200000*12),
              (native_observation,native_observation_sha256,256*1024*1024),
              (reopened_native_observation,reopened_native_observation_sha256,256*1024*1024),
              (stage_receipt,stage_receipt_sha256,2*1024*1024),(reopened_receipt,reopened_receipt_sha256,2*1024*1024)]
    contents=[]; identities=[]
    for path,sha,maximum in inputs:
        data,identity = _read(path,sha,maximum,check);contents.append(data);identities.append(identity)
    try:
        source=_json(contents[0]); _source(source,request_sha256,material_spec,check)
        stage=_json(contents[4]); fresh=_json(contents[5])
        _receipt(stage,'STAGE',native_observation,native_observation_sha256,request_sha256,toolchain_identity_sha256)
        _receipt(fresh,'FRESH',reopened_native_observation,reopened_native_observation_sha256,request_sha256,toolchain_identity_sha256)
        # Each caller-sealed clone has its own FBX path; compare shared content
        # hashes here while the engine host binds each path to its actual clone.
        for name in ('job_id','engine_profile_sha256','source_descriptor_path','source_descriptor_sha256',
                     'source_fbx_sha256','observer_dll_sha256','observer_source_files','engine_exe_sha256','engine_build_sha256'):
            require(stage[name] == fresh[name], 'saved/reopened producer/source receipt identity differs')
        native=decode_native(_json(contents[2]),engine_version=engine_version,check=check)
        reopened=decode_native(_json(contents[3]),engine_version=engine_version,check=check)
        require(native['readback']['mesh_object'] == ASSETS['mesh']
                and native['readback']['mesh_package'] == '/Game/UCC/Character', 'native observed a different mesh package')
        require(canonical_bytes(native['readback']) == canonical_bytes(reopened['readback']), 'fresh native readback differs; no repair is admitted')
        correspondence,geo=geometry(source,native,check=check); names=source['source_to_unreal_bone_names']
        bone_identities(source,native,names,check=check); bind=verify_bind(source,native,names,check=check)
        positive_weight_identities(source,native,correspondence,names,check=check)
        weights=verify_numeric_weights(source,native,correspondence,names,check=check)
        require(weights['passed'], 'native weights exceed the fixed source-derived finite-profile cap')
        shape=morphs(source,native,correspondence,check=check)
        normal=verify_corner_normals(source,native,correspondence,contents[1],check=check)
        verify_material(source,native,material_slot_name,imported_material_slot_name,check=check)
        verify_graph(stage['actual_material_graph'],fresh['actual_material_graph']); verify_bounds(source,native,check=check)
        for (path,sha,maximum),identity in zip(inputs,identities):
            data,current=_read(path,sha,maximum,check);require(current == identity, 'sealed evidence input replaced during admission')
    except (KeyError,TypeError,IndexError,OverflowError,RecursionError,ValueError) as error:
        raise ValidationError('Malformed or inconsistent bounded Unreal bind evidence') from error
    return UnrealBindAdmission(request_sha256,toolchain_identity_sha256,source_reference_sha256,source_normals_sha256,
        native_observation_sha256,reopened_native_observation_sha256,stage_receipt_sha256,reopened_receipt_sha256,
        len(source['vertices']),len(native['positions']),len(source['triangles']),len(native['bones']),len(native['morphs']),
        sum(len(row) for row in source['weights']),len(native['positive_influences']),geo['maximum_correspondence_error_cm'],
        bind['maximum_native_full_bind_head_error_cm'],bind['maximum_native_full_bind_basis_endpoint_error_cm'],
        bind['maximum_native_inverse_bind_source_witness_error_cm'],shape['maximum_morph_error_cm'],
        normal['maximum_normal_angle_degrees'],weights['maximum_normalized_weight_error'],
        sha256(canonical_bytes(native['readback'])).hexdigest(),tuple(sorted(native['digests'].items())))
