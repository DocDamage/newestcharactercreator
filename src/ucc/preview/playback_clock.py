"""Deterministic source-fps transport; timer callbacks may arrive late."""
from dataclasses import dataclass
import math


@dataclass(slots=True)
class PlaybackClock:
    count: int
    fps: float
    frame: int=0
    playing: bool=False
    loop: bool=True
    _start: float=0.
    _origin: int=0

    def __post_init__(self):
        if type(self.count) is not int or self.count<2 or not math.isfinite(self.fps) or not 1<=self.fps<=240:
            raise ValueError("Invalid complete playback timeline")

    def seek(self,frame: int,now: float):
        if type(frame) is not int or not 0<=frame<self.count:raise ValueError("Invalid playback frame")
        self.frame=frame;self._origin=frame;self._start=now

    def play(self,now: float):
        if self.frame==self.count-1:self.frame=0
        self.seek(self.frame,now);self.playing=True

    def advance(self,now: float) -> int:
        if self.playing:
            absolute=self._origin+int(max(0.,now-self._start)*self.fps+1e-8)
            if self.loop:self.frame=absolute%self.count
            else:
                self.frame=min(absolute,self.count-1)
                if absolute>=self.count:self.playing=False
        return self.frame

    def pause(self,now: float):
        self.advance(now);self.playing=False
