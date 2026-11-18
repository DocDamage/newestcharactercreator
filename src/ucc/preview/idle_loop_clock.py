"""Fractional transport for one explicit full-cache authored idle preview."""

from dataclasses import dataclass
import math

from .playback_window import FPS, FRAME_COUNT


PERIOD_S = FRAME_COUNT / FPS


@dataclass(frozen=True, slots=True)
class LoopSample:
    """Two adjacent original cache samples and their interpolation weight."""

    left_index: int
    right_index: int
    alpha: float

    def __post_init__(self) -> None:
        if (type(self.left_index) is not int or not 0 <= self.left_index < FRAME_COUNT
                or type(self.right_index) is not int or self.right_index != (self.left_index+1) % FRAME_COUNT
                or type(self.alpha) not in (int, float) or not 0 <= self.alpha < 1):
            raise ValueError('Idle playback requires adjacent original samples and a finite blend in [0, 1)')


class IdleLoopClock:
    """A ten-second local loop over the existing 300 samples at 30 Hz."""

    __slots__ = ('_sample', '_phase', '_origin', '_playing', '_start', '_last_now')
    count = FRAME_COUNT
    fps = FPS

    def __init__(self) -> None:
        self._sample = LoopSample(0, 1, 0.)
        self._phase = self._origin = self._start = 0.
        self._playing = False
        self._last_now = None

    @property
    def sample(self) -> LoopSample:
        return self._sample

    @property
    def frame(self) -> int:
        return self._sample.left_index

    @property
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, value: bool) -> None:
        # MotionViewer's existing failure handling may stop the clock directly.
        if value is not False:
            raise ValueError('Use play(now) to start the idle loop')
        self._playing = False

    def _time(self, now: float) -> float:
        if type(now) not in (int, float):
            raise ValueError('Idle playback time must be finite and monotonic')
        try:
            value = float(now)
        except OverflowError as error:
            raise ValueError('Idle playback time must be finite and monotonic') from error
        if not math.isfinite(value) or (self._last_now is not None and value < self._last_now):
            raise ValueError('Idle playback time must be finite and monotonic')
        return value

    def _set_phase(self, phase: float) -> None:
        self._phase = phase
        left = math.floor(phase)
        self._sample = LoopSample(left, (left+1) % FRAME_COUNT, phase-left)

    def seek(self, frame: int, now: float) -> None:
        if type(frame) is not int or not 0 <= frame < FRAME_COUNT:
            raise ValueError('Idle playback frame lies outside the complete original cache')
        self._start = self._last_now = self._time(now)
        self._origin = float(frame)
        self._set_phase(self._origin)

    def play(self, now: float) -> None:
        if self._playing:
            self.advance(now)
            return
        self._start = self._last_now = self._time(now)
        self._origin = self._phase
        self._playing = True

    def advance(self, now: float) -> int:
        value = self._time(now)
        if self._playing:
            elapsed = value-self._start
            if elapsed >= PERIOD_S:
                # Reduce timestamps before subtraction to also handle overflowed
                # differences between very large finite endpoints.
                elapsed = (value % PERIOD_S - self._start % PERIOD_S) % PERIOD_S
            self._set_phase((self._origin + elapsed*FPS) % FRAME_COUNT)
        self._last_now = value
        return self.frame

    def pause(self, now: float) -> None:
        self.advance(now)
        self._playing = False

    def reset(self, now: float) -> None:
        self.seek(0, now)
        self._playing = False
