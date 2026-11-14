"""Bounded trial policies for a measured one-hand contact interval.

No geometry verdict is made here. Callers must freshly reproduce the complete
surface report, evaluate actual candidate skin, then use the saved-fit pipeline.
"""
from dataclasses import dataclass
from itertools import product
import math

from blender_bridge.native_fit_policy import BASE_HASHES,POLICY,parse_fit

ALGORITHM='BOUNDED_CONTACT_OFFSET_SEARCH_V1'
MAX_POSE_TESTS=1024


class CandidateUnavailable(ValueError):
    def __init__(self,code: str):
        self.code=code
        super().__init__(code)


@dataclass(frozen=True,slots=True)
class CandidateLayout:
    side: str
    chain: tuple[str,str,str]
    first: int
    last: int
    start: int
    end: int
    critical: tuple[int,...]
    render_frames: tuple[int,...]
    maximum: float
    count: int
    fps: float


def candidate_layout(baseline: dict,profile: dict,parents: dict,contacts: dict) -> CandidateLayout:
    count=baseline['source_frame_count'];fps=baseline['fps']
    if (type(count) is not int or not 5<=count<=2000 or type(fps) not in (int,float) or not 1<=fps<=240 or
        profile.get('skin_deformation_policy')!='BOUND_CORRECTIVE_SMOOTH_V1' or
        profile.get('mesh_strain_reference')!='TRUE_NEUTRAL_BIND_V2'):
        raise CandidateUnavailable('UNSUPPORTED_TIMELINE_OR_SKIN_REFERENCE')
    if (type(contacts) is not dict or contacts.get('status')!='CHECKED' or contacts.get('frame_count')!=count or
        type(contacts.get('frames')) is not list or len(contacts['frames'])!=count):
        raise CandidateUnavailable('COMPLETE_SURFACE_REVIEW_REQUIRED')
    pairs={side:[] for side in ('left','right')}
    for frame,row in enumerate(contacts['frames'],1):
        if type(row) is not dict or type(row.get('frame')) is not int or row['frame']!=frame:
            raise CandidateUnavailable('COMPLETE_SURFACE_REVIEW_REQUIRED')
        for side in pairs:
            value=row.get(side)
            if (type(value) is not dict or type(value.get('pair_count')) is not int or
                not 0<=value['pair_count']<=5_000_000):
                raise CandidateUnavailable('COMPLETE_SURFACE_REVIEW_REQUIRED')
            pairs[side].append(value['pair_count'])
    active=[side for side,values in pairs.items() if any(values)]
    if not active:raise CandidateUnavailable('NO_CHECKED_CROSSINGS')
    if len(active)!=1:raise CandidateUnavailable('MULTIPLE_CONTACTING_HANDS_UNSUPPORTED')
    side=active[0];flagged=[i for i,v in enumerate(pairs[side],1) if v];first,last=flagged[0],flagged[-1]
    if first==1 or last==count:raise CandidateUnavailable('CONTACT_AT_FIXED_ENDPOINT')
    targets={p['target'] for p in profile['pairs']};known=targets|set(baseline['neutral_target_helpers'])
    if type(parents) is not dict or set(parents)!=known or len(known)>256:
        raise CandidateUnavailable('COMPLETE_ACTUAL_HIERARCHY_REQUIRED')
    if (sum(p is None for p in parents.values())!=1 or
        any(p is not None and (type(p) is not str or p not in known) for p in parents.values())):
        raise CandidateUnavailable('COMPLETE_ACTUAL_HIERARCHY_REQUIRED')
    for name in parents:
        seen=set();n=name
        while n is not None:
            if n not in parents or n in seen:raise CandidateUnavailable('COMPLETE_ACTUAL_HIERARCHY_REQUIRED')
            seen.add(n);n=parents[n]
    hand=profile['landmarks'][side+'_hand']['target'];ancestors=[];n=parents[hand]
    while n is not None:
        if n in targets:ancestors.append(n)
        n=parents[n]
    if len(ancestors)<2:raise CandidateUnavailable('MAPPED_ARM_CHAIN_REQUIRED')
    chain=(ancestors[1],ancestors[0],hand)
    feet=[(baseline['target_anatomical_landmarks']['left_foot'][i]+baseline['target_anatomical_landmarks']['right_foot'][i])/2 for i in range(3)]
    span=math.dist(baseline['target_anatomical_landmarks']['head'],feet)
    if not .1<span<10:raise CandidateUnavailable('INVALID_ANATOMICAL_SPAN')
    ranked=sorted(flagged,key=lambda f:(-pairs[side][f-1],f))
    fade=math.ceil(fps*.5);start=max(1,first-fade);end=min(count,last+fade)
    if end-start-1>MAX_POSE_TESTS:raise CandidateUnavailable('CONTACT_INTERVAL_EXCEEDS_CANDIDATE_BUDGET')
    critical=tuple(dict.fromkeys((ranked[0],ranked[min(1,len(ranked)-1)],first-1,first,last,start+1,end-1)))
    chosen={1,count,first,last,ranked[0]}
    for frame in ranked+list(range(1,count+1)):
        if len(chosen)==5:break
        chosen.add(frame)
    return CandidateLayout(side,chain,first,last,start,end,critical,tuple(sorted(chosen)),min(.03,.02*span),count,float(fps))


def trial_policy(layout: CandidateLayout,vector: tuple,bindings: dict,baseline: dict,profile: dict,parents: dict) -> tuple[dict,dict]:
    if (type(bindings) is not dict or set(bindings)!=BASE_HASHES or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in bindings.values())):
        raise ValueError('Candidate policy needs original source-FK bindings')
    if (type(vector) not in (tuple,list) or len(vector)!=3 or
        any(type(v) not in (int,float) or not -layout.maximum<=v<=layout.maximum for v in vector)):
        raise ValueError('Candidate vector exceeds fixed finite bounds')
    rows=[]
    for frame in range(1,layout.count+1):
        t=min(1.,max(0.,(frame-layout.start)/(layout.first-layout.start)),max(0.,(layout.end-frame)/(layout.end-layout.last)))
        t=t*t*(3-2*t)
        rows.append({'frame':frame,'offset_world':[v*t for v in vector]})
    data={'schema_version':1,'policy':POLICY,'bindings':dict(bindings),'coordinate_space':'BLENDER_WORLD_METERS',
          'chain':dict(zip(('side','upper_arm','forearm','hand'),(layout.side,*layout.chain))),
          'fps':layout.fps,'frames':rows,'render_frames':list(layout.render_frames)}
    return data,parse_fit(data,bindings,baseline,profile,parents)


def coarse_vectors(layout: CandidateLayout) -> tuple[tuple[float,float,float],...]:
    step=min(.02,layout.maximum/math.sqrt(2))
    return tuple(tuple(step*x for x in v) for v in product((-1,0,1),repeat=3) if 0<sum(x*x for x in v)<=2)


def refine_vectors(layout: CandidateLayout,observations: list[dict],*,rank_key=None,step_size=None) -> tuple[tuple[float,float,float],...]:
    step=min(.005,layout.maximum/6) if step_size is None else step_size
    if type(step) not in (float,int) or not 0<step<=.005:raise ValueError('Invalid bounded refinement step')
    known={tuple(round(v,9) for v in r['vector']) for r in observations}
    best=sorted(observations,key=rank_key or (lambda r:(r['pairs'],math.hypot(*r['vector']))))[:8];vectors=set()
    for row in best:
        for delta in product((-step,0.,step),repeat=3):
            v=tuple(round(a+b,9) for a,b in zip(row['vector'],delta))
            if 0<math.hypot(*v)<=layout.maximum and v not in known:vectors.add(v)
    return tuple(sorted(vectors,key=lambda v:(math.hypot(*v),v)))
