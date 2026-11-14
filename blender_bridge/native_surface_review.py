"""Actual evaluated hand/opposite-limb triangle intersections, never a grasp verdict."""
from hashlib import sha256
import struct

POLICY="HAND_OPPOSITE_UPPER_LIMB_TRIANGLES_V1"
MAX_HIGHLIGHTS=1_000_000


def weighted_region(weights: dict,regions: dict,deform: set) -> str | None:
    total=sum(v for name,v in weights.items() if name in deform)
    if total<=0:return None
    # The armature normalizes deform weights. Hand wins an exact hand/arm tie;
    # left wins a remaining side tie. Each evaluated vertex has one region.
    order=('left_hand','right_hand','left_arm','right_arm')
    scores={key:sum(v for name,v in weights.items() if name in regions[key]) for key in order}
    best=max(order,key=lambda key:scores[key])
    return best if scores[best]/total>=.5 else None


def limb_bones(parents: dict, hands: dict, deform: set) -> dict:
    def ancestors(name):
        result=[]
        while name is not None:
            if name not in parents or name in result:raise ValueError("Invalid surface-review rig hierarchy")
            result.append(name);name=parents[name]
        return result
    paths={side:ancestors(name) for side,name in hands.items()}
    common=next((n for n in paths["left"] if n in paths["right"]),None)
    if common is None:raise ValueError("Hands have no common rig ancestor")
    result={}
    for side in ("left","right"):
        path=paths[side];index=path.index(common)
        if index<2:raise ValueError("No separate upper-limb branch above the hand")
        branch=path[index-1]
        hand={n for n in deform if hands[side] in ancestors(n)}
        limb={n for n in deform if branch in ancestors(n)}-hand
        if not hand or not limb:raise ValueError("Missing deforming hand/upper-limb branch")
        result[side+"_hand"]=hand;result[side+"_arm"]=limb
    if any(result[a]&result[b] for a in result for b in result if a<b):
        raise ValueError("Surface-review bone regions overlap")
    return result


class SurfaceInspector:
    def __init__(self,profile: dict,rig,human):
        self.human=human;self.status="CHECKED";self.reason="";self.rows=[];self.regions=None;self.highlights=0
        self.hands={side:profile["landmarks"][side+"_hand"]["target"] for side in ("left","right")}
        self.bones={};self.vertex_counts={};self.deform={b.name for b in rig.data.bones if b.use_deform}
        try:
            self.bones=limb_bones({b.name:b.parent.name if b.parent else None for b in rig.data.bones},
                self.hands,self.deform)
        except ValueError:self.unavailable("HAND_BRANCHES_UNAVAILABLE")

    def unavailable(self,reason):
        self.status="UNAVAILABLE";self.reason=reason
        for row in self.rows:row["left"]=row["right"]=None

    def _vertices(self,mesh):
        names={g.index:g.name for g in self.human.vertex_groups}
        result={key:set() for key in self.bones}
        for vertex in mesh.vertices:
            weights={names[g.group]:g.weight for g in vertex.groups}
            region=weighted_region(weights,self.bones,self.deform)
            if region is not None:result[region].add(vertex.index)
        if any(not value for value in result.values()) or any(result[a]&result[b] for a in result for b in result if a<b):
            self.unavailable("WEIGHTED_REGIONS_UNAVAILABLE")
        self.vertex_counts={k:len(v) for k,v in result.items()}
        return result

    def inspect(self,mesh,frame: int,skin_sha: str,triangle_sha: str):
        from mathutils.bvhtree import BVHTree
        if self.regions is None and self.status=="CHECKED":self.regions=self._vertices(mesh)
        row={"frame":frame,"skin_sha256":skin_sha,"triangle_sha256":triangle_sha,"left":None,"right":None}
        if self.status=="CHECKED":
            points=[self.human.matrix_world@v.co for v in mesh.vertices]
            triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
            for side,other in (("left","right"),("right","left")):
                hand=[(i,t) for i,t in enumerate(triangles) if all(v in self.regions[side+"_hand"] for v in t)]
                arm=[(i,t) for i,t in enumerate(triangles) if all(v in self.regions[other+"_arm"] for v in t)]
                if not hand or not arm:
                    self.unavailable("WEIGHTED_REGIONS_UNAVAILABLE");break
                if len(hand)*len(arm)>5_000_000:
                    self.unavailable("SURFACE_WORKLOAD_EXCEEDED");break
                ht=BVHTree.FromPolygons(points,[t for _,t in hand],all_triangles=True)
                at=BVHTree.FromPolygons(points,[t for _,t in arm],all_triangles=True)
                pairs=sorted((hand[a][0],arm[b][0]) for a,b in ht.overlap(at))
                digest=sha256()
                for a,b in pairs:digest.update(struct.pack("<II",a,b))
                h=sorted({a for a,_ in pairs});a=sorted({b for _,b in pairs})
                self.highlights+=len(h)+len(a)
                if self.highlights>MAX_HIGHLIGHTS:
                    self.unavailable("SURFACE_WORKLOAD_EXCEEDED");break
                row[side]={"pair_count":len(pairs),"pair_sha256":digest.hexdigest(),"hand_triangles":h,"opposite_arm_triangles":a}
        if self.status!="CHECKED":row["left"]=row["right"]=None
        self.rows.append(row)

    def report(self,bindings: dict) -> dict:
        return {"schema_version":1,"policy":POLICY,"bindings":dict(bindings),"status":self.status,"reason":self.reason,
            "hands":self.hands,"region_bones":{k:sorted(v) for k,v in self.bones.items()},"region_vertex_counts":self.vertex_counts,
            "frame_count":len(self.rows),"frames":self.rows,"contact_quality_verified":False,"engine_import_verified":False}
