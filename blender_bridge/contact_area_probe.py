"""Actual stable-face constraints for disposable bounded arm candidates."""
from dataclasses import replace

from blender_bridge.body_contact_areas import AreaInspector,area_report
from blender_bridge.body_contact_review import body_report
from blender_bridge.native_contact_probe import CandidateProbe,CandidateBudgetExceeded


def frame_areas(mesh,row):
    return {side:{mesh.loop_triangles[i].polygon_index for key in ('hand_triangles','central_triangles') for i in row[side][key]}
        for side in ('left','right')}


class SourceAreaAudit:
    def __init__(self,profile):self.profile=profile;self.inspector=None;self.areas=[]

    def frame(self,bpy,human,rig,mesh,frame,skin,topology):
        if self.inspector is None:self.inspector=AreaInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,topology)
        if self.inspector.status!='CHECKED' or self.inspector.area_reason:
            raise ValueError('COMPLETE_STABLE_BODY_AREAS_REQUIRED')
        self.areas.append(frame_areas(mesh,self.inspector.rows[-1]))

    def verify(self,expected,baseline,bindings,reopened):
        actual=area_report(body_report(baseline,bindings,self.inspector,None,reopened),[self.inspector])
        if actual!=expected:raise ValueError('Fresh source body contact areas differ from bound baseline')
        return actual


def area_critical_layout(layout,source):
    rows=source.inspector.rows
    ranked=sorted(range(layout.start+1,layout.end),key=lambda f:(-sum(rows[f-1][s]['pair_count'] for s in ('left','right')),f))
    extra=[f for f in ranked[:2] if any(rows[f-1][s]['pair_count'] for s in ('left','right'))]
    return replace(layout,critical=tuple(dict.fromkeys((*layout.critical,*extra))))


def area_trial_rank(row):
    # Different contact constraints have different count scales. Keep successful
    # trials first, then prefer progress through checked poses over comparing an
    # arm triangle-pair count directly with a new-body-polygon count.
    return (row['pairs']!=0,row['pairs']>=5000001,-row['checked'],row['pairs'],
        -row.get('body_frames_checked',0),sum(v*v for v in row['vector']))


class CandidateAreaGuard:
    def __init__(self,profile,source):
        self.profile=profile;self.source=source;self.frames=[];self.rejected=[]

    def reset(self):self.frames=[]

    def __call__(self,bpy,human,rig,mesh,frame,skin,topology):
        inspector=AreaInspector(self.profile,rig,human);inspector.inspect(mesh,frame,skin,topology)
        if (inspector.status!='CHECKED' or inspector.area_reason or inspector.polygon_sha!=self.source.inspector.polygon_sha):
            raise ValueError('CANDIDATE_STABLE_BODY_AREAS_UNAVAILABLE')
        actual=frame_areas(mesh,inspector.rows[-1]);cost=0
        for side in ('left','right'):
            cost+=len(actual[side]-self.source.areas[frame-1][side])
            cost+=max(0,inspector.rows[-1][side]['pair_count']-self.source.inspector.rows[frame-1][side]['pair_count'])
        self.frames.append(frame)
        if cost:self.rejected.append(frame)
        return cost


class AreaCandidateProbe(CandidateProbe):
    def __init__(self,bpy,human,rig,baseline,profile,source):
        self.area_guard=CandidateAreaGuard(profile,source)
        self._queries={};self._cache_enabled=True;self.cache_hits=0
        super().__init__(bpy,human,rig,baseline,profile,mesh_guard=self.area_guard)

    def frame(self,plan,frame):
        key=(tuple(plan['chain']),frame,tuple(plan['offsets'][frame-1]))
        if self._cache_enabled and key in self._queries:
            self.cache_hits+=1;cost,checked,error=self._queries[key]
            if error is not None:raise ValueError(error)
            if checked:self.area_guard.frames.append(frame)
            return cost
        before=len(self.area_guard.frames)
        try:cost=super().frame(plan,frame)
        except CandidateBudgetExceeded:raise
        except ValueError as error:
            self._queries[key]=(None,False,str(error));raise
        self._queries[key]=(cost,len(self.area_guard.frames)>before,None)
        return cost

    def evaluate(self,plan,frames):
        self.area_guard.reset();result=super().evaluate(plan,frames)
        return {**result,'body_frames_checked':len(self.area_guard.frames)}

    def evaluate_complete(self,plan,frames):
        # Sampling may reuse an exact already evaluated pose. Final acceptance
        # always evaluates the entire changed interval again, including all
        # quality, source-skin and body-area constraints, inside the same budget.
        self._cache_enabled=False
        try:return self.evaluate(plan,frames)
        finally:self._cache_enabled=True
