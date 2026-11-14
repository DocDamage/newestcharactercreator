"""Strict MPFB source intake and exact, private facial-state fingerprints."""
from array import array
from hashlib import sha256
import importlib
import math
from pathlib import Path
import struct

from blender_bridge.face_policy import BASE_SHA, RIG_SHA, TARGETS, TOPOLOGY_SHA, digest, read_json
from blender_bridge.mpfb_service import locate_human_service, locate_target_service
from blender_bridge.native_fit_scene import polygon_digest, exact_weights_digest, bone_controls
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.pose_environment import validate_pose_environment
from blender_bridge.face_materials import signature as material_signature


def float32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


def coordinates(key) -> str:
    points = array('f', [0.])* (len(key.data)*3)
    key.data.foreach_get('co', points)
    if not all(math.isfinite(v) for v in points):
        raise ValueError('Nonfinite facial shape coordinates')
    return sha256(points.tobytes()).hexdigest()


def key_settings(key) -> dict:
    return {name: getattr(key, name) for name in ('mute', 'interpolation', 'slider_min', 'slider_max', 'vertex_group')}


def key_state(key) -> dict:
    return {'coordinates': coordinates(key), 'settings': key_settings(key), 'value': float(key.value),
            'relative': key.relative_key.name}


def rest_state(rig) -> dict:
    return {b.name: {'matrix': [float(x) for row in b.matrix_local for x in row],
                     'head': list(b.head_local), 'tail': list(b.tail_local)} for b in rig.data.bones}


def canonical_rest(before: dict, after: dict) -> None:
    # MPFB's float32 refit may round rest coordinates. This intake check never
    # changes the source file. Saved-result verification below is exact.
    if set(before) != set(after) or any(
            abs(a-b) > 1e-6 for name in before for field in before[name]
            for a, b in zip(before[name][field], after[name][field])):
        raise ValueError('Source rest rig differs from the canonical MPFB refit')


def intake(bpy):
    service, module = locate_human_service()
    target_service, _ = locate_target_service(module)
    package = importlib.import_module(module.removesuffix('.services.humanservice'))
    assets = Path(package.__file__).resolve().parent/'data'
    base = assets/'3dobjs/base.obj'; rig_file = assets/'rigs/standard/rig.default.json'
    if base.is_symlink() or digest(base) != BASE_SHA or rig_file.is_symlink() or digest(rig_file) != RIG_SHA:
        raise ValueError('Installed MPFB base/rig assets differ from the pinned family')
    manifest = assets.parent/'blender_manifest.toml'
    import tomllib
    if tomllib.loads(manifest.read_text(encoding='utf-8')).get('version') != '2.0.18':
        raise ValueError('Facial operation supports installed MPFB 2.0.18 only')
    object_service = importlib.import_module(module.rsplit('.', 1)[0]+'.objectservice').ObjectService
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and object_service.object_is_basemesh(o)]
    rigs = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    if len(meshes) != 1 or len(rigs) != 1:
        raise ValueError('Facial operation needs exactly one basemesh/default rig; attached meshes are unsupported')
    human, rig = meshes[0], rigs[0]
    for obj in bpy.data.objects:
        if obj == human or obj == rig:
            continue
        parent = obj.parent
        while parent is not None:
            if parent in (human, rig):
                raise ValueError('Facial refit does not support attached objects')
            parent = parent.parent
        if object_service.object_is_any_makehuman_object(obj) or any(
                mod.type == 'ARMATURE' and mod.object == rig for mod in obj.modifiers):
            raise ValueError('Facial refit does not support related MPFB assets or shared skin')
    if not object_service.object_is_basemesh(human) or not object_service.object_is_skeleton(rig):
        raise ValueError('Facial operation requires a registered MPFB basemesh and skeleton')
    if human.parent != rig or rig.parent is not None or human.data.users != 1 or rig.data.users != 1:
        raise ValueError('Facial operation cannot refit shared or ambiguously parented character data')
    if polygon_digest(human) != TOPOLOGY_SHA:
        raise ValueError('Facial operation requires exact pinned MPFB polygon topology')
    definition = read_json(rig_file, RIG_SHA, 1024*1024)
    if set(definition) != {b.name for b in rig.data.bones}:
        raise ValueError('Facial operation requires the exact default-rig bone set')
    for bone in rig.data.bones:
        expected = definition[bone.name]
        if (bone.parent.name if bone.parent else '') != expected['parent'] or any(
                getattr(bone, field) != expected[field] for field in
                ('inherit_scale', 'use_connect', 'use_inherit_rotation', 'use_local_location')):
            raise ValueError('Facial operation requires the actual default-rig hierarchy and inheritance')
    for obj in bpy.data.objects:
        if obj.library or obj.override_library or len(obj.constraints):
            raise ValueError('Facial operation rejects linked, overridden or constrained objects')
    for data in (human, rig, human.data, rig.data, human.data.shape_keys):
        animation = getattr(data, 'animation_data', None)
        if animation and (animation.action or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError('Facial operation requires an unanimated neutral character')
    if rig.data.pose_position != 'POSE':
        raise ValueError('Facial operation requires normal rig pose evaluation')
    validate_pose_environment(rig, human, [b.name for b in rig.pose.bones])
    source_stack(human, rig)
    from blender_bridge.refit_revision import rig_fingerprint
    rig_fingerprint(bpy, human)
    for vertex in human.data.vertices:
        if any(not math.isfinite(g.weight) or not 0 <= g.weight <= 1.00001 for g in vertex.groups):
            raise ValueError('Facial source has invalid vertex-group weights')
    keys = human.data.shape_keys
    if not keys or not keys.use_relative or human.show_only_shape_key:
        raise ValueError('Facial operation requires ordinary relative MPFB shape keys')
    return human, rig, service, target_service


def own_keys(human, target_service, root: Path, *, create: bool) -> list:
    """Never overwrite an unknown key just because it has a familiar name."""
    keys = human.data.shape_keys.key_blocks
    result = []
    for _, name, _ in TARGETS:
        if any(k.name.startswith(name+'.') for k in keys):
            raise ValueError('Ambiguous suffixed facial shape key: '+name)
        key = keys.get(name)
        if key is None:
            if not create:
                raise ValueError('Saved facial result lacks its declared key: '+name)
            key = target_service.load_target(human, str(root/(name+'.target.gz')), weight=0.)
        else:
            reference_name = 'UCC_FACE_REFERENCE_TEMPORARY'
            if keys.get(reference_name):
                raise ValueError('Reserved temporary facial key already exists')
            reference = target_service.load_target(human, str(root/(name+'.target.gz')),
                                                   weight=0., name=reference_name)
            try:
                if (coordinates(key) != coordinates(reference) or key_settings(key) != key_settings(reference)
                        or key.relative_key != reference.relative_key):
                    raise ValueError('Existing facial key differs from the pinned target: '+name)
            finally:
                human.shape_key_remove(reference)
        if key.name != name or not math.isfinite(key.value) or not 0 <= key.value <= .5:
            raise ValueError('Facial shape key value/name is incompatible')
        result.append(key)
    if result[0].value and result[1].value:
        raise ValueError('Both opposing facial targets are active')
    return result


def invariant_state(bpy, human, rig, target_service) -> dict:
    own = {name for _, name, _ in TARGETS}
    uv = sha256()
    for layer in human.data.uv_layers:
        uv.update(layer.name.encode('utf-8')+b'\0')
        values = array('f', [0.])*(len(layer.data)*2)
        layer.data.foreach_get('uv', values); uv.update(values.tobytes())
    polygons = [(p.material_index, p.use_smooth) for p in human.data.polygons]
    return {'topology': polygon_digest(human), 'weights': exact_weights_digest(human),
            'bone_controls': bone_controls(rig), 'stack': source_stack(human, rig),
            'pose_channels': {b.name: {'mode': b.rotation_mode, 'location': list(b.location),
                                      'scale': list(b.scale), 'quaternion': list(b.rotation_quaternion),
                                      'euler': list(b.rotation_euler), 'axis_angle': list(b.rotation_axis_angle)}
                              for b in rig.pose.bones},
            'macro': target_service.get_macro_info_dict_from_basemesh(human),
            'keys': {k.name: key_state(k) for k in human.data.shape_keys.key_blocks if k.name not in own},
            'key_order': [k.name for k in human.data.shape_keys.key_blocks if k.name not in own],
            'relative_keys': human.data.shape_keys.use_relative,
            'uv_sha256': uv.hexdigest(), 'active_uv_index': human.data.uv_layers.active_index,
            'polygon_material_smooth_sha256': sha256(repr(polygons).encode()).hexdigest(),
            'materials': [m.name if m else None for m in human.data.materials],
            'material_state': material_signature(bpy),
            'unrelated_meshes': {o.name: {'coordinates': mesh_coordinates(o), 'topology': polygon_digest(o),
                                         'weights': exact_weights_digest(o),
                                         'keys': {k.name: key_state(k) for k in o.data.shape_keys.key_blocks}
                                         if o.data.shape_keys else {}}
                                 for o in bpy.data.objects if o.type == 'MESH' and o != human},
            'objects': {o.name: {'type': o.type, 'parent': o.parent.name if o.parent else None,
                                'world': [float(x) for row in o.matrix_world for x in row],
                                'parent_inverse': [float(x) for row in o.matrix_parent_inverse for x in row]}
                        for o in bpy.data.objects}}


def mesh_coordinates(obj) -> str:
    values = array('f', [0.])*(len(obj.data.vertices)*3)
    obj.data.vertices.foreach_get('co', values)
    return sha256(values.tobytes()).hexdigest()


def evaluated(bpy, human, *, full: bool = False) -> list:
    masks = [(m, m.show_viewport) for m in human.modifiers if full and m.type == 'MASK']
    try:
        for mod, _ in masks:
            mod.show_viewport = False
        bpy.context.view_layer.update()
        obj = human.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = obj.to_mesh()
        try:
            result = [tuple(float(v) for v in human.matrix_world @ vert.co) for vert in mesh.vertices]
            if not result or any(not math.isfinite(v) for p in result for v in p):
                raise ValueError('Empty/nonfinite evaluated facial mesh')
            return result
        finally:
            obj.to_mesh_clear()
    finally:
        for mod, value in masks:
            mod.show_viewport = value
        bpy.context.view_layer.update()


def points_digest(points: list) -> str:
    h = sha256()
    for point in points:
        h.update(struct.pack('<3f', *point))
    return h.hexdigest()
