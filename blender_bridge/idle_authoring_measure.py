"""Measure the actual neutral MPFB master locally; private anatomy never enters logs."""
from blender_bridge.face_geometry import evaluated, intake, invariant_state, rest_state
from blender_bridge.face_operations import state_digest
from blender_bridge.idle_authoring_math import body_axes, hand_anatomy, sub, dot, unit
from blender_bridge.idle_authoring_policy import FRAME_PROFILE, SOURCE_PROFILE, require, finite_vector, canonical_digest
from blender_bridge.neutral_master import inspect_neutral
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import document_sha256

SEMANTIC = ('root', 'spine05', 'spine03', 'spine01', 'neck01', 'head')
SIDE = ('pelvis', 'clavicle', 'shoulder01', 'upperarm01', 'upperarm02', 'lowerarm01',
        'lowerarm02', 'wrist', 'upperleg01', 'upperleg02', 'lowerleg01', 'lowerleg02', 'foot', 'toe3-1')


def values(matrix):
    from blender_bridge.fbx_source import matrix_values
    return matrix_values(matrix)


def stable_state(bpy, human, rig, target_service):
    state = invariant_state(bpy, human, rig, target_service)
    # The sole intended change is the bone pose channels and their original Action.
    del state['pose_channels']
    return state_digest(state)


def required_names():
    return {*SEMANTIC, *(name+'.'+side for side in ('L', 'R') for name in SIDE),
            *(f'finger{digit}-{joint}.{side}' for side in ('L', 'R')
              for digit in range(1, 6) for joint in range(1, 4))}


def sole_patches(human, points, axes, height):
    result = {}
    groups = {g.index: g.name for g in human.vertex_groups}
    for side in ('L', 'R'):
        candidates = [v.index for v in human.data.vertices if any(
            g.weight > .05 and groups[g.group].endswith('.'+side)
            and groups[g.group].startswith(('foot', 'toe')) for g in v.groups)]
        require(len(candidates) >= 3, 'Idle sole patch has insufficient actual foot/toe weights')
        low = min(dot(points[i], axes['up']) for i in candidates)
        indices = [i for i in candidates if dot(points[i], axes['up']) <= low + .005*height]
        require(3 <= len(indices) <= 2048, 'Idle sole patch is degenerate or exceeds its finite limit')
        result[side] = {'indices': indices, 'neutral_world': [list(points[i]) for i in indices]}
    return result


def measure(bpy, root, project, master_sha):
    """Read only neutral state, never evaluate or load any existing Action/clip."""
    neutral = inspect_neutral(bpy, root, {'operation': 'inspect_mpfb_neutral_master',
        'input_project': 'candidate.blend', 'options': {'master_sha256': master_sha}})
    human, rig, _, targets = intake(bpy)
    require(abs(bpy.context.scene.unit_settings.scale_length - 1) < 1e-9,
            'Idle authoring supports explicit world-meter scenes only')
    for obj in (rig, human):
        values(obj.matrix_world)
        finite_vector(obj.matrix_world.to_scale())
        require(max(abs(float(x)-1) for x in obj.matrix_world.to_scale()) < 1e-5
                and abs(obj.matrix_world.to_3x3().determinant()-1) < 1e-4,
                'Idle authoring rejects scaled/reflected object transforms')
    require(required_names() <= {b.name for b in rig.data.bones}, 'Unsupported actual MPFB idle anatomy')
    require(1 <= len(rig.data.bones) <= 256 and len(rig.data.bones)*300 <= 100000,
            'Idle full-bone timeline exceeds its finite limit')
    bones = sorted(rig.data.bones, key=lambda b: (len(b.parent_recursive), b.name))
    records = [{'name': b.name, 'parent': b.parent.name if b.parent else None,
                'head_world': list(finite_vector(rig.matrix_world @ b.head_local)),
                'tail_world': list(finite_vector(rig.matrix_world @ b.tail_local)),
                'rest_local': values(b.matrix_local), 'rest_world': values(rig.matrix_world @ b.matrix_local)}
               for b in bones]
    by_name = {r['name']: r for r in records}
    point = lambda name: by_name[name]['head_world']
    pelvis = tuple((a+b)/2 for a,b in zip(point('pelvis.L'), point('pelvis.R')))
    axes = body_axes(pelvis, point('neck01'), point('upperarm01.L'), point('upperarm01.R'))
    height = sum(v*v for v in sub(point('head'), pelvis))**.5
    require(.1 < height < 3, 'Unsupported idle anatomy units/span')
    hands = {}
    for side, sign in (('L', -1), ('R', 1)):
        for child, parent in [('upperarm02', 'upperarm01'), ('lowerarm01', 'upperarm02'),
                              ('lowerarm02', 'lowerarm01'), ('wrist', 'lowerarm02')]:
            require(by_name[child+'.'+side]['parent'] == parent+'.'+side,
                    'Unsupported actual MPFB arm-helper hierarchy')
        segment = unit(sub(point('lowerarm01.'+side), point('upperarm01.'+side)))
        require(dot(segment, tuple(sign*v for v in axes['right'])) > .6,
                'Measured arm rest is incompatible with the supported lateral neutral anatomy')
        anterior = unit(sub(point('toe3-1.'+side),point('foot.'+side)))
        require(dot(anterior,axes['forward']) > .2,
                'Actual foot/toe anatomy does not corroborate the public MPFB anterior convention')
        hand = hand_anatomy(side, point('wrist.'+side), point('finger3-1.'+side),
                            point('finger2-1.'+side), point('finger5-1.'+side))
        hands[side] = {key: list(value) for key,value in hand.items()}
    target = TargetActionTarget(project.project_id, project.revision, document_sha256(project.to_dict()),
        master_sha, neutral['state_sha256'], neutral['rest_sha256']).to_dict()
    points = evaluated(bpy, human, full=True)
    topology = [{'name': r['name'], 'parent': r['parent']} for r in records]
    frame = {'schema_version': 1, 'profile': FRAME_PROFILE, 'target': target,
        'source_profile': SOURCE_PROFILE, 'skeleton_fingerprint': state_digest({'profile': SOURCE_PROFILE, 'bones': topology}),
        'anatomy': {'axes': {k: list(v) for k,v in axes.items()}, 'hands': hands, 'bones': records},
        'sole_patches': sole_patches(human, points, axes, height),
        'neutral': {'rig_name': rig.name, 'human_name': human.name, 'rig_world': values(rig.matrix_world),
            'human_world': values(human.matrix_world), 'stable_invariants_sha256': stable_state(bpy,human,rig,targets),
            'full_vertex_count': len(points), 'full_skin_sha256': neutral['full_skin_sha256'],
            'visible_skin_sha256': neutral['visible_skin_sha256'], 'weights_sha256': neutral['weights_sha256'],
            'key_state_sha256': neutral['key_state_sha256']}}
    require(state_digest(rest_state(rig)) == target['rest_sha256'], 'Idle neutral rest changed during measurement')
    return frame, human, rig, targets


def check_frame(actual, expected):
    require(type(expected) is dict and set(expected) == set(actual)
            and canonical_digest(actual) == canonical_digest(expected),
            'Actual idle target/rest/anatomical measurement differs from its bound inspection')


def reopened_objects(bpy, frame, targets):
    human = bpy.data.objects.get(frame['neutral']['human_name'])
    rig = bpy.data.objects.get(frame['neutral']['rig_name'])
    require(human is not None and human.type == 'MESH' and rig is not None and rig.type == 'ARMATURE',
            'Saved idle review lacks the original actual human/armature')
    require(len(bpy.data.libraries) == 0 and len(bpy.data.actions) == 1, 'Saved idle review has inherited libraries/Actions')
    action = rig.animation_data.action if rig.animation_data else None
    require(action is not None and action == bpy.data.actions[0], 'Saved idle review Action assignment differs')
    blocks = []
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            blocks.extend(b for b in getattr(bpy.data, prop.identifier) if isinstance(b, bpy.types.ID))
    blocks.extend(b.node_tree for b in list(blocks) if getattr(b, 'node_tree', None) is not None)
    for block in {b.as_pointer(): b for b in blocks}.values():
        animation = getattr(block, 'animation_data', None)
        require(not block.library and not block.override_library and (not animation or
            (not len(animation.drivers) and not len(animation.nla_tracks)
             and (animation.action is None or (block == rig and animation.action == action)))),
            'Saved idle review contains an unmodeled driver/NLA/Action/library')
    require(all(not len(o.constraints) for o in bpy.data.objects)
            and all(not len(b.constraints) for b in rig.pose.bones), 'Saved idle review contains constraints')
    require(state_digest(rest_state(rig)) == frame['target']['rest_sha256']
            and stable_state(bpy,human,rig,targets) == frame['neutral']['stable_invariants_sha256'],
            'Saved idle review changed original rest/skin/keys/weights/objects/materials')
    return human, rig, action
