"""Explicit actual-rig hand/central-body partition; no contact-intent inference."""
import math
from blender_bridge.native_surface_review import limb_bones

POLICY='HAND_CENTRAL_BODY_TRIANGLES_V1'
REGIONS=('left_hand','right_hand','central_body')
MAX_PAIR_WORK=40_000_000
MAX_PAIRS_PER_FRAME=250_000
MAX_HIGHLIGHTS=1_000_000
HAND_CHUNK=64
MAX_TRANSIENT_PAIRS=262144


def central_regions(parents: dict,hands: dict,head: str,deform: set) -> dict:
    if (type(parents) is not dict or not 1<=len(parents)<=256 or head not in parents or
        any(type(n) is not str or (p is not None and (type(p) is not str or p not in parents)) for n,p in parents.items()) or
        sum(p is None for p in parents.values())!=1 or not deform<=set(parents)):
        raise ValueError('Central-body review requires the complete actual rig hierarchy')
    for name in parents:
        visited=set();n=name
        while n is not None:
            if n in visited:raise ValueError('Central-body hierarchy contains a cycle')
            visited.add(n);n=parents[n]
    limbs=limb_bones(parents,hands,deform);body=set();n=head
    while n is not None:
        if n in deform:body.add(n)
        n=parents[n]
    regions={k:limbs[k] for k in REGIONS[:2]};regions['central_body']=body
    if not all(regions.values()) or any(regions[a]&regions[b] for a in regions for b in regions if a<b):
        raise ValueError('Central-body and hand regions are missing or overlap')
    return regions


def weighted_central_region(weights: dict,regions: dict,deform: set) -> str | None:
    if any(type(v) not in (int,float) or not 0<=v<=1 or not math.isfinite(v) for v in weights.values()):
        raise ValueError('Invalid actual deform weights for central-body review')
    total=sum(v for n,v in weights.items() if n in deform)
    if total<=0:return None
    scores={k:sum(v for n,v in weights.items() if n in regions[k]) for k in REGIONS}
    best=max(REGIONS,key=lambda k:scores[k])
    return best if scores[best]/total>=.5 else None
