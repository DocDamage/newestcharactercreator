"""Reject automatic fits that trade arm clearance for new central-body areas."""
from dataclasses import dataclass
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256
from ucc.preview.body_contacts import POLICY as BODY_POLICY
from ucc.preview.contact_areas import BodyContactAreas
from .master_preview import _digest

POLICY='NO_NEW_CENTRAL_BODY_POLYGONS_V1'


@dataclass(frozen=True,slots=True)
class BodyFitGuard:
    policy: str
    body_report_sha256: str
    polygon_topology_sha256: str
    frames_checked: int


def require_body_fit_guard(review):
    areas=review.areas;contacts=review.contacts;path=Path(review.private_report)
    if (not isinstance(areas,BodyContactAreas) or areas.status!='CHECKED' or areas.contacts!=contacts or
        areas.original is None or areas.fitted is None or contacts.fitted is None or areas.reason!='' or
        not is_sha256(areas.polygon_sha256) or contacts.original.status!='CHECKED' or contacts.fitted.status!='CHECKED' or
        contacts.original.policy!=BODY_POLICY or contacts.fitted.policy!=BODY_POLICY or
        areas.new_area_frames is None or areas.more_hand_pair_frames is None or
        len(areas.original)!=len(areas.fitted) or len(areas.original)!=review.original_playback.cache.frame_count or
        len(contacts.original.pairs)!=len(areas.original) or len(contacts.fitted.pairs)!=len(areas.fitted) or
        review.fitted_playback is None or path.is_symlink() or not path.is_file() or _digest(path)!=review.report_sha256):
        raise ValidationError('BODY_FIT_AREAS_UNAVAILABLE; original motion retained')
    new=tuple(i for i,(a,b) in enumerate(zip(areas.original,areas.fitted)) if b-a)
    more=tuple(i for i,(a,b) in enumerate(zip(contacts.original.pairs,contacts.fitted.pairs)) if any(y>x for x,y in zip(a,b)))
    if new!=areas.new_area_frames or more!=areas.more_hand_pair_frames:
        raise ValidationError('BODY_FIT_AREA_COMPARISON_CHANGED; original motion retained')
    first=review.original_playback.cache.source_first_frame
    if new:
        frames=', '.join(str(first+i) for i in new[:24])
        raise ValidationError('BODY_FIT_INTRODUCES_CONTACT_AREAS; source frames '+frames+'; original motion retained')
    if more:
        frames=', '.join(str(first+i) for i in more[:24])
        raise ValidationError('BODY_FIT_INCREASES_HAND_PAIRS; source frames '+frames+'; original motion retained')
    return BodyFitGuard(POLICY,review.report_sha256,areas.polygon_sha256,len(areas.original))
