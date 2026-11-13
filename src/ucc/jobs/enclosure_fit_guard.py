"""Reject a fitted result that introduces buried or uncertain hand polygons."""
from dataclasses import dataclass
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.preview.central_enclosure import CentralEnclosure
from .master_preview import _digest

POLICY='NO_NEW_TRUNK_ENCLOSED_OR_UNCERTAIN_HAND_POLYGONS_V1'


@dataclass(frozen=True,slots=True)
class EnclosureFitGuard:
    policy: str
    enclosure_report_sha256: str
    verification_sha256: str
    frames_checked: int


def require_enclosure_fit_guard(review):
    enclosure=review.enclosure
    if (not isinstance(enclosure,CentralEnclosure) or enclosure.fitted is None or review.fitted_playback is None or
        any(len(getattr(variant,key))!=review.original_playback.cache.frame_count
            for variant in (enclosure.original,enclosure.fitted) for key in ('inside','ambiguous'))):
        raise ValidationError('ENCLOSURE_FIT_UNAVAILABLE; original motion retained')
    for name,digest in ((review.private_enclosure_report,review.enclosure_report_sha256),
                        (review.private_anatomical_verification,review.anatomical_verification_sha256)):
        path=Path(name)
        if not name or path.is_symlink() or not path.is_file() or _digest(path)!=digest:
            raise ValidationError('ENCLOSURE_FIT_EVIDENCE_CHANGED; original motion retained')
    for key,code in (('inside','ENCLOSURE_FIT_INTRODUCES_BURIED_SKIN'),('ambiguous','ENCLOSURE_FIT_INTRODUCES_UNCERTAINTY')):
        for frame,(source,fitted) in enumerate(zip(getattr(enclosure.original,key),getattr(enclosure.fitted,key))):
            if len(source)!=2 or len(fitted)!=2 or any(b-a for a,b in zip(source,fitted)):
                raise ValidationError(code+'; source frame '+str(review.original_playback.cache.source_first_frame+frame)+'; original motion retained')
    return EnclosureFitGuard(POLICY,review.enclosure_report_sha256,review.anatomical_verification_sha256,
                             review.original_playback.cache.frame_count)
