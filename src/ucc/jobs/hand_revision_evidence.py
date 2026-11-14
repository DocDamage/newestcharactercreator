"""Validate closed scalar evidence from the independent hand revision workers."""
from ucc.core.hand_parts import POLICY,canonical_digest,is_sha256
from .geometry_evidence import EvidenceError


def validate_revision_evidence(stage,proof,options,scene_sha):
    common={'schema_version','policy','manifest_sha256','source_master_sha256','original_master_sha256',
            'current_selection','selection','scene_sha256','observation_sha256','selection_changed',
            'visual_quality_approved','penetration_quality_approved','engine_import_verified'}
    if (type(stage) is not dict or set(stage) != common|{'blender_version'}
            or type(proof) is not dict or set(proof) != common|{
                'verified_reopen','skin_poses','all40_restores_exact'}):
        raise EvidenceError('Hand revision lacks complete two-worker evidence')
    expected={'schema_version':1,'policy':POLICY,'manifest_sha256':options['manifest_sha256'],
              'source_master_sha256':options['master_sha256'],'original_master_sha256':options['original_master_sha256'],
              'current_selection':options['current_selection'],'selection':options['selection'],
              'scene_sha256':scene_sha,'observation_sha256':stage['observation_sha256'],
              'selection_changed':options['selection'] != options['current_selection'],
              'visual_quality_approved':False,'penetration_quality_approved':False,'engine_import_verified':False}
    if not is_sha256(expected['observation_sha256']):
        raise EvidenceError('Hand revision lacks an observed scene identity')
    for record in (stage,proof):
        if canonical_digest({k:record[k] for k in common}) != canonical_digest(expected):
            raise EvidenceError('Hand revision evidence differs from exact source/library/selection bindings')
    if (type(stage['blender_version']) is not str or not stage['blender_version'].startswith('5.3.')
            or proof['verified_reopen'] is not True or proof['all40_restores_exact'] is not True):
        raise EvidenceError('Hand revision lacks actual independent reopening/restoration checks')
    rows=proof['skin_poses'];seen=set()
    poses={(name,axis,angle) for name,axes in [('wrist.L',(0,1,2)),
           *[(f'finger{i}-1.L',(0,)) for i in range(1,6)],('finger2-2.L',(0,)),('finger5-2.L',(0,))]
           for axis in axes for angle in (-20,20)}
    fields={'bone','axis','degrees','skin_sha256','normals_sha256','moved_vertices_over_1um',
            'maximum_displacement','potential_hand_body_overlaps','potential_hand_self_overlaps'}
    if type(rows) is not list or len(rows) != 20:
        raise EvidenceError('Hand revision lacks all20 saved-surface pose observations')
    for row in rows:
        if (type(row) is not dict or set(row) != fields or type(row['bone']) is not str
                or type(row['axis']) is not int or type(row['degrees']) is not int
                or not is_sha256(row['skin_sha256']) or not is_sha256(row['normals_sha256'])
                or type(row['moved_vertices_over_1um']) is not int or not 16<=row['moved_vertices_over_1um']<=13380
                or type(row['maximum_displacement']) is not float or not 1e-6<row['maximum_displacement']<.5
                or any(type(row[k]) is not int or not 0<=row[k]<=100000000 for k in
                       ('potential_hand_body_overlaps','potential_hand_self_overlaps'))):
            raise EvidenceError('Invalid full-skin hand pose/shading/overlap observation')
        seen.add((row['bone'],row['axis'],row['degrees']))
    if seen != poses:
        raise EvidenceError('Hand revision pose coverage duplicates or omits required controls')
    if options['selection'] == 'neutral' and scene_sha != options['original_master_sha256']:
        raise EvidenceError('Hand reset did not restore original master bytes')
    return {**expected,'verified_reopen':True,'actual_skin_pose_checks':40,
            'potential_overlap_poses':sum(r['potential_hand_body_overlaps']>0 or r['potential_hand_self_overlaps']>0 for r in rows)}
