"""Ephemeral one-shot review of the original registered 300-frame cache.

Frames are always absolute cache indices, never a sliced or rewritten cache.
This module performs no IO and makes no animation/editing/approval decisions.
"""
from dataclasses import dataclass
import math

FRAME_COUNT = 300
FPS = 30.0
SOURCE_FIRST_FRAME = 2


@dataclass(frozen=True, slots=True)
class PlaybackWindow:
    """Inclusive one-based saved TARGET frame bounds; original source is +1."""
    target_first_frame: int = 1
    target_last_frame: int = FRAME_COUNT

    def __post_init__(self) -> None:
        if (type(self.target_first_frame) is not int or type(self.target_last_frame) is not int
                or not 1 <= self.target_first_frame <= self.target_last_frame <= FRAME_COUNT):
            raise ValueError('Choose an inclusive target review window within frames 1-300')

    @property
    def frame_count(self) -> int:
        """The complete admitted cache count, not the selected sample count."""
        return FRAME_COUNT

    @property
    def fps(self) -> float:
        return FPS

    @property
    def first_index(self) -> int:
        return self.target_first_frame-1

    @property
    def last_index(self) -> int:
        return self.target_last_frame-1

    @property
    def source_first_frame_selected(self) -> int:
        return self.first_index+SOURCE_FIRST_FRAME

    @property
    def source_last_frame_selected(self) -> int:
        return self.last_index+SOURCE_FIRST_FRAME

    @property
    def sample_count(self) -> int:
        return self.target_last_frame-self.target_first_frame+1

    @property
    def sample_span_s(self) -> float:
        return (self.sample_count-1)/FPS

    @property
    def nominal_coverage_s(self) -> float:
        return self.sample_count/FPS

    @property
    def is_static(self) -> bool:
        return self.sample_count==1

    def contains_index(self, index: int) -> bool:
        return type(index) is int and self.first_index <= index <= self.last_index

    def elapsed_at_index(self, index: int) -> float:
        """Sample time relative to the selected start, excluding final dwell."""
        if not self.contains_index(index):
            raise ValueError('Playback index lies outside the selected review window')
        return (index-self.first_index)/FPS


class WindowPlaybackClock:
    """Absolute-index, non-looping transport with a final 1/fps sample dwell.

    At sample_span_s the end frame is displayed. Playing becomes false after
    nominal_coverage_s, and that same end frame remains displayed indefinitely.
    Single-frame windows are static, so play() never starts a timer clock.
    """
    __slots__ = ('_window','_frame','_playing','_origin','_start','_last_now')

    def __init__(self, window: PlaybackWindow):
        if type(window) is not PlaybackWindow:
            raise ValueError('A typed immutable playback window is required')
        self._window = window
        self._frame = window.first_index
        self._playing = False
        self._origin = self._frame
        self._start = 0.0
        self._last_now = None

    @property
    def window(self) -> PlaybackWindow:
        return self._window

    @property
    def count(self) -> int:
        return FRAME_COUNT

    @property
    def fps(self) -> float:
        return FPS

    @property
    def frame(self) -> int:
        return self._frame

    @property
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, value: bool) -> None:
        # Existing MotionViewer failure cleanup stops its clock this way.
        if value is not False:
            raise ValueError('Use play(now) to start bounded playback')
        self._playing = False

    @property
    def loop(self) -> bool:
        return False

    @loop.setter
    def loop(self, value: bool) -> None:
        if value is not False:
            raise ValueError('A private review window cannot enable looping')

    def _time(self, now: float) -> float:
        if type(now) not in (int,float):
            raise ValueError('Playback time must be a finite monotonic number')
        try:
            value = float(now)
        except (ValueError,OverflowError) as error:
            raise ValueError('Playback time must be a finite monotonic number') from error
        if not math.isfinite(value) or (self._last_now is not None and value < self._last_now):
            raise ValueError('Playback time must be finite and nondecreasing')
        return value

    def seek(self, frame: int, now: float) -> None:
        if not self.window.contains_index(frame):
            raise ValueError('Playback index lies outside the selected review window')
        value = self._time(now)
        self._frame = self._origin = frame
        self._start = self._last_now = value
        if self.window.is_static:
            self._playing = False

    def play(self, now: float) -> None:
        if self._playing:
            self.advance(now)
            return
        value = self._time(now)
        frame = self.window.first_index if self.frame==self.window.last_index else self.frame
        self.seek(frame,value)
        self._playing = not self.window.is_static

    def advance(self, now: float) -> int:
        value = self._time(now)
        if self._playing:
            elapsed = value-self._start
            remaining = self.window.last_index-self._origin+1
            # Compare before multiplying: even a huge finite late timestamp (or
            # overflowed difference between finite endpoints) safely holds end.
            if elapsed >= remaining/FPS:
                self._frame = self.window.last_index
                self._playing = False
            else:
                steps = int(elapsed*FPS+1e-8)
                self._frame = min(self._origin+steps,self.window.last_index)
                if steps >= remaining:
                    self._playing = False
        self._last_now = value
        return self.frame

    def pause(self, now: float) -> None:
        self.advance(now)
        self._playing = False

    def reset(self, now: float) -> None:
        self.seek(self.window.first_index,now)
        self._playing = False
