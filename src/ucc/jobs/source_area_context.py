"""Bind a freshly reviewed original body-area baseline to candidate search."""
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256
from .master_preview import _digest


def source_area_inputs(store,ctx,review,*,cancel=None):
    areas=review.areas;path=Path(review.private_report);jobs=store.root/'.ucc-jobs'
    if (any(getattr(review,k)!=getattr(ctx.playback,k) for k in ('project_id','revision','master_sha256','source_sha256')) or
        dict(review.bindings)!=ctx.bindings or review.metadata_sha256!=_digest(store.root/'project.ucc.json',cancel) or
        review.fitted_playback is not None or review.contacts.fitted is not None or areas is None or
        areas.status!='CHECKED' or areas.reason!='' or not is_sha256(areas.polygon_sha256) or
        review.contacts.original.status!='CHECKED' or areas.contacts!=review.contacts or areas.fitted is not None or areas.original is None or
        len(areas.original)!=ctx.baseline['source_frame_count'] or
        review.original_playback.job_id!=ctx.playback.job_id or review.original_playback.cache.packed!=ctx.playback.cache.packed or
        jobs.is_symlink() or path.parent.is_symlink() or path.resolve().parent.parent!=jobs.resolve() or
        path.is_symlink() or not path.is_file() or _digest(path,cancel)!=review.report_sha256):
        raise ValidationError('COMPLETE_STABLE_BODY_AREAS_REQUIRED; source selection/evidence changed')
    return path,review.report_sha256


def validate_candidate_areas(raw,source,count,changed,pose_tests):
    fields={'policy','source_frames_verified','polygon_topology_sha256','candidate_frames_checked',
        'new_area_frames','more_hand_pair_frames','rejected_pose_observations'}
    if (type(raw) is not dict or set(raw)!=fields or raw['policy']!='NO_NEW_CENTRAL_BODY_POLYGONS_V1' or
        raw['polygon_topology_sha256']!=source.areas.polygon_sha256 or
        any(type(raw[k]) is not int for k in ('source_frames_verified','candidate_frames_checked','new_area_frames','more_hand_pair_frames','rejected_pose_observations')) or
        raw['source_frames_verified']!=count or raw['candidate_frames_checked']!=changed or raw['new_area_frames']!=0 or
        raw['more_hand_pair_frames']!=0 or not 0<=raw['rejected_pose_observations']<=pose_tests):
        raise ValidationError('Candidate lacks complete unchanged stable body-area coverage')
