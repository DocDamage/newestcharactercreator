"""Synthetic receipt-only fixture; NEVER a model, bone or Blender proof."""
from hashlib import sha256
from pathlib import Path

from ucc.export.godot_blender_recipe import POLICY
from ucc.export.godot_candidate_contract import canonical_bytes


def unit_producer_receipts(folder: Path, request) -> tuple[dict, dict]:
    recipe = {'policy':POLICY, 'source_bindings':dict(request.source_bindings),
        'permissions':[item.to_dict() for item in request.permissions],
        'project':{'project_id':request.project_id,'revision':request.revision,
                   'project_file_sha256':request.project_file_sha256}}
    payloads = {'source_review.blend':b'UNIT_NOT_BLENDER_DATA', 'source_bones.bin':b'\0'*(25*163*16*4),
                'source_action.json':b'{"unit_only":true}', 'export_recipe.json':canonical_bytes(recipe),
                'expression_clip.json':b'{"unit_only":true}'}
    for name, data in payloads.items(): (folder/name).write_bytes(data)
    hashes = {name:sha256(data).hexdigest() for name,data in payloads.items()}
    fields = {'source_review.blend':'review_scene_sha256','source_bones.bin':'source_bones_sha256',
              'source_action.json':'source_action_sha256','export_recipe.json':'export_recipe_sha256',
              'expression_clip.json':'clip_sha256'}
    motion = next(sha for name,sha in request.source_bindings if name.startswith('motion:'))
    report = {'producer_policy':POLICY,'source_motion_sha256':motion,
              **{field:hashes[name] for name,field in fields.items()}}
    verification = {'producer_policy':POLICY,'master_sha256':request.master_sha256,
        'source_motion_sha256':motion, 'export_recipe_sha256':hashes['export_recipe.json'],
        'bound_files':{**hashes,'blender_stage.json':dict(request.files)['blender_stage.json']},
        'frames':[{'frame':i,'master_source_error_m':0.,'bone_world_error':0.} for i in range(1,26)]}
    return report,verification
