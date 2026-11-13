"""Arm-clear seed -> measured body failures -> bounded wrist orientation search."""
from __future__ import annotations
from types import SimpleNamespace
from typing import TYPE_CHECKING
import math

from blender_bridge.contact_candidate_policy import trial_policy
from blender_bridge.native_contact_candidate import search_candidate
from blender_bridge.hand_candidate_policy import measured_window,orientation_vectors,hand_trial,nearby_vectors,hand_rank

if TYPE_CHECKING:
    from blender_bridge.contact_candidate_policy import CandidateLayout
    from blender_bridge.contact_area_probe import AreaCandidateProbe,SourceAreaAudit

ALGORITHM='BOUNDED_HAND_CONTACT_AREA_SEARCH_V3'


def search_hand_candidate(layout: CandidateLayout,probe: AreaCandidateProbe,bindings: dict,baseline: dict,
                          profile: dict,parents: dict,source: SourceAreaAudit,*,observations: list[dict] | None=None) -> tuple[dict,list[dict]]:
    observations=[] if observations is None else observations
    seed_rows=[]
    # A seed is explicitly arm-only, not accepted output. Its evaluations share
    # the actual 1,024-pose budget with every subsequent body/hand query.
    try:
        seed,seed_rows=search_candidate(layout,SimpleNamespace(evaluate=probe.evaluate_arm_seed),
            bindings,baseline,profile,parents,observations=seed_rows)
    finally:
        observations.extend({**r,'phase':'arm_seed'} for r in seed_rows)
    vector=tuple(max(seed['frames'],key=lambda r:math.hypot(*r['offset_world']))['offset_world'])
    _,plan=trial_policy(layout,vector,bindings,baseline,profile,parents)
    changed=list(range(layout.start+1,layout.end));bad=[]

    def available():
        if len(observations)>=499:raise ValueError('CANDIDATE_TRIAL_BUDGET_EXCEEDED')

    def record(row):
        available()
        observations.append(row)

    for frame in changed:
        available()
        result=probe.evaluate(plan,[frame]);record({'vector':vector,'phase':'seed_body',**result})
        if result.get('body_frames_checked')!=1:raise ValueError('SEED_COMPLETE_BODY_CONSTRAINTS_UNAVAILABLE')
        if result['pairs']:bad.append(frame)
    if not bad:
        available()
        result=probe.evaluate_complete(plan,changed);record({'vector':vector,'phase':'seed_complete',**result})
        if result['pairs']==0:return seed,observations
        raise ValueError('FRESH_SEED_BODY_REPRODUCTION_FAILED')

    window=measured_window(layout,bad)
    worst=max(bad,key=lambda f:sum(source.inspector.rows[f-1][s]['pair_count'] for s in ('left','right')))
    critical=list(dict.fromkeys((worst,bad[0],layout.critical[0],bad[-1],*layout.critical)))
    learned=[];tested=set();hand_rows=[]

    def evaluate(v,rotation,complete=False):
        available()
        phase='hand_complete' if complete else 'hand_sample'
        try:data,plan=hand_trial(layout,window,v,rotation,bindings,baseline,profile,parents)
        except ValueError as error:
            row={'vector':v,'hand_rotation':rotation,'phase':phase,'pairs':5_000_001,'checked':0,'reason':str(error)}
            record(row);hand_rows.append(row);return None,row
        frames=changed if complete else critical
        method=probe.evaluate_complete if complete else probe.evaluate
        result=method(plan,frames);row={'vector':v,'hand_rotation':rotation,'phase':phase,**result}
        record(row);hand_rows.append(row)
        failed=result.get('failed_frame')
        if complete and type(failed) is int and failed in changed and failed not in critical:
            critical.append(failed);learned.append(failed)
        return data,row

    def try_configuration(v,rotation):
        key=(tuple(v),tuple(rotation))
        if key in tested:return None
        tested.add(key)
        _,row=evaluate(v,rotation)
        if row['pairs']:return None
        data,row=evaluate(v,rotation,True)
        if row['pairs']:return None
        # Include learned failure poses in the private saved-fit visual review.
        chosen=list(dict.fromkeys((1,layout.count,*reversed(learned),worst,bad[0],bad[-1],*layout.render_frames)))[:5]
        data['render_frames']=sorted(chosen)
        return data

    for rotation in orientation_vectors():
        chosen=try_configuration(vector,rotation)
        if chosen is not None:return chosen,observations
    for step in (min(.005,layout.maximum/6),min(.0025,layout.maximum/12),min(.00125,layout.maximum/24)):
        best=[];seen=set()
        for row in sorted(hand_rows,key=hand_rank):
            key=(tuple(row['vector']),tuple(row['hand_rotation']))
            if key not in seen:best.append(row);seen.add(key)
            if len(best)==2:break
        for row in best:
            for v in nearby_vectors(layout,row['vector'],step):
                chosen=try_configuration(v,row['hand_rotation'])
                if chosen is not None:return chosen,observations
    raise ValueError('NO_BOUNDED_HAND_CONTACT_CANDIDATE_FOUND; original motion retained')
