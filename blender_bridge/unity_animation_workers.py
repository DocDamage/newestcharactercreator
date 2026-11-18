"""Build private Unity animated source and independently reopen its Blender lineage."""

from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path

import numpy as np

from blender_bridge.expression_policy import TARGETS, keyname
from blender_bridge.fbx_source import inspect_fbx_source
from blender_bridge.godot_outputs import write_json
from blender_bridge.godot_runtime_geometry import binding_arrays, capture_binding, sampled_mesh
from blender_bridge.godot_runtime_source import character_state
from blender_bridge.godot_source import pose_values
from blender_bridge.native_corrective import NAME, POLICY as SKIN_POLICY
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import bound_scene, digest, reopen_native, scene_objects
from blender_bridge.unity_animation_take import export_animated_fbx, validate_clock
from blender_bridge.unity_source_reference import animated_reference
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import MAX_BYTES as MAX_BINDING_BYTES
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unity_animation_recipe import (
    BIND, BONES, CORRECTION_INPUTS, FBX, FBX_SNAPSHOT, FPS, INPUT_FILES, OUTPUT_LIMITS, POLICY, REFERENCES, SOURCE_FRAMES,
    STAGE, STAGE_REPORT, VERIFY_REPORT, VIRTUAL_FRAME, WEIGHTS, output_option, source_report,
    validate_binding, validate_job,
)


RAW, CORRECTED, NORMALS, WORLD_BONES = REFERENCES


def _file(path: Path, maximum: int, expected: str | None = None) -> str:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise ValueError('Missing or oversized registered Unity source file: '+path.name)
    observed = digest(path)
    if expected is not None and observed != expected:
        raise ValueError('Registered Unity source file SHA changed: '+path.name)
    return observed


def _unused(root, names) -> None:
    if any((root/name).exists() or (root/name).is_symlink() for name in names):
        raise ValueError('Registered Unity source refuses existing outputs')


def _unassigned(bpy, human, rig) -> None:
    if (len(human.data.materials) or bpy.data.libraries or bpy.context.scene.unit_settings.scale_length != 1.
            or len(rig.data.bones) != BONES or any(human.matrix_world[i][j] != float(i == j)
                                                    for i in range(4) for j in range(4))
            or any(image.source != 'VIEWER' or image.filepath or image.packed_file is not None for image in bpy.data.images)):
        raise ValueError('Registered Unity V1 requires the unassigned MPFB world-metre source profile')


def _context(bpy, root, job, *, validate_worker_job=validate_job, validate_target_binding=validate_binding):
    options = job['options']
    validate_worker_job(job['operation'], job['input_project'], options)
    raw = read_json(root/'target_binding.json', options['target_binding_sha256'], MAX_BINDING_BYTES)
    binding = TargetActionBinding.from_dict(raw)
    validate_target_binding(binding, options)
    if bpy.app.version[:2] != (5, 3):
        raise ValueError('Registered Unity source requires Blender 5.3')
    bound_scene(root/'candidate.blend', options['master_sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig = scene_objects(bpy)
    _unassigned(bpy, human, rig)
    state = character_state(bpy, human, rig)
    native_options = {key: options[key] for name, key in INPUT_FILES.items() if name != 'target_binding.json'}
    native_options['source_sha256'] = options['source_sha256']
    return options, state, native_options


def _frame(bpy, human, rig, *, references=REFERENCES) -> dict[str, bytes]:
    corrected, normals = sampled_mesh(bpy, human)
    modifier = human.modifiers[NAME]
    modifier.show_viewport = False
    try:
        raw, _ = sampled_mesh(bpy, human)
    finally:
        modifier.show_viewport = True
        bpy.context.view_layer.update()
    poses = pose_values(rig, human, [bone.name for bone in rig.data.bones])
    return {name: np.asarray(values, dtype='<f4').tobytes()
            for name, values in zip(references, (raw, corrected, normals, poses), strict=True)}


def _references(bpy, root, native_options, state, *, write, references=REFERENCES):
    hashes = {name: sha256() for name in references}
    first = {}
    frames = 0
    with ExitStack() as stack:
        streams = {name: stack.enter_context((root/name).open('xb')) for name in references} if write else {}

        def observe(api, human, rig, frame, _skin_sha):
            nonlocal frames
            if frame != frames + 1 or frame > SOURCE_FRAMES or human.modifiers.get(NAME) is None:
                raise ValueError('Registered Unity source has incomplete 300-frame corrective-skin coverage')
            values = _frame(api, human, rig, references=references)
            if frame == 1:
                first.update(values)
            for name, data in values.items():
                if len(data) != references[name] // SOURCE_FRAMES:
                    raise ValueError('Registered Unity native reference has unexpected dimensions')
                hashes[name].update(data)
                if write:
                    streams[name].write(data)
            frames += 1

        reopened = reopen_native(bpy, root, native_options, frame_observer=observe)
    human, rig = scene_objects(bpy)
    _unassigned(bpy, human, rig)
    validate_clock(bpy.context.scene, rig.animation_data.action)
    if (frames != SOURCE_FRAMES or reopened['skin_deformation_policy'] != SKIN_POLICY
            or character_state(bpy, human, rig) != state):
        raise ValueError('Registered Unity review changed source state, corrective profile or clock')
    return human, rig, first, {name: value.hexdigest() for name, value in hashes.items()}


def _correction_inputs(bpy, root, human, rig, *, write: bool) -> dict[str, str]:
    arrays = binding_arrays(capture_binding(bpy, human, rig, human.modifiers[NAME]))
    result = {}
    for name, exact_bytes in CORRECTION_INPUTS.items():
        payload = arrays[name].tobytes()
        if len(payload) != exact_bytes:
            raise ValueError('Unity corrective operands differ from the exact source topology')
        if write:
            with (root/name).open('xb') as stream:
                stream.write(payload)
        result[name] = sha256(payload).hexdigest()
    return result


@contextmanager
def _bind_donor(bpy, human):
    donor = human.copy()
    donor.data = human.data.copy()
    bpy.context.scene.collection.objects.link(donor)
    try:
        donor.modifiers.remove(donor.modifiers[NAME])
        yield donor
    finally:
        data = donor.data
        bpy.data.objects.remove(donor, do_unlink=True)
        bpy.data.meshes.remove(data)


def stage(bpy, root: Path, job: dict) -> dict:
    _unused(root, OUTPUT_LIMITS)
    options, state, native_options = _context(bpy, root, job)
    human, rig, first, references = _references(bpy, root, native_options, state, write=True)
    references.update(_correction_inputs(bpy, root, human, rig, write=True))
    scene = bpy.context.scene

    def check_virtual_endpoint():
        try:
            scene.frame_set(VIRTUAL_FRAME)
            bpy.context.view_layer.update()
            if _frame(bpy, human, rig) != first:
                raise ValueError('Unity export virtual endpoint does not reproduce registered sample one')
        finally:
            scene.frame_set(0)
            bpy.context.view_layer.update()

    with _bind_donor(bpy, human) as donor:
        bind, weights = animated_reference(bpy, donor, rig, master_sha=options['master_sha256'],
                                           request_sha=options['target_binding_sha256'])
        write_json(root/BIND, bind)
        write_json(root/WEIGHTS, weights)
        export_animated_fbx(bpy, donor, rig, root/FBX, check_virtual_endpoint)
    if character_state(bpy, human, rig) != state:
        raise ValueError('Registered Unity source export changed the reopened original state')
    with (root/FBX).open('rb') as stream:
        if not stream.read(23).startswith(b'Kaydara FBX Binary'):
            raise ValueError('Expected actual binary Unity animation FBX')
    files = {name: _file(root/name, maximum, references.get(name)) for name, maximum in OUTPUT_LIMITS.items()
             if name != STAGE_REPORT}
    write_json(root/STAGE_REPORT, source_report(options, files))
    _check_inputs(root, options)
    return {'policy': POLICY, 'files': {**files, STAGE_REPORT: digest(root/STAGE_REPORT)},
            'engine_import_verified': False}


def _check_inputs(root, options):
    for name, key in INPUT_FILES.items():
        _file(root/name, 512 * 1024**2, options[key])


def _neutral_facial_action(bpy, rig, auxiliary) -> bool:
    """The combined Unity FBX includes the twelve canonical constant facial curves."""
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if (len(auxiliary) != 1 or len(meshes) != 1 or
            not any(mod.type == 'ARMATURE' and mod.object == rig for mod in meshes[0].modifiers)):
        return False
    keys = meshes[0].data.shape_keys
    animation = keys.animation_data if keys is not None else None
    action = auxiliary[0]
    if (animation is None or animation.action != action or animation.action_slot is None or
            len(animation.nla_tracks) or len(animation.drivers) or
            action.users - int(action.use_fake_user) != 1 or len(action.slots) != 1 or
            len(keys.key_blocks) != len(TARGETS) + 1 or not keys.use_relative):
        return False

    expected = set()
    for role, family, _ in TARGETS:
        key = keys.key_blocks.get(keyname(role, family))
        if key is None or key.value != 0.0:
            return False
        expected.add(key.path_from_id('value'))

    bags = [bag for layer in action.layers for strip in layer.strips for bag in strip.channelbags]
    if len(bags) != 1 or bags[0].slot_handle != animation.action_slot.handle or len(bags[0].fcurves) != len(expected):
        return False
    start, end = (float(x) for x in rig.animation_data.action.frame_range)
    if end - start != VIRTUAL_FRAME - 1:
        return False
    for curve in bags[0].fcurves:
        if (curve.data_path not in expected or curve.array_index != 0 or curve.mute or len(curve.modifiers) or
                len(curve.sampled_points) or len(curve.keyframe_points) != VIRTUAL_FRAME):
            return False
        expected.remove(curve.data_path)
        if any(point.interpolation != 'LINEAR' or point.co.x != start + i or point.co.y != 0.0
               for i, point in enumerate(curve.keyframe_points)):
            return False
    return not expected


def _check_fbx(bpy, root, bind, expected_sha, *, fbx=FBX, readback=FBX_SNAPSHOT, world_bones=WORLD_BONES, engine='Unity'):
    observed = inspect_fbx_source(bpy, root/fbx, root/readback, expected_sha,
        validate_auxiliary_actions=lambda rig, actions: _neutral_facial_action(bpy, rig, actions))
    if (observed['fps'] != FPS or observed['frame_count'] != VIRTUAL_FRAME
            or observed['bone_count'] != BONES):
        raise ValueError(f'Reimported {engine} FBX take lost the 30 Hz clock or exact skeleton')
    snapshot = read_json(root/readback, observed['snapshot']['sha256'], 64 * 1024**2)
    named = {bone['name']: bone for bone in bind['bones']}
    if {row['name']: row['parent'] for row in snapshot['bones']} != {name: bone['parent'] for name, bone in named.items()}:
        raise ValueError(f'Reimported {engine} FBX bone hierarchy differs from the saved target')
    indices = {row['name']: index for index, row in enumerate(snapshot['bones'])}
    order = [indices[name] for name in named]
    rest = np.asarray(snapshot['armature_rest_world']).reshape(4, 4) @ np.asarray(
        [row['matrix'] for row in snapshot['bones']]).reshape(BONES, 4, 4)[order]
    authored_rest = np.asarray([bone['world'] for bone in named.values()]).reshape(BONES, 4, 4)
    if np.max(np.abs(rest-authored_rest)) > 1e-4:
        raise ValueError(f'Reimported {engine} FBX changed neutral world bind matrices')
    source = np.fromfile(root/world_bones, dtype='<f4').reshape(SOURCE_FRAMES, BONES, 4, 4)
    for index, row in enumerate(snapshot['frames']):
        world = np.asarray(row['armature_world']).reshape(4, 4)
        poses = np.asarray(row['poses']).reshape(BONES, 4, 4)[order]
        if np.max(np.abs(world @ poses-source[index % SOURCE_FRAMES])) > 1e-4:
            raise ValueError(f'Reimported {engine} FBX world pose differs from the original registered Action')
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    if len(rigs) != 1 or len(meshes) != 1 or not any(mod.type == 'ARMATURE' and mod.object == rigs[0]
                                                  for mod in meshes[0].modifiers):
        raise ValueError(f'Reimported {engine} FBX lost its actual skinned mesh')
    return observed['snapshot']['sha256']


def verify(bpy, root: Path, job: dict) -> dict:
    _unused(root, (VERIFY_REPORT, FBX_SNAPSHOT))
    options, state, native_options = _context(bpy, root, job)
    files = {name: _file(root/name, maximum, options[output_option(name)])
             for name, maximum in OUTPUT_LIMITS.items()}
    human, rig, _, references = _references(bpy, root, native_options, state, write=False)
    references.update(_correction_inputs(bpy, root, human, rig, write=False))
    if any(files[name] != expected or (root/name).stat().st_size != OUTPUT_LIMITS[name]
           for name, expected in references.items()):
        raise ValueError('Unity raw or corrected source references differ after reopening the registered Action')
    with _bind_donor(bpy, human) as donor:
        bind, weights = animated_reference(bpy, donor, rig, master_sha=options['master_sha256'],
                                           request_sha=options['target_binding_sha256'])
    for name, expected in ((BIND, bind), (WEIGHTS, weights),
                           (STAGE_REPORT, source_report(options, {key: value for key, value in files.items()
                                                                if key != STAGE_REPORT}))):
        if canonical_bytes(read_json(root/name, files[name], OUTPUT_LIMITS[name])) != canonical_bytes(expected):
            raise ValueError('Unity staged bind, weights or clock differ after fresh native reopening')
    snapshot = _check_fbx(bpy, root, bind, files[FBX])
    for name, expected in files.items():
        _file(root/name, OUTPUT_LIMITS[name], expected)
    _check_inputs(root, options)
    write_json(root/VERIFY_REPORT, source_report(options, files, fbx_readback_sha256=snapshot))
    return {'policy': POLICY, 'verification_sha256': digest(root/VERIFY_REPORT), 'fbx_readback_sha256': snapshot,
            'files': files, 'engine_import_verified': False}


def run(bpy, root: Path, job: dict) -> dict:
    validate_job(job['operation'], job['input_project'], job['options'])
    return (stage if job['operation'] == STAGE else verify)(bpy, root, job)
