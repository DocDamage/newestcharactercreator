"""One fresh Action traversal measures both stable surface areas and enclosure."""
from hashlib import sha256
import json

from blender_bridge.body_contact_areas import AreaInspector,area_report,MAX_REPORT as AREA_LIMIT
from blender_bridge.body_contact_review import BodyCollector,FLAGS,SOURCE_FIELDS,FIT_FIELDS,measure_body_contacts,unchanged
from blender_bridge.body_contact_regions import weighted_central_region
from blender_bridge.central_regions import volume_regions
from blender_bridge.central_enclosure import observe_central_enclosure,POLICY
from blender_bridge.native_inputs import read_json
from blender_bridge.native_review_reopen import digest

MAX_REPORT=64*1024*1024
OPERATIONS={kind+'_'+variant+'_anatomical_safety':(FIT_FIELDS if variant=='fitted' else SOURCE_FIELDS)|
    ({'body_review_sha256','enclosure_review_sha256'} if kind=='verify' else set())
    for kind in ('inspect','verify') for variant in ('native','fitted')}


def checked_anatomical_job(job):
    options=job['options'];fields=OPERATIONS[job['operation']]
    if 'fitted_sha256' in fields:
        from blender_bridge.native_symmetric_policy import layer_fields
        fields=layer_fields(fields,options)
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Anatomical review requires exact hashes and fixed staged inputs')
    return options


class AnatomicalInspector(AreaInspector):
    def __init__(self,profile,rig,human):
        super().__init__(profile,rig,human)
        self.volume_regions,self.limb_roots=volume_regions(profile,self.parents,self.deform)
        self.volume_vertices=None;self.enclosure_rows=[]

    def inspect(self,mesh,frame,skin,triangles):
        super().inspect(mesh,frame,skin,triangles)
        if self.status!='CHECKED' or self.area_reason:raise ValueError('COMPLETE_ANATOMICAL_SURFACES_REQUIRED')
        if self.volume_vertices is None:
            names={g.index:g.name for g in self.human.vertex_groups};self.volume_vertices={k:set() for k in self.volume_regions}
            for vertex in mesh.vertices:
                region=weighted_central_region({names[g.group]:g.weight for g in vertex.groups},self.volume_regions,self.deform)
                if region is not None:self.volume_vertices[region].add(vertex.index)
            if not all(self.volume_vertices.values()):raise ValueError('COMPLETE_ANATOMICAL_WEIGHTED_REGIONS_REQUIRED')
        observation=observe_central_enclosure([tuple(v.co) for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],
            [t.polygon_index for t in mesh.loop_triangles],self.polygons,self.volume_vertices['central_body'],
            {s:self.volume_vertices[s+'_hand'] for s in ('left','right')},tuple(self.world))
        self.enclosure_rows.append({'frame':frame,'skin_sha256':skin,'triangle_sha256':triangles,'observation':observation})

    def enclosure_report(self):
        return {'world_matrix':self.world,'limb_roots':self.limb_roots,
            'region_bones':{k:sorted(v) for k,v in self.volume_regions.items()},
            'region_vertex_ids':{k:sorted(v) for k,v in self.volume_vertices.items()},'frames':self.enclosure_rows}


class AnatomicalCollector(BodyCollector):
    def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
        if self.inspector is None:self.inspector=AnatomicalInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,triangles)


def measure_anatomical_safety(bpy,root,options,*,collector_factory=AnatomicalCollector):
    collectors=[]
    def factory(profile):
        collector=collector_factory(profile);collectors.append(collector);return collector
    base={k:v for k,v in options.items() if k not in {'body_review_sha256','enclosure_review_sha256'}}
    contacts=measure_body_contacts(bpy,root,base,collector_factory=factory)
    inspectors=[c.inspector for c in collectors if c.inspector is not None]
    areas=area_report(contacts,inspectors)
    enclosure={'schema_version':1,'policy':POLICY,'bindings':base,'source_frame_count':contacts['source_frame_count'],
        'paired':contacts['paired'],'polygon_topology_sha256':areas['polygon_topology_sha256'],
        'original':inspectors[0].enclosure_report(),'fitted':inspectors[1].enclosure_report() if contacts['paired'] else None,
        'originals_unchanged':True,**FLAGS}
    return areas,enclosure


def _unchanged(root,options):
    unchanged(root,options)
    if 'enclosure_review_sha256' in options:
        path=root/'central_enclosure.json'
        if path.is_symlink() or not path.is_file() or digest(path)!=options['enclosure_review_sha256']:
            raise ValueError('Anatomical review changed bound enclosure evidence')


def inspect_anatomical_safety(bpy,root,options):
    names=('body_contacts.json','central_enclosure.json')
    if any((root/n).exists() or (root/n).is_symlink() for n in names):raise ValueError('Refuse to replace anatomical evidence')
    _unchanged(root,options);data=measure_anatomical_safety(bpy,root,options);records=[]
    for name,report,limit in zip(names,data,(AREA_LIMIT,MAX_REPORT)):
        payload=json.dumps(report,allow_nan=False,separators=(',',':')).encode()
        if len(payload)>limit:raise ValueError('Complete anatomical evidence exceeds bounded size; no truncation')
        with (root/name).open('xb') as stream:stream.write(payload)
        records.append({'name':name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()})
    _unchanged(root,options)
    return {'status':'REAL_ANATOMICAL_SAFETY_MEASURED','bindings':dict(options),'frames':data[1]['source_frame_count'],
        'report':records[0],'enclosure_report':records[1],'originals_unchanged':True,**FLAGS}


def verify_anatomical_safety(bpy,root,options):
    _unchanged(root,options)
    expected=(read_json(root/'body_contacts.json',options['body_review_sha256'],AREA_LIMIT),
              read_json(root/'central_enclosure.json',options['enclosure_review_sha256'],MAX_REPORT))
    actual=measure_anatomical_safety(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh anatomical surface/enclosure evidence differs')
    _unchanged(root,options)
    return {'status':'REAL_ANATOMICAL_SAFETY_VERIFIED','bindings':dict(options),'frames_verified':actual[1]['source_frame_count'],
        'paired':actual[1]['paired'],'originals_unchanged':True,**FLAGS}
