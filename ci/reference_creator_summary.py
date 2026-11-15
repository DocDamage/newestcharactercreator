"""Closed aggregate-only creator evidence; never retain paths, poses or geometry."""
STATUS = 'REAL_ORIGINAL_REFERENCED_CREATOR_EDITS_HISTORY_EXPRESSIONS_AND_SIXTEEN_GUARDS_PASSED'
FLAGS = frozenset({'original_source_only', 'originals_and_installed_inputs_preserved',
    'source_bindings_and_NoAI_preserved', 'exact_master_history_saved_reopened',
    'hand_instance_selection_and_strengths_retained', 'no_op_preserves_metadata_history',
    'complete_expression_frames_decoded', 'preview_owner_and_master_unchanged'})
GUARDS = frozenset({'master_NoAI', 'master_assigned_action', 'master_unregistered_neutral',
    'master_cancel_after_face', 'master_external_after_face', 'preview_NoAI',
    'preview_assigned_action', 'preview_unregistered_neutral', 'preview_pending_body',
    'preview_cancel_live_clip', 'preview_external_live_clip', 'preview_changed_source',
    'preview_rehashed_receipt', 'preview_damaged_skin_cache', 'preview_same_worker',
    'preview_WAL_policy'})
WORKERS = {
    'master_hand': {'inspect_fbx_animation': 8, 'inspect_mpfb_neutral_master': 14,
        'inspect_mpfb_expression_keys': 30, 'verify_mpfb_hand_revision': 14,
        'stage_mpfb_hand_revision': 14, 'stage_mpfb_face': 5, 'verify_mpfb_face': 5,
        'verify_mpfb_hand_assets': 3, 'build_mpfb_hand_assets': 3, 'inspect_character': 2,
        'verify_mpfb_expression_keys': 1, 'stage_mpfb_expression_keys': 1,
        'create_human': 1, 'refit_human': 1},
    'master_nohand': {'inspect_mpfb_neutral_master': 8, 'inspect_fbx_animation': 4,
        'inspect_mpfb_expression_keys': 12, 'stage_mpfb_face': 3, 'inspect_character': 1,
        'verify_mpfb_face': 3, 'refit_human': 1},
    'preview_hand': {'inspect_fbx_animation': 2, 'inspect_mpfb_neutral_master': 2,
        'inspect_mpfb_expression_keys': 2, 'verify_mpfb_expression_clip': 1,
        'stage_mpfb_expression_clip': 1, 'stage_mpfb_hand_revision': 1,
        'inspect_character': 2, 'verify_mpfb_hand_revision': 1},
    'preview_nohand': {'inspect_fbx_animation': 2, 'inspect_mpfb_neutral_master': 2,
        'inspect_mpfb_expression_keys': 2, 'stage_mpfb_expression_clip': 1,
        'inspect_character': 2, 'verify_mpfb_expression_clip': 1}}
COUNTS = {'source_frames': 300, 'source_bones': 71, 'setup_source_workers': 6,
    'setup_source_frame_observations': 1800, 'positive_source_frame_observations': 4800,
    'changed_master_transactions': 5, 'verified_noop_transactions': 1,
    'decoded_expression_frames': 50, 'expression_vertices': 13380, 'expression_triangles': 26756}


def validate_summary(raw: object) -> dict:
    fields = FLAGS | set(COUNTS) | {'status', 'positive_workers', 'guards',
        'visual_quality_approved', 'engine_import_verified'}
    if type(raw) is not dict or set(raw) != fields or raw['status'] != STATUS:
        raise ValueError('Incomplete closed reference-creator summary')
    if any(raw[key] is not True for key in FLAGS):
        raise ValueError('Creator preservation or complete playback evidence missing')
    if any(type(raw[key]) is not int or raw[key] != count for key, count in COUNTS.items()):
        raise ValueError('Incomplete source, transaction or cache coverage')
    actual = raw['positive_workers']
    if type(actual) is not dict or set(actual) != set(WORKERS):
        raise ValueError('Missing creator worker groups')
    for group, counts in WORKERS.items():
        if (type(actual[group]) is not dict or actual[group] != counts
                or any(type(v) is not int for v in actual[group].values())):
            raise ValueError('Incomplete actual creator workers')
    if (type(raw['guards']) is not dict or set(raw['guards']) != GUARDS
            or any(value is not True for value in raw['guards'].values())):
        raise ValueError('Incomplete real creator rejection guards')
    if raw['visual_quality_approved'] is not False or raw['engine_import_verified'] is not False:
        raise ValueError('Creator CI does not grant visual or engine approval')
    return raw
