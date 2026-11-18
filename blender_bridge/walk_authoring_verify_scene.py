"""Measure a saved original walk using independent, read-only Blender evaluation."""
from array import array
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from blender_bridge import walk_authoring_phase as phase
from blender_bridge.face_geometry import evaluated, invariant_state, rest_state
from blender_bridge.face_operations import state_digest
from blender_bridge.fbx_source import matrix_values
from blender_bridge.idle_authoring_policy import require


ACTION = 'UCC_ORIGINAL_STANDING_WALK'
LIMITS = {
    'armature_matrix': 1e-6, 'bone_local_translation_m': 2e-5,
    'bone_local_scale_delta': 2e-5, 'fbx_bind_bone_matrix': 1e-4,
    'fbx_world_pose_matrix': 1e-4, 'ankle_target_m': 2e-5,
    'repeat_bone_matrix': 2e-5, 'repeat_skin_coordinate_m': 2e-5,
    'stance_anchor_m': .001, 'stance_drift_m': .001, 'stance_height_m': .001,
    'weighted_foot_penetration_m': .001, 'visible_penetration_m': .001,
    'peak_swing_floor_clearance_min_m': .035, 'knee_flex_min_deg': 12.,
    'knee_flex_max_deg': 65., 'max_adjacent_knee_step_deg': 12.,
}


@dataclass(frozen=True)
class WalkSceneObservation:
    metrics: dict
    bones: dict
    bone_timeline: list[dict[str, list[float]]]
    armature_timeline: list[list[float]]
    neutral_armature: Any
    posed_armature: Any


def matrix(values: list[float]):
    from mathutils import Matrix
    return Matrix([values[i:i + 4] for i in range(0, 16, 4)])


def delta(a, b) -> float:
    require(len(a) == len(b) and len(a) > 0, 'Walk observation arity differs')
    return max(abs(x - y) for x, y in zip(a, b, strict=True))


def _dot_quaternion(a, b) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _check_action(bpy: Any, rig: Any) -> int:
    action = rig.animation_data.action if rig.animation_data else None
    require(action is not None and len(bpy.data.actions) == 1 and action in tuple(bpy.data.actions)
            and len(action.slots)==1 and rig.animation_data.action_slot == action.slots[0]
            and action.name == ACTION and tuple(action.frame_range)==(1.,300.)
            and not len(bpy.data.libraries), 'WRONG_SAVED_WALK_ACTION')
    blocks = [b for prop in bpy.data.bl_rna.properties if prop.type=='COLLECTION'
              for b in getattr(bpy.data,prop.identifier) if isinstance(b,bpy.types.ID)]
    blocks.extend(b.node_tree for b in tuple(blocks) if getattr(b,'node_tree',None) is not None)
    for b in {b.as_pointer():b for b in blocks}.values():
        animation = getattr(b,'animation_data',None)
        require(not b.library and not b.override_library
                and (not animation or (not len(animation.drivers) and not len(animation.nla_tracks)
                     and (animation.action is None or (b==rig and animation.action==action)))),
                'SAVED_WALK_HAS_OTHER_ANIMATION_OR_LIBRARY')
    require(all(not o.constraints for o in bpy.data.objects)
            and all(not b.constraints for b in rig.pose.bones), 'SAVED_WALK_HAS_CONSTRAINTS')
    curves = [curve for layer in action.layers for strip in layer.strips
              for bag in strip.channelbags for curve in bag.fcurves]
    expected = {('location',i) for i in range(3)} | {
        (b.path_from_id('rotation_quaternion'),i) for b in rig.pose.bones for i in range(4)}
    require(len(curves)==len(expected) and {(c.data_path,c.array_index) for c in curves}==expected,
            'MISSING_DUPLICATE_OR_UNSUPPORTED_WALK_CURVE')
    for curve in curves:
        require(not curve.mute and not curve.modifiers and len(curve.keyframe_points)==300
                and all(k.co.x==i and math.isfinite(k.co.y) and k.interpolation=='LINEAR'
                        for i,k in enumerate(curve.keyframe_points,1)), 'WRONG_DENSE_WALK_CURVE')
        if curve.data_path=='location':
            require(all(k.co.y == curve.keyframe_points[0].co.y for k in curve.keyframe_points),
                    'ARMATURE_OFFSET_CURVE_IS_NOT_CONSTANT')
    return len(curves)


def check_invariants(actual: dict, neutral: dict, moving: set[str], z_offset: float) -> None:
    """Allow only the declared inherited world offset and pose channel changes."""
    actual.pop('pose_channels')
    neutral.pop('pose_channels')
    require(set(actual['objects'])==set(neutral['objects']), 'WALK_CHANGED_SCENE_OBJECTS')
    for name, obj in actual['objects'].items():
        a,b = obj.pop('world'),neutral['objects'][name].pop('world')
        if name in moving:
            b[11] += z_offset
        require(delta(a,b)<=LIMITS['armature_matrix'], 'WALK_CHANGED_UNAUTHORIZED_OBJECT_TRANSFORM')
    require(actual==neutral, 'WALK_CHANGED_SOURCE_TOPOLOGY_WEIGHTS_KEYS_OR_MATERIALS')


def _foot_regions(human, frame, neutral, forward):
    regions={}
    for side in ('L','R'):
        mark=frame['sole_patches'][side]
        markers=tuple(mark['indices'])
        groups={g.index for g in human.vertex_groups
                if g.name.endswith('.'+side) and g.name.startswith(('foot','toe'))}
        envelope=tuple(v.index for v in human.data.vertices
                       if any(g.group in groups and g.weight>.05 for g in v.groups))
        require(3 <= len(markers)==len(set(markers)) and set(markers)<=set(envelope)
                and len(mark['neutral_world'])==len(markers), 'BAD_NEUTRAL_WEIGHTED_SOLE_REGION')
        points=[neutral[i] for i in markers]
        require(max(math.dist(a,b) for a,b in zip(points,mark['neutral_world'],strict=True))<=1e-6,
                'INDEPENDENT_NEUTRAL_SOLE_MARKERS_DIFFER')
        along=[sum(x*y for x,y in zip(p,forward,strict=True)) for p in points]
        lo,hi=min(along),max(along)
        require(hi-lo>1e-6,'DEGENERATE_NEUTRAL_SOLE')
        bands=tuple(tuple(i for i,x in enumerate(along)
                          if low <= (x-lo)/(hi-lo) < high)
                    for low,high in ((0.,.25),(.25,.75),(.75,1.01)))
        require(all(bands),'MISSING_REAR_MID_OR_FORE_NEUTRAL_SOLE')
        regions[side]=(markers,envelope,points,bands)
    return regions


def measure_contact(positions, region, foot, travel, forward, floor, anchors) -> dict:
    """Compare measured sole points in the nominal transported ground frame."""
    markers, envelope, neutral, bands = region
    weighted_floor = min(positions[i][2] for i in envelope) - floor
    measurements = {'weighted_floor_m': weighted_floor}
    if foot.phase_index == phase.STANCE_FRAMES + phase.SWING_FRAMES // 2:
        measurements['peak_swing_clearance_m'] = weighted_floor
    if foot.is_stance:
        compensated = tuple(tuple(positions[i][k] + travel * forward[k] for k in (0, 1))
                            for i in markers)
        expected = tuple(tuple(p[k] + foot.stance_anchor_m * forward[k] for k in (0, 1))
                         for p in neutral)
        first = anchors.setdefault(foot.stance_anchor_m, compensated)
        for name, members in zip(('rear', 'mid', 'fore'), bands, strict=True):
            measurements[name + '_anchor_m'] = max(math.dist(compensated[i], expected[i]) for i in members)
            measurements[name + '_drift_m'] = max(math.dist(compensated[i], first[i]) for i in members)
            measurements[name + '_height_m'] = max(abs(positions[markers[i]][2] - neutral[i][2])
                                                      for i in members)
    return measurements


def _flatten(points) -> array:
    return array('f', (value for point in points for value in point))


def wrap_residual(last, first, ref_last, ref_first) -> float:
    """Compare equivalent 1/30 s steps across the end and an internal stride."""
    return phase.FPS * max(abs((b - a) - (d - c))
                           for a, b, c, d in zip(last, first, ref_last, ref_first, strict=True))


def observe_saved(
    bpy: Any, review_path: Path, frame: dict, neutral_human: Any, neutral_rig: Any, target_service: Any,
) -> WalkSceneObservation:
    """Read every persisted sample with the normal mask and the full weighted skin."""
    from mathutils import Vector

    neutral_state=invariant_state(bpy,neutral_human,neutral_rig,target_service)
    neutral_full,neutral_visible=evaluated(bpy,neutral_human,full=True),evaluated(bpy,neutral_human)
    require((len(neutral_full),len(neutral_visible))==(19158,13380),'WRONG_NEUTRAL_SURFACES')
    forward=Vector((*frame['anatomy']['axes']['forward'][:2],0.)).normalized()
    require(forward.length>=.999999,'DEGENERATE_GROUND_AXES')
    regions=_foot_regions(neutral_human,frame,neutral_full,forward)
    floor=min(p[2] for _,_,points,_ in regions.values() for p in points)
    bind=matrix(frame['neutral']['rig_world'])
    posed=bind.copy()
    posed.translation += Vector((0.,0.,phase.ARMATURE_WORLD_Z_M))
    bpy.ops.wm.open_mainfile(filepath=str(review_path),load_ui=False)
    human=bpy.data.objects.get(frame['neutral']['human_name'])
    rig=bpy.data.objects.get(frame['neutral']['rig_name'])
    require(human is not None and human.type=='MESH' and rig is not None and rig.type=='ARMATURE'
            and human.parent==rig and rig.parent is None and rig.data.pose_position=='POSE',
            'WRONG_SAVED_WALK_CHARACTER')
    bones={r['name']:r for r in frame['anatomy']['bones']}
    require(set(bones)==set(rig.pose.bones.keys()) and len(bones)==163
            and state_digest(rest_state(rig))==frame['target']['rest_sha256'], 'SAVED_WALK_CHANGED_REST_RIG')
    scene=bpy.context.scene
    require((scene.frame_start,scene.frame_end,scene.render.fps,scene.render.fps_base)==(1,300,30,1.)
            and scene.unit_settings.scale_length==1., 'WRONG_SAVED_WALK_CLOCK')
    curve_count = _check_action(bpy, rig)
    scene.frame_set(1)
    bpy.context.view_layer.update()
    check_invariants(invariant_state(bpy,human,rig,target_service),neutral_state,
                          {rig.name,human.name},phase.ARMATURE_WORLD_Z_M)
    references, latest, timeline={},None,[]
    counts={'double_stance':0,'left_only':0,'right_only':0}
    anchors={side:{} for side in ('L','R')}
    minimum={'visible_floor_m':math.inf,'whole_full_floor_m':math.inf,'weighted_floor_m':math.inf,
             'peak_swing_clearance_m':math.inf,'knee_flex_deg':math.inf,'knee_pole_alignment':math.inf}
    maximum={k:0. for k in ('armature_matrix','bone_local_translation_m','bone_local_scale_delta',
        'ankle_target_m','repeat_bone_matrix','repeat_skin_coordinate_m','stance_anchor_m',
        'stance_drift_m','stance_height_m','knee_flex_deg','adjacent_knee_step_deg')}
    for band in ('rear','mid','fore'):
        for key in ('anchor','drift','height'):
            maximum[band+'_'+key+'_m']=0.
    neutral_poles={}
    for side in ('L','R'):
        hip,knee,ankle=(Vector(bones[n+'.'+side]['head_world'])
                        for n in ('upperleg01','lowerleg01','foot'))
        axis=(ankle-hip).normalized()
        offset=knee-hip
        neutral_poles[side]=(offset-axis*offset.dot(axis)).normalized()
        require(neutral_poles[side].length>.99,'DEGENERATE_NEUTRAL_KNEE_POLE')
    knee_history = []
    earlier_quats = {}
    first_quats = {}
    first_repeat = None
    armature_timeline = []
    posed_values=matrix_values(posed)
    for frame_index in range(phase.STORED_FRAMES):
        scene.frame_set(frame_index+1)
        bpy.context.view_layer.update()
        world=matrix_values(rig.matrix_world)
        maximum['armature_matrix']=max(maximum['armature_matrix'],delta(world,posed_values))
        poses={name:matrix_values(rig.matrix_world@rig.pose.bones[name].matrix) for name in bones}
        timeline.append(poses)
        for bone in rig.pose.bones:
            q=tuple(bone.rotation_quaternion)
            length=math.hypot(*q)
            require(bone.rotation_mode=='QUATERNION' and math.isfinite(length)
                    and abs(length-1)<1e-5,'NONUNIT_OR_INACTIVE_WALK_QUATERNION')
            previous=earlier_quats.get(bone.name)
            require(previous is None or _dot_quaternion(previous,q)>=0.,'WALK_QUATERNION_SIGN_DISCONTINUITY')
            earlier_quats[bone.name]=q
            if frame_index==0:
                first_quats[bone.name]=q
            if frame_index == phase.STORED_FRAMES - 1:
                require(_dot_quaternion(first_quats[bone.name],q)>=0.,'WALK_WRAPPED_QUATERNION_SIGN_DISCONTINUITY')
            maximum['bone_local_translation_m']=max(maximum['bone_local_translation_m'],bone.location.length)
            maximum['bone_local_scale_delta']=max(maximum['bone_local_scale_delta'],
                                                 max(abs(v-1.) for v in bone.scale))
        armature_timeline.append(world)
        full,visible=evaluated(bpy,human,full=True),evaluated(bpy,human)
        require((len(full),len(visible))==(19158,13380),'WRONG_WALK_SURFACE_COUNTS')
        minimum['visible_floor_m']=min(minimum['visible_floor_m'],min(p[2] for p in visible)-floor)
        minimum['whole_full_floor_m']=min(minimum['whole_full_floor_m'],min(p[2] for p in full)-floor)
        sample=phase.sample_walk(frame_index)
        require(sample.left.is_stance or sample.right.is_stance,'WALK_MISSING_GROUND_SUPPORT_PHASE')
        counts['double_stance' if sample.left.is_stance and sample.right.is_stance
               else 'left_only' if sample.left.is_stance else 'right_only']+=1
        knee=[]
        for side,foot in (('L',sample.left),('R',sample.right)):
            hip,joint,ankle=(matrix(poses[name+'.'+side]).translation
                            for name in ('upperleg01','lowerleg01','foot'))
            limb=(ankle-hip).normalized()
            bend=joint-hip
            neutral_pole=neutral_poles[side]
            observed=(bend-limb*bend.dot(limb)).normalized()
            expected=(neutral_pole-limb*neutral_pole.dot(limb)).normalized()
            alignment=observed.dot(expected)
            minimum['knee_pole_alignment']=min(minimum['knee_pole_alignment'],alignment)
            flex=math.degrees((joint-hip).angle(ankle-joint))
            knee.append(flex)
            minimum['knee_flex_deg']=min(minimum['knee_flex_deg'],flex)
            maximum['knee_flex_deg']=max(maximum['knee_flex_deg'],flex)
            target=Vector(bones['foot.'+side]['head_world'])+forward*foot.forward_m
            target.z+=foot.lift_m
            maximum['ankle_target_m']=max(maximum['ankle_target_m'],math.dist(ankle,target))
            details=measure_contact(full,regions[side],foot,sample.time_s*phase.GROUND_SPEED_M_S,
                            forward, floor, anchors[side])
            for key,value in details.items():
                if key in minimum:
                    minimum[key]=min(minimum[key],value)
                else:
                    maximum[key]=max(maximum[key],value)
                    combined='stance_'+key.split('_',1)[1]
                    maximum[combined]=max(maximum[combined],value)
        if knee_history:
            maximum['adjacent_knee_step_deg']=max(maximum['adjacent_knee_step_deg'],delta(knee,knee_history[-1]))
        knee_history.append(knee)
        latest=(_flatten(poses.values()), _flatten(full), _flatten(visible))
        turn = frame_index % phase.STRIDE_FRAMES
        if frame_index < phase.STRIDE_FRAMES:
            references[turn]=latest
        else:
            reference=references[turn]
            maximum['repeat_bone_matrix']=max(maximum['repeat_bone_matrix'],delta(reference[0],latest[0]))
            maximum['repeat_skin_coordinate_m']=max(maximum['repeat_skin_coordinate_m'],
                                                   delta(reference[1],latest[1]),delta(reference[2],latest[2]))
            if frame_index == phase.STRIDE_FRAMES:
                first_repeat=latest
    maximum['adjacent_knee_step_deg']=max(maximum['adjacent_knee_step_deg'],delta(knee_history[0],knee_history[-1]))
    require(counts=={'double_stance':60,'left_only':120,'right_only':120} and first_repeat is not None,
            'WRONG_COMPLETE_WALK_PHASE_COVERAGE')
    require(all(maximum[k]<=LIMITS[k] for k in ('armature_matrix','bone_local_translation_m',
            'bone_local_scale_delta','ankle_target_m','repeat_bone_matrix','repeat_skin_coordinate_m')),
            'SAVED_WALK_NUMERIC_POSE_EXCEEDS_BOUND')
    seam={
        'bone_matrix_phase_repeat':delta(references[0][0],first_repeat[0]),
        'full_skin_repeat_coordinate_m':delta(references[0][1],first_repeat[1]),
        'visible_skin_repeat_coordinate_m':delta(references[0][2],first_repeat[2]),
        'bone_matrix_wrap_velocity_residual_s':wrap_residual(latest[0],references[0][0],
                                                           references[29][0],first_repeat[0]),
        'full_skin_wrap_velocity_residual_m_s':wrap_residual(latest[1],references[0][1],
                                                            references[29][1],first_repeat[1]),
        'visible_skin_wrap_velocity_residual_m_s':wrap_residual(latest[2],references[0][2],
                                                               references[29][2],first_repeat[2]),
    }
    require(all(math.isfinite(v) and v<=2e-3 for v in seam.values()), 'WALK_MEASURED_SEAM_EXCEEDS_BOUND')
    zero, virtual = phase.sample_walk(0), phase.sample_walk(phase.STORED_FRAMES)
    for a,b in ((zero.left,virtual.left),(zero.right,virtual.right)):
        require(a.forward_m==b.forward_m and a.lift_m==b.lift_m
                and a.forward_velocity_m_s==b.forward_velocity_m_s and a.lift_velocity_m_s==b.lift_velocity_m_s
                and abs((b.stance_anchor_m-a.stance_anchor_m)-6.5)<1e-12,'WRONG_ANALYTIC_VIRTUAL_SEAM')
    metrics={
        'frames':300, 'curve_count':curve_count,'bones':len(bones),'evaluated_full_vertices':19158,
        'evaluated_visible_vertices':13380,'phase_counts':counts,'minimum':minimum,'maximum':maximum,
        'seam':seam, 'neutral_visible_floor_m':min(p[2] for p in neutral_visible)-floor,
        'neutral_whole_full_floor_m':min(p[2] for p in neutral_full)-floor,
        'sole_regions':{side:{'weighted_vertices':len(regions[side][1]),
                             'sole_vertices':len(regions[side][0])} for side in ('L','R')},
        'stored_clock':[1,300,30],'virtual_review_frame':301,'virtual_frame_stored':False,
    }
    return WalkSceneObservation(metrics, bones, timeline, armature_timeline, bind, posed)


def contact_gates(metrics: dict) -> dict[str, bool]:
    lo,hi=metrics['minimum'],metrics['maximum']
    return {
        'compensated_stance_anchor':hi['stance_anchor_m']<=LIMITS['stance_anchor_m'],
        'compensated_stance_drift':hi['stance_drift_m']<=LIMITS['stance_drift_m'],
        'stance_height_vs_neutral':hi['stance_height_m']<=LIMITS['stance_height_m'],
        'weighted_foot_floor':lo['weighted_floor_m']>=-LIMITS['weighted_foot_penetration_m'],
        'whole_visible_floor':lo['visible_floor_m']>=-LIMITS['visible_penetration_m'],
        'weighted_peak_swing_clearance':lo['peak_swing_clearance_m']>=LIMITS['peak_swing_floor_clearance_min_m'],
        'knee_bends_toward_neutral_pole':lo['knee_pole_alignment']>.99,
        'knee_flex':lo['knee_flex_deg']>=LIMITS['knee_flex_min_deg']
                    and hi['knee_flex_deg']<=LIMITS['knee_flex_max_deg'],
        'no_large_adjacent_knee_angle_step':hi['adjacent_knee_step_deg']<=LIMITS['max_adjacent_knee_step_deg'],
    }
