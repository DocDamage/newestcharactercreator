"""Bounded actual hand/central-body triangle inspection, without quality approval."""
from hashlib import sha256
import struct

from blender_bridge.body_contact_regions import (
    POLICY,REGIONS,MAX_PAIR_WORK,MAX_PAIRS_PER_FRAME,MAX_HIGHLIGHTS,HAND_CHUNK,MAX_TRANSIENT_PAIRS,
    central_regions,weighted_central_region,
)


def triangle_pairs(points,hand,body,tree_type,*,body_tree=None):
    """Bound transient overlap lists by querying compact 64-triangle hand chunks."""
    if not hand or not body:raise ValueError('WEIGHTED_REGIONS_UNAVAILABLE')
    if len(hand)*len(body)>MAX_PAIR_WORK:raise ValueError('SURFACE_WORKLOAD_EXCEEDED')
    if body_tree is None:body_tree=tree_type.FromPolygons(points,[t for _,t in body],all_triangles=True)
    chunk_size=min(HAND_CHUNK,max(1,MAX_TRANSIENT_PAIRS//len(body)))
    digest=sha256();hand_ids=set();body_ids=set();count=0
    for start in range(0,len(hand),chunk_size):
        chunk=hand[start:start+chunk_size];ids=sorted({v for _,tri in chunk for v in tri});lookup={v:i for i,v in enumerate(ids)}
        tree=tree_type.FromPolygons([points[i] for i in ids],[tuple(lookup[v] for v in tri) for _,tri in chunk],all_triangles=True)
        pairs=sorted((chunk[a][0],body[b][0]) for a,b in tree.overlap(body_tree))
        count+=len(pairs)
        if count>MAX_PAIRS_PER_FRAME:raise ValueError('SURFACE_PAIR_BUDGET_EXCEEDED')
        for a,b in pairs:digest.update(struct.pack('<II',a,b));hand_ids.add(a);body_ids.add(b)
    return {'pair_count':count,'pair_sha256':digest.hexdigest(),'hand_triangles':sorted(hand_ids),'central_triangles':sorted(body_ids)}


class BodyContactInspector:
    def __init__(self,profile,rig,human):
        self.rows=[];self.human=human;self.status='CHECKED';self.reason='';self.vertices=None;self.highlights=0
        self.parents={b.name:b.parent.name if b.parent else None for b in rig.data.bones}
        self.deform={b.name for b in rig.data.bones if b.use_deform}
        self.hands={s:profile['landmarks'][s+'_hand']['target'] for s in ('left','right')}
        self.head=profile['landmarks']['head']['target'];self.regions={};self.counts={}
        self.world=[float(v) for row in human.matrix_world for v in row]
        try:self.regions=central_regions(self.parents,self.hands,self.head,self.deform)
        except ValueError:self.unavailable('CENTRAL_BRANCH_UNAVAILABLE')

    def unavailable(self,reason):
        self.status='UNAVAILABLE';self.reason=reason
        for row in self.rows:row['left']=row['right']=None

    def inspect(self,mesh,frame,skin_sha,triangle_sha):
        from mathutils.bvhtree import BVHTree
        row={'frame':frame,'skin_sha256':skin_sha,'triangle_sha256':triangle_sha,'left':None,'right':None}
        if [float(v) for line in self.human.matrix_world for v in line]!=self.world:
            raise ValueError('Central-body review world transform changed during inspection')
        if self.status=='CHECKED':
            try:
                if self.vertices is None:
                    names={g.index:g.name for g in self.human.vertex_groups};self.vertices={k:set() for k in REGIONS}
                    for vertex in mesh.vertices:
                        region=weighted_central_region({names[g.group]:g.weight for g in vertex.groups},self.regions,self.deform)
                        if region is not None:self.vertices[region].add(vertex.index)
                    self.counts={k:len(v) for k,v in self.vertices.items()}
                    if not all(self.counts.values()):raise ValueError('WEIGHTED_REGIONS_UNAVAILABLE')
                triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
                selected={k:[(i,t) for i,t in enumerate(triangles) if all(v in members for v in t)] for k,members in self.vertices.items()}
                if not all(selected.values()):raise ValueError('WEIGHTED_REGIONS_UNAVAILABLE')
                points=[self.human.matrix_world@v.co for v in mesh.vertices];body=selected['central_body']
                body_tree=BVHTree.FromPolygons(points,[t for _,t in body],all_triangles=True)
                for side in ('left','right'):
                    hand=selected[side+'_hand']
                    if len(hand)*len(body)>MAX_PAIR_WORK:raise ValueError('SURFACE_WORKLOAD_EXCEEDED')
                    hit=triangle_pairs(points,hand,body,BVHTree,body_tree=body_tree)
                    self.highlights+=len(hit['hand_triangles'])+len(hit['central_triangles'])
                    if self.highlights>MAX_HIGHLIGHTS:raise ValueError('SURFACE_HIGHLIGHTS_EXCEEDED')
                    row[side]=hit
            except ValueError as error:
                reason=str(error)
                if reason not in {'WEIGHTED_REGIONS_UNAVAILABLE','SURFACE_WORKLOAD_EXCEEDED','SURFACE_PAIR_BUDGET_EXCEEDED','SURFACE_HIGHLIGHTS_EXCEEDED'}:
                    raise
                self.unavailable(reason)
        if self.status!='CHECKED':row['left']=row['right']=None
        self.rows.append(row)

    def report(self):
        return {'policy':POLICY,'status':self.status,'reason':self.reason,'hands':dict(self.hands),'head':self.head,
                'parents':dict(self.parents),'deform_bones':sorted(self.deform),'world_matrix':list(self.world),
                'region_bones':{k:sorted(v) for k,v in self.regions.items()},'region_vertex_counts':dict(self.counts),
                'frame_count':len(self.rows),'frames':self.rows,'contact_quality_verified':False,'engine_import_verified':False}
