"""Stable evaluated-face intake alongside independently reproduced body contacts."""
from hashlib import sha256
import json

from blender_bridge.body_contact_review import (
    BodyCollector,FLAGS,SOURCE_FIELDS,FIT_FIELDS,measure_body_contacts,unchanged,
)
from blender_bridge.native_body_contacts import BodyContactInspector
from blender_bridge.native_inputs import read_json

POLICY='STATIC_EVALUATED_POLYGON_CONTACT_AREAS_V1'
MAX_REPORT=40*1024*1024
OPERATIONS={'inspect_native_body_areas':SOURCE_FIELDS,'verify_native_body_areas':SOURCE_FIELDS|{'body_review_sha256'},
            'inspect_fitted_body_areas':FIT_FIELDS,'verify_fitted_body_areas':FIT_FIELDS|{'body_review_sha256'}}


def checked_area_job(job):
    fields=OPERATIONS[job['operation']];options=job['options']
    if 'fitted_sha256' in fields:
        from blender_bridge.native_symmetric_policy import layer_fields
        fields=layer_fields(fields,options)
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Body contact areas require exact hashes and fixed staged inputs')
    return options


class AreaInspector(BodyContactInspector):
    def __init__(self,*args):
        super().__init__(*args);self.polygons=None;self.polygon_sha=None;self.area_reason=''

    def inspect(self,mesh,*args):
        super().inspect(mesh,*args)
        if self.area_reason:return
        if len(mesh.polygons)>100000 or len(mesh.loops)>1000000:
            self.area_reason='POLYGON_BUDGET_EXCEEDED';return
        polygons=[list(p.vertices) for p in mesh.polygons]
        digest=sha256(json.dumps(polygons,separators=(',',':')).encode()).hexdigest()
        if self.polygons is None:self.polygons=polygons;self.polygon_sha=digest
        elif digest!=self.polygon_sha:self.area_reason='POLYGON_TOPOLOGY_CHANGED'


class AreaCollector(BodyCollector):
    def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
        if self.inspector is None:self.inspector=AreaInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,triangles)


def area_report(contacts,inspectors):
    source=inspectors[0];reason=''
    if any(i.status!='CHECKED' for i in inspectors):reason='BODY_CONTACTS_UNAVAILABLE'
    elif any(i.area_reason for i in inspectors):reason=next(i.area_reason for i in inspectors if i.area_reason)
    elif any(i.polygons!=source.polygons for i in inspectors):reason='POLYGON_TOPOLOGY_CHANGED'
    return {'schema_version':1,'policy':POLICY,'status':'UNAVAILABLE' if reason else 'CHECKED','reason':reason,
        'bindings':dict(contacts['bindings']),'body_contacts':contacts,'polygons':[] if reason else source.polygons,
        'polygon_topology_sha256':None if reason else source.polygon_sha,'originals_unchanged':True,**FLAGS}


def measure_body_areas(bpy,root,options):
    collectors=[]
    def factory(profile):
        collector=AreaCollector(profile);collectors.append(collector);return collector
    contacts=measure_body_contacts(bpy,root,options,collector_factory=factory)
    return area_report(contacts,[c.inspector for c in collectors if c.inspector is not None])


def inspect_body_areas(bpy,root,options):
    output=root/'body_contacts.json'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace body contact areas')
    data=measure_body_areas(bpy,root,options);payload=json.dumps(data,allow_nan=False,separators=(',',':')).encode()
    if len(payload)>MAX_REPORT:raise ValueError('Complete body contact areas exceed bounded size; no truncation')
    with output.open('xb') as stream:stream.write(payload)
    return {'status':'REAL_NATIVE_BODY_CONTACTS_MEASURED','bindings':dict(options),'frames':data['body_contacts']['source_frame_count'],
        'report':{'name':output.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},'originals_unchanged':True,**FLAGS}


def verify_body_areas(bpy,root,options):
    expected=read_json(root/'body_contacts.json',options['body_review_sha256'],MAX_REPORT)
    actual=measure_body_areas(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh saved-scene stable contact areas differ')
    unchanged(root,options);contacts=actual['body_contacts']
    return {'status':'REAL_NATIVE_BODY_CONTACTS_VERIFIED','bindings':dict(options),'frames_verified':contacts['source_frame_count'],
        'paired':contacts['paired'],'originals_unchanged':True,**FLAGS}
