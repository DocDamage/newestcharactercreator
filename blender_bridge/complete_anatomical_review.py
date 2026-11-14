"""One fresh traversal binds areas, enclosure and complete trunk surface pairs."""
from hashlib import sha256
import json

from blender_bridge.anatomical_review import AnatomicalInspector,AnatomicalCollector,measure_anatomical_safety
from blender_bridge.body_contact_review import SOURCE_FIELDS,FIT_FIELDS,FLAGS,unchanged
from blender_bridge.central_geometry import central_geometry
from blender_bridge.central_surface import observe_central_surfaces,POLICY
from blender_bridge.body_contact_regions import MAX_HIGHLIGHTS
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import digest

REPORTS={'body_contacts.json':('body_review_sha256',40*1024*1024),
         'central_enclosure.json':('enclosure_review_sha256',64*1024*1024),
         'full_trunk_contacts.json':('full_trunk_review_sha256',64*1024*1024)}
REPORT_HASHES={key for key,_ in REPORTS.values()}
OPERATIONS={kind+'_'+variant+'_complete_anatomical_safety':(FIT_FIELDS if variant=='fitted' else SOURCE_FIELDS)|
    (REPORT_HASHES if kind=='verify' else set()) for kind in ('inspect','verify') for variant in ('native','fitted')}


def checked_complete_job(job):
    options=job['options'];fields=OPERATIONS[job['operation']]
    if 'fitted_sha256' in fields:
        from blender_bridge.native_symmetric_policy import layer_fields
        fields=layer_fields(fields,options)
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Complete anatomical review requires exact hashes and fixed staged inputs')
    return options


class CompleteInspector(AnatomicalInspector):
    def __init__(self,profile,rig,human):
        super().__init__(profile,rig,human);self.complete_rows=[];self.complete_highlights=0

    def inspect(self,mesh,frame,skin,triangles):
        from mathutils.bvhtree import BVHTree
        super().inspect(mesh,frame,skin,triangles)
        faces=[tuple(t.vertices) for t in mesh.loop_triangles];polygon_ids=[t.polygon_index for t in mesh.loop_triangles]
        geometry=central_geometry([tuple(v.co) for v in mesh.vertices],faces,polygon_ids,self.polygons,
            self.volume_vertices['central_body'],tuple(self.world))
        observation=observe_central_surfaces(geometry,faces,polygon_ids,
            {s:self.volume_vertices[s+'_hand'] for s in ('left','right')},BVHTree)
        self._record(frame,skin,triangles,observation)

    def _record(self,frame,skin,triangles,observation):
        if observation['body_triangle_ids']!=self.enclosure_rows[-1]['observation']['body_triangle_ids']:
            raise ValueError('Complete anatomical observations disagree on actual body triangles')
        total=self.complete_highlights+sum(len(observation[s][key]) for s in ('left','right')
            for key in ('hand_triangles','central_triangles'))
        if total>MAX_HIGHLIGHTS:raise ValueError('COMPLETE_TRUNK_SURFACE_HIGHLIGHTS_EXCEEDED')
        self.complete_highlights=total
        self.complete_rows.append({'frame':frame,'skin_sha256':skin,'triangle_sha256':triangles,'observation':observation})


class CompleteCollector(AnatomicalCollector):
    def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
        if self.inspector is None:self.inspector=CompleteInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,triangles)


def measure_complete(bpy,root,options,*,collector_factory=None):
    if collector_factory is None:
        collector_factory=CompleteCollector
        if 'fitted_sha256' in options:
            from blender_bridge.anatomical_reuse import ExactSourceFrames,collector_factory as exact_factory
            collector_factory=exact_factory(ExactSourceFrames())
    collectors=[]
    def factory(profile):
        collector=collector_factory(profile);collectors.append(collector);return collector
    base={k:v for k,v in options.items() if k not in REPORT_HASHES}
    areas,enclosure=measure_anatomical_safety(bpy,root,base,collector_factory=factory)
    inspectors=[c.inspector for c in collectors if c.inspector is not None]
    if len(inspectors)!=(2 if enclosure['paired'] else 1):raise ValueError('Missing complete anatomical frame traversal')
    full={'schema_version':1,'policy':POLICY,'bindings':base,'source_frame_count':enclosure['source_frame_count'],
        'paired':enclosure['paired'],'polygon_topology_sha256':areas['polygon_topology_sha256'],
        'original':{'frames':inspectors[0].complete_rows},
        'fitted':{'frames':inspectors[1].complete_rows} if enclosure['paired'] else None,
        'originals_unchanged':True,**FLAGS}
    return areas,enclosure,full


def require_unchanged(root,options):
    unchanged(root,options)
    for name,(key,_) in REPORTS.items():
        if key in options:
            path=root/name
            if path.is_symlink() or not path.is_file() or digest(path)!=options[key]:
                raise ValueError('Complete anatomy changed a bound report: '+name)


def inspect_complete(bpy,root,options):
    if any((root/name).exists() or (root/name).is_symlink() for name in REPORTS):
        raise ValueError('Refuse to replace complete anatomical evidence')
    require_unchanged(root,options);data=measure_complete(bpy,root,options)
    payloads=[json.dumps(report,allow_nan=False,separators=(',',':')).encode() for report in data]
    # Check every bound before creating any of the three output files.
    if any(len(payload)>limit for payload,(_,limit) in zip(payloads,REPORTS.values())):
        raise ValueError('Complete anatomical evidence exceeds bounded size; no truncation')
    records=[]
    for name,payload in zip(REPORTS,payloads):
        with (root/name).open('xb') as stream:stream.write(payload)
        records.append({'name':name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()})
    require_unchanged(root,options)
    return {'status':'REAL_COMPLETE_ANATOMICAL_SAFETY_MEASURED','bindings':dict(options),
        'frames':data[2]['source_frame_count'],'report':records[0],'enclosure_report':records[1],
        'full_trunk_report':records[2],'originals_unchanged':True,**FLAGS}


def verify_complete(bpy,root,options):
    require_unchanged(root,options)
    expected=tuple(read_json(root/name,options[key],limit) for name,(key,limit) in REPORTS.items())
    actual=measure_complete(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh complete anatomical surface/enclosure evidence differs')
    require_unchanged(root,options)
    return {'status':'REAL_COMPLETE_ANATOMICAL_SAFETY_VERIFIED','bindings':dict(options),
        'frames_verified':actual[2]['source_frame_count'],'paired':actual[2]['paired'],'originals_unchanged':True,**FLAGS}
