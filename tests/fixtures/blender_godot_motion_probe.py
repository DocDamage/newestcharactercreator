"""Original diagnostic controls on the actual MPFB rig, never a shipping clip."""
from blender_bridge.expression_clip_action import all_curves
from blender_bridge.face_geometry import float32

CONTROLS = (("root", 'Y', .2), ("upperarm01.L", 'Z', .25),
            ("spine03", 'X', .1), ("wrist.R", 'X', .2), ("finger2-1.R", 'Z', .4))


def create(bpy, rig) -> None:
    if rig.animation_data is not None:
        raise ValueError('Diagnostic requires an unanimated original MPFB rig')
    rig.animation_data_create()
    rig.animation_data.action = bpy.data.actions.new('UCC_NONSHIPPING_GODOT_MOTION_DIAGNOSTIC_V1')
    for frame in (1, 13, 25):
        for name, axis, peak in CONTROLS:
            bone = rig.pose.bones[name]
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = (0., 0., 0.)
            bone.rotation_euler['XYZ'.index(axis)] = peak if frame == 13 else 0.
            if not bone.keyframe_insert('rotation_euler', frame=frame):
                raise ValueError('Actual MPFB control keyframe insertion failed')
    for curve in all_curves(rig.animation_data.action):
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()


def verify_controls(rig, frame: int) -> None:
    for name, axis, peak in CONTROLS:
        peak = float32(peak)
        start, delta, elapsed = (0., peak, frame-1) if frame <= 13 else (peak, -peak, frame-13)
        expected = float32(start + float32(float32(delta*elapsed)/12.))
        observed = rig.pose.bones[name].rotation_euler
        if any(abs(value-(expected if index == 'XYZ'.index(axis) else 0.)) > 1e-7
               for index, value in enumerate(observed)):
            raise ValueError('Actual source Action differs from independently computed controls')
