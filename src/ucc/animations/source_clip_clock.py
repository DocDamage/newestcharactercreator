"""Stored measured source timing; no fresh bytes, playback or rights approval."""
from dataclasses import dataclass
import math

from ucc.animations.metadata import AnimationMetadataError


@dataclass(frozen=True, slots=True)
class SourceClipClock:
    source_first_frame: int
    source_last_frame: int
    frame_count: int
    fps: float

    def __post_init__(self) -> None:
        if (any(type(value) is not int for value in
                (self.source_first_frame, self.source_last_frame, self.frame_count))
                or max(abs(self.source_first_frame), abs(self.source_last_frame)) > 100_000
                or not 2 <= self.frame_count == self.source_last_frame-self.source_first_frame+1 <= 2400
                or type(self.fps) not in (int, float) or not 1 <= self.fps <= 240
                or not math.isfinite(self.fps)):
            raise AnimationMetadataError('Invalid measured source clock')

    @property
    def sample_span_s(self) -> float:
        return (self.source_last_frame-self.source_first_frame)/self.fps

    @property
    def nominal_coverage_s(self) -> float:
        return self.frame_count/self.fps

    def source_frame_at_index(self, index: int) -> int:
        """Map a zero-based full-source sample index without shifting the source."""
        if type(index) is not int or not 0 <= index < self.frame_count:
            raise AnimationMetadataError('Source sample index is outside the measured clip')
        return self.source_first_frame+index

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'source_first_frame': self.source_first_frame,
                'source_last_frame': self.source_last_frame, 'frame_count': self.frame_count,
                'fps': self.fps, 'sample_span_s': self.sample_span_s,
                'nominal_coverage_s': self.nominal_coverage_s,
                'evidence_scope': 'STORED_MEASURED_SOURCE_METADATA_ONLY'}
