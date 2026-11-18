"""Read-only desktop completion admission; never substitutes for native proof."""
from pathlib import Path
from hashlib import sha256

from ucc.core.body_sprites import BodySpriteRequest, POLICY, validate_recipe, worker_bindings
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import CLOCK, canonical_bytes, checked_sha, checked_uuid, closed, read_document
from ucc.jobs.body_sprite_export import BodySpriteExport
from ucc.jobs.body_sprite_transactions import file_inventory
from ucc.jobs.master_preview import _digest
from ucc.jobs.target_action_context import protected
from ucc.sprites.body_evidence import atlas_side, frame_names

FALSE_FIELDS = frozenset({'material_adopted', 'project_metadata_changed',
    'source_redistribution_authorized', 'sprite_redistribution_authorized',
    'ai_input_authorized', 'cloud_transmission_authorized', 'visual_quality_approved',
    'usable_action_approved', 'engine_import_verified'})
RECEIPT_FIELDS = FALSE_FIELDS | {'schema_version', 'policy', 'request_sha256', 'bindings',
    'files', 'full_clock', 'selected_window', 'source_admission', 'source_intake_job_ids',
    'blender_stage_job_id', 'blender_reopen_job_id', 'blender_executable_sha256',
    'worker_dependencies', 'original_source_verified', 'saved_scene_rerender_verified', 'image_count'}


def verify_body_sprite_delivery(result: BodySpriteExport, request: BodySpriteRequest,
                                destination: Path, cancel=None) -> BodySpriteExport:
    """Rehash the closed delivered inventory off the GUI thread before reporting."""
    if (type(result) is not BodySpriteExport or result.destination != destination
            or result.image_count != request.image_count
            or result.selected_target_frames != request.window.target_frames
            or result.selected_source_frames != request.window.source_frames):
        raise ValidationError('Body-sprite completion differs from the selected private sample')
    root = protected(destination)
    if not root.is_dir():
        raise ValidationError('Private sprite destination is missing')
    path = protected(root/'body_sprite_receipt.json')
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValidationError('Private sprite receipt is not one ordinary file')
    with path.open('rb') as stream:
        payload = stream.read(256*1024+1)
    if (len(payload) > 256*1024 or sha256(payload).hexdigest() != result.receipt_sha256
            or _digest(path, cancel) != result.receipt_sha256):
        raise ValidationError('Private sprite receipt changed or exceeds its metadata limit')
    receipt = closed(read_document(payload), RECEIPT_FIELDS)
    if (receipt['schema_version'] != 1 or type(receipt['schema_version']) is not int
            or receipt['policy'] != POLICY or receipt['request_sha256'] != request.sha256
            or canonical_bytes(receipt['full_clock']) != canonical_bytes(dict(CLOCK))
            or canonical_bytes(receipt['selected_window']) != canonical_bytes(request.window.to_dict())
            or type(receipt['image_count']) is not int or receipt['image_count'] != request.image_count
            or receipt['original_source_verified'] is not True
            or receipt['saved_scene_rerender_verified'] is not True
            or any(receipt[key] is not False for key in FALSE_FIELDS)):
        raise ValidationError('Private sprite receipt scope or approval flags differ from the request')
    ids = receipt['source_intake_job_ids']
    if (type(ids) is not list or len(ids) != 2 or tuple(ids) != result.source_intake_job_ids
            or receipt['blender_stage_job_id'] != result.stage_job_id
            or receipt['blender_reopen_job_id'] != result.reopen_job_id):
        raise ValidationError('Private sprite receipt worker identities differ from the completed operation')
    all_ids = [*ids, result.stage_job_id, result.reopen_job_id]
    for value in all_ids:
        checked_uuid(value)
    old_ids = set(request.target_binding.producer.worker_job_ids)
    if len(set(all_ids)) != 4 or set(all_ids) & old_ids:
        raise ValidationError('Private sprite rendering must retain four fresh worker identities')
    bindings = receipt['bindings']
    if type(bindings) is not dict or set(bindings) != set(worker_bindings(request, '0'*64)) | {'scene_sha256','stage_sha256'}:
        raise ValidationError('Private sprite receipt bindings are incomplete')
    for digest in bindings.values():
        checked_sha(digest)
    if bindings != {**worker_bindings(request, bindings['recipe_sha256']),
                    'scene_sha256': bindings['scene_sha256'], 'stage_sha256': bindings['stage_sha256']}:
        raise ValidationError('Private sprite receipt lost its selected saved binding')
    files = receipt['files']
    if type(files) is not dict:
        raise ValidationError('Private sprite receipt inventory is missing')
    tiles_per_side = atlas_side(request)//request.settings.resolution
    sheet_capacity = tiles_per_side**2
    sheets = (request.image_count+sheet_capacity-1)//sheet_capacity
    expected = {*frame_names(request), 'body_sprite_recipe.json', 'body_sprite_stage.json',
                'body_sprite_verification.json', 'sprite_atlas.json', 'README.txt',
                *(f'sprite_sheet_{index:03d}.png' for index in range(sheets))}
    if set(files) != expected:
        raise ValidationError('Private sprite receipt contains unexpected or missing delivered files')
    for digest in files.values():
        checked_sha(digest)
    if file_inventory(root, {*files, path.name}, cancel) != {**files, path.name: result.receipt_sha256}:
        raise ValidationError('Private sprite delivered files changed after backend completion')
    if files['body_sprite_recipe.json'] != bindings['recipe_sha256'] or files['body_sprite_stage.json'] != bindings['stage_sha256']:
        raise ValidationError('Private sprite receipt report hashes differ from its worker bindings')
    recipe_path = root/'body_sprite_recipe.json'
    with recipe_path.open('rb') as stream:
        recipe_payload = stream.read(256*1024+1)
    if len(recipe_payload) > 256*1024 or sha256(recipe_payload).hexdigest() != files['body_sprite_recipe.json']:
        raise ValidationError('Private sprite recipe changed or exceeds its metadata limit')
    recipe = validate_recipe(read_document(recipe_payload))
    if (canonical_bytes(recipe['request']) != canonical_bytes(request.to_dict())
            or canonical_bytes(recipe['source_admission']) != canonical_bytes(receipt['source_admission'])
            or recipe['source_admission']['worker_job_ids'] != ids):
        raise ValidationError('Private sprite receipt differs from the source admission and exact requested recipe')
    checked_sha(receipt['blender_executable_sha256'])
    if receipt['blender_executable_sha256'] != request.target_binding.producer.blender_executable_sha256:
        raise ValidationError('Private sprite receipt differs from the selected saved Blender identity')
    dependencies = receipt['worker_dependencies']
    if type(dependencies) is not dict or not 1 <= len(dependencies) <= 256:
        raise ValidationError('Private sprite receipt lacks bounded worker dependencies')
    for name, digest in dependencies.items():
        if type(name) is not str or not 1 <= len(name) <= 8192:
            raise ValidationError('Private sprite worker dependency identity is malformed')
        checked_sha(digest)
    return result
