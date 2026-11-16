"""Private real Key Action and closed saved-Action observation, without repair."""
from blender_bridge.expression_policy import TARGETS, keyname
from blender_bridge.face_geometry import intake, float32

ACTION_NAME = 'UCC_PRIVATE_EXPRESSION_CLIP_V1'


def linear_weight(peak: float, frame: int) -> float:
    """Independent float32 linear interpolation, not FCurve.evaluate.

    Blender evaluates the float product before its division. Keeping these
    roundings explicit avoids concealing a one-ULP mismatch behind tolerance.
    """
    if frame in (1, 25): return 0.
    if frame == 13: return peak
    begin, delta, elapsed = (0., peak, frame-1) if frame < 13 else (peak, -peak, frame-13)
    return float32(begin+float32(float32(delta*elapsed)/12.))


def peaks(parameters: dict, race: dict) -> dict:
    return {(r, f): float32(parameters[r]*race[f]) for r, f, _ in TARGETS}


def all_curves(action) -> list:
    if len(action.layers) != 1 or len(action.layers[0].strips) != 1:
        raise ValueError('Expression Action requires one layer and one keyframe strip')
    strip = action.layers[0].strips[0]
    if strip.type != 'KEYFRAME' or len(strip.channelbags) != 1:
        raise ValueError('Expression Action requires one actual keyframe channel bag')
    return list(strip.channelbags[0].fcurves)


def reject_unrelated_animation(bpy, *, allowed_key=None, allowed_action=None):
    blocks = [bpy.context.scene, *bpy.data.objects, *bpy.data.materials, *bpy.data.meshes,
              *bpy.data.armatures, *bpy.data.shape_keys, *bpy.data.node_groups]
    blocks += [o.data for o in bpy.data.objects if o.data is not None]
    blocks += [m.node_tree for m in bpy.data.materials if m.node_tree is not None]
    for data in blocks:
        animation = getattr(data, 'animation_data', None)
        permitted = allowed_key is not None and data == allowed_key and animation is not None and animation.action == allowed_action
        if animation and ((animation.action and not permitted) or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError('Saved expression/source contains unsupported unrelated animation or drivers')


def source_intake(bpy):
    human, rig, service, targets = intake(bpy)
    if len(bpy.data.actions):
        raise ValueError('Expression source must not contain an existing Action')
    reject_unrelated_animation(bpy)
    return human, rig, service, targets


def create_action(bpy, human, values: dict) -> None:
    keys = human.data.shape_keys
    keys.animation_data_create(); keys.animation_data.action = bpy.data.actions.new(ACTION_NAME)
    for frame in (1, 13, 25):
        for (role, family), value in values.items():
            key = keys.key_blocks[keyname(role, family)]
            key.value = value if frame == 13 else 0.
            if not key.keyframe_insert(data_path='value', frame=frame):
                raise ValueError('Failed to create actual expression keyframes')
    for curve in all_curves(keys.animation_data.action):
        for point in curve.keyframe_points: point.interpolation = 'LINEAR'
    scene = bpy.context.scene
    scene.render.fps = 24; scene.render.fps_base = 1.
    scene.frame_start = 1; scene.frame_end = 25
    scene.render.frame_map_old = 100; scene.render.frame_map_new = 100
    scene.frame_set(1); bpy.context.view_layer.update()


def saved_intake(bpy, values: dict) -> tuple:
    candidates = [o for o in bpy.data.objects if o.type == 'MESH' and o.data.shape_keys
                  and any(k.name.startswith('UCC_EXPR_V1_') for k in o.data.shape_keys.key_blocks)]
    if len(candidates) != 1:
        raise ValueError('Saved expression preview needs one prepared basemesh')
    human = candidates[0]; keys = human.data.shape_keys; animation = keys.animation_data
    action = animation.action if animation else None
    if (action is None or action.name != ACTION_NAME or len(bpy.data.actions) != 1
            or len(animation.drivers) or len(animation.nla_tracks) or len(action.slots) != 1
            or animation.action_slot != action.slots[0] or animation.action_influence != 1.
            or animation.action_blend_type != 'REPLACE' or list(action.frame_range) != [1., 25.]):
        raise ValueError('Saved expression Action identity, binding, range or blending differs')
    scene = bpy.context.scene
    if (scene.render.fps != 24 or scene.render.fps_base != 1. or scene.frame_start != 1 or scene.frame_end != 25
            or scene.frame_current != 1 or scene.frame_subframe != 0.
            or scene.render.frame_map_old != 100 or scene.render.frame_map_new != 100):
        raise ValueError('Saved expression timeline is not the exact neutral 25-frame/24fps clip')
    curves = all_curves(action)
    expected = {keys.key_blocks[keyname(r, f)].path_from_id('value'): v for (r, f), v in values.items()}
    if (len(curves) != 12 or {c.data_path for c in curves} != set(expected)
            or any(c.array_index != 0 or c.mute or len(c.modifiers) or c.extrapolation != 'CONSTANT' for c in curves)):
        raise ValueError('Saved expression Action has missing, duplicate or unexpected curves/modifiers')
    for curve in curves:
        points = curve.keyframe_points
        if len(points) != 3 or any(p.interpolation != 'LINEAR' or list(p.co) != [float(frame), value]
                for p, frame, value in zip(points, (1, 13, 25), (0., expected[curve.data_path], 0.))):
            raise ValueError('Saved expression Action differs from the exact three linear keys')
    reject_unrelated_animation(bpy, allowed_key=keys, allowed_action=action)
    human, rig, service, targets = intake(bpy, allowed_key_action=action)
    return human, rig, service, targets
