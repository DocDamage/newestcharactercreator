"""Read-only exact neutral inspection; not permission to adopt or edit a master."""
from pathlib import Path

from blender_bridge.face_geometry import intake, invariant_state
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest
from blender_bridge.expression_geometry import source_state
from blender_bridge.expression_policy import PREFIX, TARGETS, keyname

OPERATION = 'inspect_mpfb_neutral_master'
POLICY = 'READ_ONLY_MPFB_EXACT_NEUTRAL_MASTER_V1'


def checked_job(job: dict) -> None:
    options = job.get('options')
    if (job.get('operation') != OPERATION or job.get('input_project') != 'candidate.blend'
            or type(options) is not dict or set(options) != {'master_sha256'}
            or type(options['master_sha256']) is not str or len(options['master_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in options['master_sha256'])):
        raise ValueError('Neutral inspection requires fixed candidate.blend and its exact SHA-256 only')


def animation_audit(bpy) -> int:
    if len(bpy.data.actions):
        raise ValueError('Neutral master contains existing Actions, including unused Actions')
    if len(bpy.data.libraries):
        raise ValueError('Neutral master contains linked libraries')
    blocks = []
    for prop in bpy.data.bl_rna.properties:
        if prop.type == 'COLLECTION':
            blocks.extend(b for b in getattr(bpy.data, prop.identifier) if isinstance(b, bpy.types.ID))
    blocks.extend(b.node_tree for b in list(blocks) if getattr(b, 'node_tree', None) is not None)
    unique = {b.as_pointer(): b for b in blocks}
    for block in unique.values():
        if block.library or block.override_library:
            raise ValueError('Neutral master contains linked or overridden data')
        animation = getattr(block, 'animation_data', None)
        if animation and (animation.action or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError('Neutral master contains animation, drivers or NLA on a loaded datablock')
    return len(unique)


def neutral_pose_and_keys(rig, human) -> int:
    if rig.data.pose_position != 'POSE':
        raise ValueError('Neutral master requires ordinary POSE evaluation')
    for bone in rig.pose.bones:
        if len(bone.constraints):
            raise ValueError('Neutral master contains bone constraints, including muted constraints')
        if any(float(bone.matrix_basis[i][j]) != float(i == j) for i in range(4) for j in range(4)):
            raise ValueError('Neutral master bone pose is not exact identity')
    keys = [k for k in human.data.shape_keys.key_blocks if k.name.startswith(PREFIX)]
    expected = {keyname(role, family) for role, family, _ in TARGETS}
    if keys and ({k.name for k in keys} != expected or any(k.value != 0. for k in keys)):
        raise ValueError('Neutral master reserved expression keys are incomplete or nonneutral')
    return len(keys)


def inspect_neutral(bpy, root: Path, job: dict) -> dict:
    checked_job(job)
    candidate = root/'candidate.blend'; expected = job['options']['master_sha256']
    if candidate.is_symlink() or not candidate.is_file() or digest(candidate) != expected:
        raise ValueError('Neutral master staged SHA-256 differs')
    if bpy.app.version[:2] != (5, 3):
        raise ValueError('Neutral master inspection requires Blender 5.3')
    bpy.ops.wm.open_mainfile(filepath=str(candidate), load_ui=False)
    blocks = animation_audit(bpy)
    human, rig, _, targets = intake(bpy)
    expression_count = neutral_pose_and_keys(rig, human)
    before = source_state(bpy, human, rig, targets)
    invariants = invariant_state(bpy, human, rig, targets)
    if (source_state(bpy, human, rig, targets) != before
            or invariant_state(bpy, human, rig, targets) != invariants
            or animation_audit(bpy) != blocks or neutral_pose_and_keys(rig, human) != expression_count
            or digest(candidate) != expected):
        raise ValueError('Read-only neutral inspection changed original source state')
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': expected,
            'blender_version': bpy.app.version_string, 'mpfb_version': '2.0.18',
            'bone_count': len(rig.pose.bones), 'full_vertex_count': 19158, 'visible_vertex_count': 13380,
            'inspected_datablocks': blocks, 'action_count': 0, 'driven_datablocks': 0, 'nla_tracks': 0,
            'bone_constraints': 0, 'exact_identity_pose_basis': True, 'expression_key_count': expression_count,
            'state_sha256': state_digest(before), 'full_skin_sha256': before['full_sha256'],
            'visible_skin_sha256': before['visible_sha256'], 'rest_sha256': before['rest_sha256'],
            'weights_sha256': invariants['weights'], 'key_state_sha256': state_digest(before['all_keys']),
            'source_state_preserved': True, 'source_provenance_verified': False,
            'project_action_admission_verified': False, 'engine_import_verified': False, 'visual_quality_approved': False}
