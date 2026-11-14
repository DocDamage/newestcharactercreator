"""Reject new complete-trunk hand/body contact identities before publication."""
from dataclasses import dataclass
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.preview.central_surface import CompleteTrunkSurfaces,POLICY as SURFACE_POLICY
from .master_preview import _digest

POLICY='NO_NEW_COMPLETE_TRUNK_HAND_BODY_POLYGONS_V1'


@dataclass(frozen=True,slots=True)
class CompleteTrunkFitGuard:
    policy: str
    full_trunk_report_sha256: str
    verification_sha256: str
    frames_checked: int


def require_complete_trunk_fit_guard(review):
    full=review.full_trunk;count=review.original_playback.cache.frame_count
    if not isinstance(full,CompleteTrunkSurfaces) or full.fitted is None or review.fitted_playback is None:
        raise ValidationError('COMPLETE_TRUNK_FIT_UNAVAILABLE; original motion retained')
    for variant in (full.original,full.fitted):
        if (variant.surface.status!='CHECKED' or variant.surface.policy!=SURFACE_POLICY or
            any(len(rows)!=count for rows in (variant.surface.pairs,variant.hand_polygons,variant.body_polygons)) or
            any(len(row)!=2 for rows in (variant.surface.pairs,variant.hand_polygons,variant.body_polygons) for row in rows)):
            raise ValidationError('COMPLETE_TRUNK_FIT_COVERAGE_CHANGED; original motion retained')
    for name,digest in ((review.private_full_trunk_report,review.full_trunk_report_sha256),
                        (review.private_anatomical_verification,review.anatomical_verification_sha256)):
        path=Path(name)
        if not name or path.is_symlink() or not path.is_file() or _digest(path)!=digest:
            raise ValidationError('COMPLETE_TRUNK_FIT_EVIDENCE_CHANGED; original motion retained')
    new=tuple(i for i in range(count) if any(b-a for key in ('hand_polygons','body_polygons')
        for a,b in zip(getattr(full.original,key)[i],getattr(full.fitted,key)[i])))
    more=tuple(i for i,(a,b) in enumerate(zip(full.original.surface.pairs,full.fitted.surface.pairs))
               if any(y>x for x,y in zip(a,b)))
    if new!=full.new_area_frames or more!=full.more_hand_pair_frames:
        raise ValidationError('COMPLETE_TRUNK_FIT_COMPARISON_CHANGED; original motion retained')
    for frames,code in ((new,'COMPLETE_TRUNK_FIT_INTRODUCES_CONTACT_AREAS'),(more,'COMPLETE_TRUNK_FIT_INCREASES_HAND_PAIRS')):
        if frames:
            first=review.original_playback.cache.source_first_frame
            raise ValidationError(code+'; source frames '+', '.join(str(first+i) for i in frames[:24])+'; original motion retained')
    return CompleteTrunkFitGuard(POLICY,review.full_trunk_report_sha256,review.anatomical_verification_sha256,count)
