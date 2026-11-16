"""Closed aggregate only; no source paths, poses, scenes or mesh data."""
STATUS = 'REAL_ORIGINAL_PLAIN_REFERENCE_SIX_EDITS_TWO_NOOPS_THIRTEEN_GUARDS_PASSED'
FLAGS = frozenset({'original_source_only', 'originals_and_installed_inputs_preserved',
    'source_bindings_and_NoAI_preserved', 'exact_master_history_saved_reopened',
    'hand_instance_and_selection_retained', 'no_op_preserves_metadata_history',
    'paired_physical_body_readbacks', 'expression_controls_not_introduced'})
WORKERS = {'hand-0-face_revision': {'inspect_fbx_animation': 2,
                          'inspect_mpfb_neutral_master': 4,
                          'stage_mpfb_face': 1,
                          'inspect_character': 4,
                          'verify_mpfb_face': 1,
                          'verify_mpfb_hand_assets': 1,
                          'stage_mpfb_hand_revision': 2,
                          'verify_mpfb_hand_revision': 2,
                          'build_mpfb_hand_assets': 1},
 'hand-1-body_refit': {'inspect_mpfb_neutral_master': 4,
                       'inspect_fbx_animation': 2,
                       'inspect_character': 3,
                       'build_mpfb_hand_assets': 1,
                       'verify_mpfb_hand_assets': 1,
                       'stage_mpfb_hand_revision': 2,
                       'verify_mpfb_hand_revision': 2,
                       'verify_mpfb_face': 2,
                       'stage_mpfb_face': 2,
                       'refit_human': 1},
 'hand-2-body_generation': {'inspect_mpfb_neutral_master': 4,
                            'inspect_fbx_animation': 2,
                            'stage_mpfb_hand_revision': 2,
                            'verify_mpfb_hand_revision': 2,
                            'build_mpfb_hand_assets': 1,
                            'inspect_character': 3,
                            'verify_mpfb_hand_assets': 1,
                            'verify_mpfb_face': 1,
                            'stage_mpfb_face': 1,
                            'create_human': 1},
 'hand-3-face_revision': {'inspect_fbx_animation': 2,
                          'inspect_mpfb_neutral_master': 2,
                          'verify_mpfb_face': 1,
                          'inspect_character': 2,
                          'stage_mpfb_face': 1,
                          'stage_mpfb_hand_revision': 1,
                          'verify_mpfb_hand_revision': 1},
 'nohand-0-face_revision': {'inspect_fbx_animation': 2,
                            'inspect_mpfb_neutral_master': 4,
                            'inspect_character': 4,
                            'verify_mpfb_face': 1,
                            'stage_mpfb_face': 1},
 'nohand-1-body_refit': {'inspect_fbx_animation': 2,
                         'inspect_mpfb_neutral_master': 4,
                         'inspect_character': 3,
                         'stage_mpfb_face': 2,
                         'refit_human': 1,
                         'verify_mpfb_face': 2},
 'nohand-2-body_generation': {'inspect_fbx_animation': 2,
                              'inspect_mpfb_neutral_master': 4,
                              'inspect_character': 3,
                              'verify_mpfb_face': 1,
                              'create_human': 1,
                              'stage_mpfb_face': 1},
 'nohand-3-face_revision': {'inspect_fbx_animation': 2,
                            'inspect_mpfb_neutral_master': 2,
                            'inspect_character': 2,
                            'stage_mpfb_face': 1,
                            'verify_mpfb_face': 1}}
GUARDS = frozenset(['hand_NoAI',
 'hand_assigned_action',
 'hand_tiny_pose',
 'hand_pending_body',
 'hand_unregistered_neutral',
 'nohand_NoAI',
 'nohand_assigned_action',
 'nohand_tiny_pose',
 'nohand_pending_body',
 'live_cancel_after_face',
 'live_external_after_face',
 'late_rehashed_pointer',
 'late_WAL_policy'])
COUNTS = {'source_frames': 300, 'source_bones': 71,
    'setup_source_workers': 6, 'setup_source_frame_observations': 1800,
    'positive_source_frame_observations': 4800, 'changed_master_transactions': 6,
    'verified_noop_transactions': 2}


def validate_summary(raw: object) -> dict:
    fields = FLAGS | set(COUNTS) | {'status', 'positive_workers', 'guards',
        'visual_quality_approved', 'engine_import_verified'}
    if type(raw) is not dict or set(raw) != fields or raw['status'] != STATUS:
        raise ValueError('Incomplete closed plain-reference summary')
    if any(raw[key] is not True for key in FLAGS):
        raise ValueError('Plain reference preservation evidence missing')
    if any(type(raw[key]) is not int or raw[key] != count for key, count in COUNTS.items()):
        raise ValueError('Incomplete original source or transaction coverage')
    actual = raw['positive_workers']
    if type(actual) is not dict or set(actual) != set(WORKERS):
        raise ValueError('Missing plain-reference transaction')
    for case, counts in WORKERS.items():
        if (type(actual[case]) is not dict or actual[case] != counts
                or any(type(v) is not int for v in actual[case].values())):
            raise ValueError('Incomplete actual plain-reference workers')
    if (type(raw['guards']) is not dict or set(raw['guards']) != GUARDS
            or any(value is not True for value in raw['guards'].values())):
        raise ValueError('Incomplete actual plain-reference guards')
    if raw['visual_quality_approved'] is not False or raw['engine_import_verified'] is not False:
        raise ValueError('Plain-reference CI grants no visual or engine approval')
    return raw
