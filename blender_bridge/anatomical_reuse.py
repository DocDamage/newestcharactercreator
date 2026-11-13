"""Exact process-local reuse of independently measured original geometry."""
from array import array
from copy import deepcopy
import json
from typing import Any,Callable

from blender_bridge.complete_anatomical_review import CompleteInspector,CompleteCollector
from blender_bridge import native_body_contacts


MAX_KEY_BYTES=256*1024*1024


class ExactSourceFrames:
    def __init__(self) -> None:
        self.frames={};self.contexts=set();self.bytes=0;self.hits=0;self.misses=0;self.dropped=0

    def store(self,frame: int,key: tuple[bytes,bytes,bytes,bytes],rows: tuple[dict,dict,dict]) -> None:
        size=sum(len(v) for v in key[1:])+(0 if key[0] in self.contexts else len(key[0]))
        if frame in self.frames or self.bytes+size>MAX_KEY_BYTES or len(self.frames)>=2000:
            self.dropped+=1;return
        self.frames[frame]=(key,rows);self.contexts.add(key[0]);self.bytes+=size


class ExactInspector(CompleteInspector):
    def __init__(self,profile: dict,rig: Any,human: Any,memo: ExactSourceFrames,source: bool) -> None:
        super().__init__(profile,rig,human)
        self._profile=profile;self._memo=memo;self._source=source;self._context_bytes=None

    def _context(self) -> bytes:
        # Include actual independently selected regions and full topology.
        # No quantized coordinate hash is used to authorize reuse.
        import blender_bridge.central_enclosure as enclosure
        import blender_bridge.central_surface as surface
        import blender_bridge.central_geometry as geometry
        import blender_bridge.central_cap as cap
        import blender_bridge.closed_skin as closed
        import blender_bridge.skin_winding as winding
        import blender_bridge.body_contact_regions as regions
        modules=(enclosure,surface,geometry,cap,closed,winding,regions,native_body_contacts)
        budgets={m.__name__:{k:repr(v) for k,v in vars(m).items() if k.isupper() and
                            type(v) in (int,float,str,tuple,frozenset)} for m in modules}
        values={'profile':self._profile,'parents':self.parents,'deform':sorted(self.deform),
            'world':self.world,'hands':self.hands,'head':self.head,'status':self.status,'reason':self.reason,
            'area_reason':self.area_reason,'polygons':self.polygons,'polygon_sha':self.polygon_sha,
            'regions':{k:sorted(v) for k,v in self.regions.items()},
            'vertices':{k:sorted(v) for k,v in self.vertices.items()},'counts':self.counts,
            'volume_regions':{k:sorted(v) for k,v in self.volume_regions.items()},
            'volume_vertices':{k:sorted(v) for k,v in self.volume_vertices.items()},
            'limb_roots':self.limb_roots,'budgets':budgets}
        context=json.dumps(values,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
        if context!=self._context_bytes:self._context_bytes=context
        return self._context_bytes

    def _key(self,mesh: Any) -> tuple[bytes,bytes,bytes,bytes] | None:
        # Bounds precede allocation. A miss falls through to the unchanged
        # original validation; there is no partial geometric verdict.
        if (not 4<=len(mesh.vertices)<=50000 or not 4<=len(mesh.loop_triangles)<=100000 or
            not 1<=len(mesh.polygons)<=100000 or len(mesh.loops)>1000000):
            return None
        if [float(v) for row in self.human.matrix_world for v in row]!=self.world:
            raise ValueError('Central-body review world transform changed during inspection')
        vertices=array('f',[0.])*(3*len(mesh.vertices));mesh.vertices.foreach_get('co',vertices)
        triangles=array('I',[0])*(3*len(mesh.loop_triangles));mesh.loop_triangles.foreach_get('vertices',triangles)
        polygons=array('I')
        for polygon in mesh.polygons:
            polygons.append(len(polygon.vertices));polygons.extend(polygon.vertices)
        return self._context(),vertices.tobytes(),triangles.tobytes(),polygons.tobytes()

    def inspect(self,mesh,frame,skin,triangles):
        # Each fresh inspector fully computes its first frame before it can
        # establish a region/topology context. Source frames always compute.
        first=self.vertices is None or self.volume_vertices is None or self.polygons is None
        key=None if first else self._key(mesh)
        cached=self._memo.frames.get(frame) if not self._source and not first else None
        if cached is not None and key is not None and cached[0]==key:
            body,volume,full=cached[1]
            self.highlights+=sum(len(body[s][k]) for s in ('left','right')
                                 for k in ('hand_triangles','central_triangles'))
            if self.highlights>native_body_contacts.MAX_HIGHLIGHTS:
                self.unavailable('SURFACE_HIGHLIGHTS_EXCEEDED')
                raise ValueError('COMPLETE_ANATOMICAL_SURFACES_REQUIRED')
            self.rows.append({'frame':frame,'skin_sha256':skin,'triangle_sha256':triangles,
                              **{s:deepcopy(body[s]) for s in ('left','right')}})
            self.enclosure_rows.append({'frame':frame,'skin_sha256':skin,'triangle_sha256':triangles,
                                        'observation':deepcopy(volume['observation'])})
            self._record(frame,skin,triangles,deepcopy(full['observation']))
            self._memo.hits+=1;return
        if not self._source:self._memo.misses+=1
        super().inspect(mesh,frame,skin,triangles)
        if self._source:
            if key is None:key=self._key(mesh)
            if key is None:self._memo.dropped+=1
            else:self._memo.store(frame,key,(self.rows[-1],self.enclosure_rows[-1],self.complete_rows[-1]))


def collector_factory(memo: ExactSourceFrames) -> Callable[[dict],CompleteCollector]:
    calls=[]
    class ExactCollector(CompleteCollector):
        def __init__(self,profile,source):super().__init__(profile);self._source=source
        def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
            if self.inspector is None:self.inspector=ExactInspector(self.profile,rig,human,memo,self._source)
            self.inspector.inspect(mesh,frame,skin,triangles)
    def factory(profile):
        if len(calls)>=2:raise ValueError('EXACT_ANATOMICAL_COLLECTOR_COVERAGE')
        source=not calls;calls.append(source)
        return ExactCollector(profile,source)
    return factory
