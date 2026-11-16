"""Read-only full-timeline central-body observations and independent reproduction."""
from array import array
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
from typing import Any

from blender_bridge.native_body_contacts import BodyContactInspector
from blender_bridge.body_contact_regions import POLICY
from blender_bridge.native_fit_measure import measure_saved_fit
from blender_bridge.native_fit_policy import BASE_HASHES
from blender_bridge.native_review_reopen import reopen_native,digest
from blender_bridge.native_inputs import read_json,validate_profile

SOURCE_FIELDS=BASE_HASHES
FIT_FIELDS=BASE_HASHES|{'fit_sha256','fitted_sha256','fit_report_sha256'}
OPERATIONS={'inspect_native_body_contacts':SOURCE_FIELDS,'verify_native_body_contacts':SOURCE_FIELDS|{'body_review_sha256'},
            'inspect_fitted_body_contacts':FIT_FIELDS,'verify_fitted_body_contacts':FIT_FIELDS|{'body_review_sha256'}}
MAX_REPORT=32*1024*1024
FLAGS={'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}


def checked_body_job(job: dict) -> dict:
    options=job['options'];fields=OPERATIONS[job['operation']]
    if 'fitted_sha256' in fields:
        from blender_bridge.native_symmetric_policy import layer_fields
        fields=layer_fields(fields,options)
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Body contact review requires exact hashes and fixed staged filenames')
    return options


def input_hashes(options: dict) -> dict:
    files={'candidate.blend':'master_sha256','review_motion.blend':'review_sha256','target_timeline.json':'timeline_sha256',
           'native_mapping.json':'mapping_sha256','source_snapshot.json':'snapshot_sha256'}
    if 'fitted_sha256' in options:files.update({'contact_fit.json':'fit_sha256','fitted_motion.blend':'fitted_sha256','fitted_timeline.json':'fit_report_sha256'})
    if 'body_review_sha256' in options:files['body_contacts.json']='body_review_sha256'
    if 'base_fit_policy_sha256' in options:
        files.update({'base_contact_fit.json':'base_fit_policy_sha256','base_fitted_motion.blend':'base_fitted_sha256',
                      'base_fitted_timeline.json':'base_fit_report_sha256'})
    return {n:options[k] for n,k in files.items()}


def unchanged(root,options):
    for name,expected in input_hashes(options).items():
        path=root/name
        if path.is_symlink() or not path.is_file() or digest(path)!=expected:
            raise ValueError('Body contact review changed a bound original: '+name)


class BodyCollector:
    def __init__(self,profile):self.profile=profile;self.inspector=None

    def source_frame(self,bpy,human,rig,frame,skin):
        bpy.context.view_layer.update();graph=bpy.context.evaluated_depsgraph_get();evaluated=human.evaluated_get(graph)
        mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        try:
            mesh.calc_loop_triangles();actual=sha256()
            for vertex in mesh.vertices:actual.update(struct.pack('<qqq',*(round(v*1000000) for v in vertex.co)))
            if actual.hexdigest()!=skin:raise ValueError('Body inspection does not reproduce the verified original skin')
            indices=array('I',[0])*(len(mesh.loop_triangles)*3);mesh.loop_triangles.foreach_get('vertices',indices)
            if sys.byteorder!='little':indices.byteswap()
            self.fitted_frame(bpy,human,rig,mesh,frame,skin,sha256(indices.tobytes()).hexdigest())
        finally:evaluated.to_mesh_clear()

    def fitted_frame(self,bpy,human,rig,mesh,frame,skin,triangles):
        if self.inspector is None:self.inspector=BodyContactInspector(self.profile,rig,human)
        self.inspector.inspect(mesh,frame,skin,triangles)


def body_report(baseline,base,source,fitted,reopened):
    count=baseline['source_frame_count'];paired=fitted is not None
    if source is None or len(source.rows)!=count or (paired and len(fitted.rows)!=count):
        raise ValueError('Body contact inspection did not cover every saved frame')
    return {'schema_version':1,'policy':POLICY,'measurement':'FRESH_SAVED_ACTION_BODY_SURFACES_V1','bindings':base,
        'paired':paired,'source_frame_count':count,'source_first_frame':baseline['source_first_frame'],'fps':baseline['fps'],
        'original':source.report(),'fitted':fitted.report() if paired else None,
        'original_review_verification':reopened,'fitted_frames_verified':count if paired else 0,
        'originals_unchanged':True,**FLAGS}


def measure_body_contacts(bpy: Any,root: Path,options: dict,*,collector_factory=BodyCollector) -> dict:
    base={k:v for k,v in options.items() if k!='body_review_sha256'}
    unchanged(root,options)
    try:
        baseline=read_json(root/'target_timeline.json',base['timeline_sha256'],64*1024*1024)
        profile=validate_profile(read_json(root/'native_mapping.json',base['mapping_sha256'],64*1024),
            base['source_sha256'],base['snapshot_sha256'],base['master_sha256'])
        source=collector_factory(profile);fitted=collector_factory(profile);paired='fitted_sha256' in base
        if paired:
            actual=measure_saved_fit(bpy,root,base,source_frame_observer=source.source_frame,fitted_frame_observer=fitted.fitted_frame)
            expected=read_json(root/'fitted_timeline.json',base['fit_report_sha256'],64*1024*1024)
            if actual!=expected:raise ValueError('Body review fitted geometry differs from its canonical saved Action')
            reopened=actual['original_review_verification']
        else:reopened=reopen_native(bpy,root,base,frame_observer=source.source_frame)
        count=baseline['source_frame_count']
        if source.inspector is None or len(source.inspector.rows)!=count or (paired and (fitted.inspector is None or len(fitted.inspector.rows)!=count)):
            raise ValueError('Body contact inspection did not cover every saved frame')
        return body_report(baseline,base,source.inspector,fitted.inspector if paired else None,reopened)
    finally:unchanged(root,options)


def inspect_body_contacts(bpy,root,options):
    output=root/'body_contacts.json'
    if output.exists() or output.is_symlink():raise ValueError('Refuse to replace body contact observations')
    data=measure_body_contacts(bpy,root,options);payload=json.dumps(data,allow_nan=False,separators=(',',':')).encode()
    if len(payload)>MAX_REPORT:raise ValueError('Complete body review exceeds bounded size; no truncation')
    with output.open('xb') as stream:stream.write(payload)
    return {'status':'REAL_NATIVE_BODY_CONTACTS_MEASURED','bindings':dict(options),'frames':data['source_frame_count'],
            'report':{'name':output.name,'bytes':len(payload),'sha256':sha256(payload).hexdigest()},'originals_unchanged':True,**FLAGS}


def verify_body_contacts(bpy,root,options):
    expected=read_json(root/'body_contacts.json',options['body_review_sha256'],MAX_REPORT)
    actual=measure_body_contacts(bpy,root,options)
    if actual!=expected:raise ValueError('Fresh saved-scene central-body contacts/topology differ')
    return {'status':'REAL_NATIVE_BODY_CONTACTS_VERIFIED','bindings':dict(options),'frames_verified':actual['source_frame_count'],
            'paired':actual['paired'],'originals_unchanged':True,**FLAGS}
