"""Bind a derived Blender review scene to its original selected Action source."""
import math
from pathlib import Path
from threading import Event

from ucc.core.errors import ValidationError
from ucc.export.godot_blender_recipe import POLICY
from ucc.export.godot_candidate_contract import GodotCandidateRequest
from .master_preview import _digest

EXTRA_LIMITS = {'source_review.blend': 512*1024*1024, 'source_bones.bin': 25*163*16*4,
                'source_action.json': 8*1024*1024, 'export_recipe.json': 256*1024,
                'expression_clip.json': 256*1024}


def evidence_folder(folder: Path) -> Path:
    """Godot must not automatically import private Blender evidence."""
    nested = folder/'.ucc-source-evidence'
    return nested if nested.exists() or nested.is_symlink() else folder


def validate_producer_chain(folder: Path, request: GodotCandidateRequest, report: dict,
                            verification: dict, cancel: Event | None) -> None:
    from .godot_candidate_inputs import read_json, regular_file
    folder = evidence_folder(folder)
    motion = [sha for name, sha in request.source_bindings if name.startswith('motion:')]
    if len(motion) != 1:
        raise ValidationError('Producer needs one exact original Action source')
    bindings = verification.get('bound_files', {})
    if (type(bindings) is not dict or verification.get('producer_policy') != POLICY or report.get('producer_policy') != POLICY
            or verification.get('master_sha256') != request.master_sha256
            or verification.get('source_motion_sha256') != motion[0]
            or report.get('source_motion_sha256') != motion[0]
            or verification.get('export_recipe_sha256') != report.get('export_recipe_sha256')
            or bindings.get('blender_stage.json') != dict(request.files)['blender_stage.json']):
        raise ValidationError('Derived Blender candidate lost original master, Action or recipe binding')
    fields = {'source_review.blend':'review_scene_sha256', 'source_bones.bin':'source_bones_sha256',
              'source_action.json':'source_action_sha256', 'export_recipe.json':'export_recipe_sha256',
              'expression_clip.json':'clip_sha256'}
    for name, field in fields.items():
        path = regular_file(folder/name, folder, EXTRA_LIMITS[name])
        actual = _digest(path, cancel)
        if actual != report.get(field) or (name in bindings and bindings[name] != actual):
            raise ValidationError('Derived Blender producer evidence changed: '+name)
        if name in {'source_review.blend', 'source_bones.bin', 'source_action.json'} and bindings.get(name) != actual:
            raise ValidationError('Fresh Blender reopen did not bind producer evidence: '+name)
    recipe = read_json(folder/'export_recipe.json', EXTRA_LIMITS['export_recipe.json'])
    project = recipe.get('project')
    if (type(project) is not dict or recipe.get('policy') != POLICY or recipe.get('source_bindings') != dict(request.source_bindings)
            or recipe.get('permissions') != [item.to_dict() for item in request.permissions]
            or project.get('project_id') != request.project_id
            or project.get('revision') != request.revision
            or project.get('project_file_sha256') != request.project_file_sha256):
        raise ValidationError('Producer recipe differs from admitted project or per-input engine permission')
    if (folder/'source_bones.bin').stat().st_size != EXTRA_LIMITS['source_bones.bin']:
        raise ValidationError('Producer bone reference is incomplete')
    for row in verification.get('frames', []):
        for field in ('master_source_error_m', 'bone_world_error'):
            value = row.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e-6:
                raise ValidationError('Producer original surface/bone reopening exceeds its fixed tolerance')
