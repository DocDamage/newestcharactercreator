"""Generate bounded hand policies from observed seed-body failures only."""
from dataclasses import dataclass
from itertools import product
import math

from blender_bridge.contact_candidate_policy import CandidateLayout,trial_policy
from blender_bridge.native_fit_policy import parse_fit
from blender_bridge.native_hand_fit import POLICY


@dataclass(frozen=True,slots=True)
class HandWindow:
    begin: int
    first: int
    last: int
    end: int


def measured_window(layout: CandidateLayout,failed_frames: list[int]) -> HandWindow:
    if (not failed_frames or any(type(f) is not int or not layout.start<f<layout.end for f in failed_frames)):
        raise ValueError('HAND_WINDOW_REQUIRES_CHECKED_BODY_FAILURES')
    first,last=min(failed_frames),max(failed_frames);fade=math.ceil(layout.fps*.5)
    return HandWindow(max(layout.start,first-fade),first,last,min(layout.end,last+fade))


def orientation_vectors() -> tuple[tuple[float,float,float],...]:
    return tuple(tuple(sign*degrees*x for x in axis)
        for degrees in (5.,10.,15.) for axis in ((1,0,0),(0,1,0),(0,0,1)) for sign in (-1,1))


def hand_trial(layout: CandidateLayout,window: HandWindow,vector: tuple,rotation: tuple,
               bindings: dict,baseline: dict,profile: dict,parents: dict) -> tuple[dict,dict]:
    data,_=trial_policy(layout,vector,bindings,baseline,profile,parents)
    data['policy']=POLICY
    for row in data['frames']:
        frame=row['frame']
        t=min(1.,max(0.,(frame-window.begin)/(window.first-window.begin)),
                    max(0.,(window.end-frame)/(window.end-window.last)))
        row['hand_rotation_local_degrees']=[v*t*t*(3-2*t) for v in rotation]
    return data,parse_fit(data,bindings,baseline,profile,parents)


def nearby_vectors(layout: CandidateLayout,vector: tuple,step: float) -> tuple[tuple[float,float,float],...]:
    if type(step) not in (float,int) or not 0<step<=.005:raise ValueError('Invalid bounded wrist refinement')
    values={tuple(round(v+d,9) for v,d in zip(vector,delta)) for delta in product((-step,0.,step),repeat=3) if any(delta)}
    return tuple(sorted((v for v in values if 0<math.hypot(*v)<=layout.maximum),
        key=lambda v:(math.dist(v,vector),math.hypot(*v),v)))


def hand_rank(row: dict) -> tuple:
    return (row['pairs']>=5_000_001,-(row['checked'] if row.get('phase')=='hand_complete' else 0),
        row['pairs'],-row['checked'],math.hypot(*row.get('hand_rotation',(0.,0.,0.))),math.hypot(*row['vector']))
