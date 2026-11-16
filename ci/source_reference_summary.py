"""Closed aggregate-only acceptance record; no source poses or geometry."""
STATUS = 'REAL_ORIGINAL_SOURCE_REFERENCES_HAND_EDITS_HISTORY_AND_SIX_GUARDS_PASSED'
FAULTS = frozenset({'NoAI_binding', 'assigned_action', 'tiny_pose', 'unregistered_neutral',
                   'cancel_live_neutral', 'external_revision'})
WORKERS = {'inspect_mpfb_neutral_master': 18, 'inspect_fbx_animation': 10,
           'stage_mpfb_hand_revision': 7, 'verify_mpfb_hand_revision': 7,
           'inspect_mpfb_expression_keys': 10}
FLAGS = frozenset({'original_source_only', 'source_and_originals_preserved',
    'binding_rights_retained', 'hand_and_reference_history_saved_reopened',
    'exact_original_hand_reset', 'duplicate_operations_preserve_revision_history',
    'expressions_and_strengths_preserved'})


def validate_summary(raw: object) -> dict:
    fields = FLAGS | {'status', 'source_frames', 'source_bones', 'catalog_source_workers',
        'complete_source_frame_observations', 'positive_workers', 'guards',
        'visual_quality_approved', 'engine_import_verified'}
    if type(raw) is not dict or set(raw) != fields or raw['status'] != STATUS:
        raise ValueError('Incomplete closed source-reference summary')
    if any(raw[key] is not True for key in FLAGS):
        raise ValueError('Source-reference preservation or provenance is incomplete')
    for key, expected in {'source_frames': 300, 'source_bones': 71,
            'catalog_source_workers': 2, 'complete_source_frame_observations': 3600}.items():
        if type(raw[key]) is not int or raw[key] != expected:
            raise ValueError('Incomplete full source observation coverage')
    if (type(raw['positive_workers']) is not dict or raw['positive_workers'] != WORKERS
            or any(type(v) is not int for v in raw['positive_workers'].values())):
        raise ValueError('Incomplete normal reference/hand/expression workers')
    if type(raw['guards']) is not dict or set(raw['guards']) != FAULTS or any(
            value is not True for value in raw['guards'].values()):
        raise ValueError('Incomplete actual source-reference guards')
    if raw['visual_quality_approved'] is not False or raw['engine_import_verified'] is not False:
        raise ValueError('Source references do not establish visual or engine acceptance')
    return raw
