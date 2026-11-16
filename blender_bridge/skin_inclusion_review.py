"""Read-only saved-Action skin-inclusion observations with fresh reproduction."""
from hashlib import sha256
import json

from blender_bridge.body_contact_review import BodyCollector,FLAGS,SOURCE_FIELDS,FIT_FIELDS,measure_body_contacts,unchanged
from blender_bridge.body_contact_regions import REGIONS,weighted_central_region
from blender_bridge.native_body_contacts import BodyContactInspector
from blender_bridge.native_inputs import read_json
from blender_bridge.skin_winding import observe_hand_skin,POLICY

MAX_REPORT=64*1024*1024
OPERATIONS={
    'inspect_native_skin_inclusion':SOURCE_FIELDS,'verify_native_skin_inclusion':SOURCE_FIELDS|{'body_review_sha256'},
    'inspect_fitted_skin_inclusion':FIT_FIELDS,'verify_fitted_skin_inclusion':FIT_FIELDS|{'body_review_sha256'}}
REASONS={'CENTRAL_BRANCH_UNAVAILABLE','WEIGHTED_REGIONS_UNAVAILABLE','SKIN_GEOMETRY_BUDGET','SKIN_INVALID_GEOMETRY',
    'SKIN_DEGENERATE_GEOMETRY','SKIN_DUPLICATE_FACE','SKIN_OPEN_OR_UNORIENTED','SKIN_NONMANIFOLD_VERTEX',
    'SKIN_UNSUPPORTED_TOPOLOGY','SKIN_NONPOSITIVE_VOLUME','SKIN_HAND_SELECTION_BUDGET','SKIN_HAND_SELECTION_OVERLAP','SKIN_RAY_BUDGET'}


def checked_skin_job(job):
    options=job['options'];fields=OPERATIONS[job['operation']]
    if 'fitted_sha256' in fields:
        from blender_bridge.native_symmetric_policy import layer_fields
        fields=layer_fields(fields,options)
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Skin inclusion requires exact hashes and fixed staged inputs')
    return options


class SkinInspector(BodyContactInspector):
    def unavailable(self,reason):
        self.status='UNAVAILABLE';self.reason=reason
        for row in self.rows:row['observation']=None

    def inspect(self,mesh,frame,skin_sha,triangle_sha):
        row={'frame':frame,'skin_sha256':skin_sha,'triangle_sha256':triangle_sha,'observation':None}
        if [float(v) for line in self.human.matrix_world for v in line]!=self.world:
            raise ValueError('Skin inclusion world transform changed')
        if self.status=='CHECKED':
            try:
                if self.vertices is None:
                    names={g.index:g.name for g in self.human.vertex_groups};self.vertices={k:set() for k in REGIONS}
                    for vertex in mesh.vertices:
                        region=weighted_central_region({names[g.group]:g.weight for g in vertex.groups},self.regions,self.deform)
                        if region is not None:self.vertices[region].add(vertex.index)
                    self.counts={k:len(v) for k,v in self.vertices.items()}
                    if not all(self.counts.values()):raise ValueError('WEIGHTED_REGIONS_UNAVAILABLE')
                points=[tuple(self.human.matrix_world@v.co) for v in mesh.vertices]
                triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
                hands={s:self.vertices[s+'_hand'] for s in ('left','right')}
                row['observation']=observe_hand_skin(points,triangles,hands)
            except ValueError as error:
                if str(error) not in REASONS:raise
                self.unavailable(str(error))
        self.rows.append(row)

    def report(self):
        data=super().report();data['policy']=POLICY
        return data


class SkinCollector(BodyCollector):
    def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
        if self.inspector is None:self.inspector=SkinInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,triangles)


def measure_skin(bpy,root,options):
    data=measure_body_contacts(bpy,root,options,collector_factory=SkinCollector)
    data['policy']=POLICY;data['measurement']='FRESH_SAVED_ACTION_CLOSED_SKIN_V1'
    return data


def inspect_skin(bpy,root,options):
    output=root/'body_contacts.json'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace skin inclusion observations')
    data=measure_skin(bpy,root,options);payload=json.dumps(data,allow_nan=False,separators=(',',':')).encode()
    if len(payload)>MAX_REPORT:raise ValueError('Complete skin inclusion exceeds bounded report; no truncation')
    with output.open('xb') as stream:stream.write(payload)
    return {'status':'REAL_NATIVE_SKIN_INCLUSION_MEASURED','bindings':dict(options),'frames':data['source_frame_count'],
        'report':{'name':output.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},'originals_unchanged':True,**FLAGS}


def verify_skin(bpy,root,options):
    expected=read_json(root/'body_contacts.json',options['body_review_sha256'],MAX_REPORT)
    actual=measure_skin(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh saved-scene closed-skin observations differ')
    unchanged(root,options)
    return {'status':'REAL_NATIVE_SKIN_INCLUSION_VERIFIED','bindings':dict(options),'frames_verified':actual['source_frame_count'],
        'paired':actual['paired'],'originals_unchanged':True,**FLAGS}
