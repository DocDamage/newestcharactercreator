"""Prepare and independently reopen one registered Unreal FBX take in Blender."""

from pathlib import Path

from blender_bridge.godot_outputs import write_json
from blender_bridge.godot_runtime_source import character_state
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import digest
from blender_bridge.unity_animation_workers import (
    _bind_donor, _check_fbx, _check_inputs, _context, _correction_inputs, _file, _references, _unused,
)
from blender_bridge.unity_source_reference import animated_reference
from blender_bridge.unreal_animation_take import export_animated_fbx
from blender_bridge.unreal_fbx_metadata import validate_portable_header
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_animation_recipe import (
    BIND, FBX, FBX_SNAPSHOT, OUTPUT_LIMITS, POLICY, REFERENCES, STAGE, STAGE_REPORT, VERIFY_REPORT,
    output_option, source_report, validate_binding, validate_job,
)


WORLD_BONES = 'unreal_animated_world_bones.f32'
AXIS_AND_UNIT_SETTINGS = {
    b'UpAxis': 2, b'UpAxisSign': 1, b'FrontAxis': 0, b'FrontAxisSign': 1, b'CoordAxis': 1,
    b'CoordAxisSign': 1, b'UnitScaleFactor': 100.0, b'OriginalUnitScaleFactor': 100.0,
}


def _check_export_profile(path: Path) -> None:
    from io_scene_fbx.parse_fbx import parse

    root, _version = parse(str(path))
    validate_portable_header(root)
    settings, = (node for node in root.elems if node.id == b'GlobalSettings')
    properties, = (node for node in settings.elems if node.id == b'Properties70')
    axis = [node for node in properties.elems if node.id == b'P' and node.props[0] in AXIS_AND_UNIT_SETTINGS]
    objects, = (node for node in root.elems if node.id == b'Objects')
    takes = sum(node.id == b'AnimationStack' for node in objects.elems)
    if (len(axis) != len(AXIS_AND_UNIT_SETTINGS)
            or {node.props[0]: node.props[-1] for node in axis} != AXIS_AND_UNIT_SETTINGS or takes != 1):
        raise ValueError('Unreal animated FBX must use the exact centimetre axes and one take')


def _bind_reference(bpy, donor, rig, options: dict) -> dict:
    bind, _ = animated_reference(bpy, donor, rig, master_sha=options['master_sha256'],
                                 request_sha=options['target_binding_sha256'])
    bind['policy'] = 'UCC_UNREAL_ANIMATED_BIND_REFERENCE_V1'
    return bind


def _registered_context(bpy, root: Path, job: dict):
    return _context(bpy, root, job, validate_worker_job=validate_job, validate_target_binding=validate_binding)


def stage(bpy, root: Path, job: dict) -> dict:
    _unused(root, OUTPUT_LIMITS)
    options, state, native_options = _registered_context(bpy, root, job)
    human, rig, _, references = _references(bpy, root, native_options, state, write=True, references=REFERENCES)
    references.update(_correction_inputs(bpy, root, human, rig, write=True))
    with _bind_donor(bpy, human) as donor:
        write_json(root/BIND, _bind_reference(bpy, donor, rig, options))
        export_animated_fbx(bpy, donor, rig, root/FBX)
    if character_state(bpy, human, rig) != state:
        raise ValueError('Registered Unreal take changed the original source state')
    files = {name: _file(root/name, maximum, references.get(name)) for name, maximum in OUTPUT_LIMITS.items()
             if name != STAGE_REPORT}
    _check_export_profile(root/FBX)
    write_json(root/STAGE_REPORT, source_report(options, files))
    _check_inputs(root, options)
    return {'policy': POLICY, 'files': {**files, STAGE_REPORT: digest(root/STAGE_REPORT)},
            'engine_import_verified': False}


def verify(bpy, root: Path, job: dict) -> dict:
    _unused(root, (VERIFY_REPORT, FBX_SNAPSHOT))
    options, state, native_options = _registered_context(bpy, root, job)
    files = {name: _file(root/name, maximum, options[output_option(name)])
             for name, maximum in OUTPUT_LIMITS.items()}
    human, rig, _, references = _references(bpy, root, native_options, state, write=False, references=REFERENCES)
    references.update(_correction_inputs(bpy, root, human, rig, write=False))
    if any(files[name] != expected or (root/name).stat().st_size != OUTPUT_LIMITS[name]
           for name, expected in references.items()):
        raise ValueError('Registered Unreal reference streams differ after native source reopen')
    with _bind_donor(bpy, human) as donor:
        bind = _bind_reference(bpy, donor, rig, options)
    expected_stage = source_report(options, {name: value for name, value in files.items() if name != STAGE_REPORT})
    for name, expected in ((BIND, bind), (STAGE_REPORT, expected_stage)):
        if canonical_bytes(read_json(root/name, files[name], OUTPUT_LIMITS[name])) != canonical_bytes(expected):
            raise ValueError('Unreal staged bind or source provenance differs from fresh reopening')
    _check_export_profile(root/FBX)
    snapshot = _check_fbx(bpy, root, bind, files[FBX], fbx=FBX, readback=FBX_SNAPSHOT,
                          world_bones=WORLD_BONES, engine='Unreal')
    for name, expected in files.items():
        _file(root/name, OUTPUT_LIMITS[name], expected)
    _check_inputs(root, options)
    write_json(root/VERIFY_REPORT, source_report(options, files, fbx_readback_sha256=snapshot))
    return {'policy': POLICY, 'verification_sha256': digest(root/VERIFY_REPORT), 'fbx_readback_sha256': snapshot,
            'files': files, 'engine_import_verified': False}


def run(bpy, root: Path, job: dict) -> dict:
    validate_job(job['operation'], job['input_project'], job['options'])
    return (stage if job['operation'] == STAGE else verify)(bpy, root, job)
