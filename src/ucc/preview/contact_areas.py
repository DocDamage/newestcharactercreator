"""Compare stable mesh-face contact areas across changing triangle splits."""
from dataclasses import dataclass
from hashlib import sha256
import json
import struct

from ucc.core.errors import ValidationError
from ucc.jobs.native_fit_evidence import FLAGS,read_json_record
from .body_contacts import BodyContacts,validate_body_measurement,validate_body_receipt,parse_body_contacts

POLICY='STATIC_EVALUATED_POLYGON_CONTACT_AREAS_V1'
REASONS={'BODY_CONTACTS_UNAVAILABLE','POLYGON_BUDGET_EXCEEDED','POLYGON_TOPOLOGY_CHANGED'}


@dataclass(frozen=True,slots=True)
class BodyContactAreas:
    contacts: BodyContacts
    status: str
    reason: str
    polygon_sha256: str | None
    original: tuple[frozenset[int],...] | None
    fitted: tuple[frozenset[int],...] | None
    new_area_frames: tuple[int,...] | None
    more_hand_pair_frames: tuple[int,...] | None


def polygon_membership(polygons,vertex_count):
    if type(polygons) is not list or not 1<=len(polygons)<=100000:
        raise ValidationError('Stable body areas require a bounded complete polygon list')
    membership={};seen=set();total=0
    for index,face in enumerate(polygons):
        if (type(face) is not list or not 3<=len(face)<=64 or
            any(type(v) is not int or not 0<=v<vertex_count for v in face) or len(set(face))!=len(face)):
            raise ValidationError('Invalid stable body polygon vertices')
        key=tuple(sorted(face));total+=len(face)
        if key in seen or total>1000000:raise ValidationError('Duplicate or excessive stable body polygons')
        seen.add(key)
        for vertex in face:membership.setdefault(vertex,set()).add(index)
    return membership


def contact_polygons(cache,surface,membership,*,cancel_check=lambda:None):
    """Resolve each actual highlighted triangle through its vertex identities.

    Global triangle numbers can change when Blender triangulates a posed quad
    differently. Original polygon vertex membership is invariant and audited.
    """
    areas=[]
    for frame,triangles in enumerate(surface.triangles):
        cancel_check();indices=cache.frame(frame)[1];faces=set()
        for triangle in triangles:
            vertices=struct.unpack_from('<III',indices,triangle*12)
            candidates=set.intersection(*(membership.get(v,set()) for v in vertices))
            if len(candidates)!=1:raise ValidationError('Highlighted triangle has missing or ambiguous stable polygon identity')
            faces.update(candidates)
        areas.append(frozenset(faces))
    return tuple(areas)


def read_body_contact_areas(folder,report,verification,bindings,baseline,profile,original_cache,*,fitted_timeline=None,
                            fitted_cache=None,cancel_check=lambda:None) -> BodyContactAreas:
    paired=fitted_timeline is not None
    validate_body_measurement(report,bindings,baseline,paired)
    validate_body_receipt(verification,bindings,baseline,paired,report['report']['sha256'])
    data,_=read_json_record(folder,report['report'],'body_contacts.json',40*1024*1024,cancel_check=cancel_check)
    return parse_body_contact_areas(data,bindings,baseline,profile,original_cache,fitted_timeline=fitted_timeline,
        fitted_cache=fitted_cache,cancel_check=cancel_check)


def parse_body_contact_areas(data,bindings,baseline,profile,original_cache,*,fitted_timeline=None,
                             fitted_cache=None,cancel_check=lambda:None) -> BodyContactAreas:
    paired=fitted_timeline is not None
    fields={'schema_version','policy','status','reason','bindings','body_contacts','polygons','polygon_topology_sha256','originals_unchanged'}|FLAGS
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        data['policy']!=POLICY or type(data['status']) is not str or data['status'] not in {'CHECKED','UNAVAILABLE'} or
        data['bindings']!=bindings or data['originals_unchanged'] is not True or any(data[k] is not False for k in FLAGS) or
        type(data['reason']) is not str or (data['reason']!='' if data['status']=='CHECKED' else data['reason'] not in REASONS)):
        raise ValidationError('Stable body area policy, provenance or approval differs')
    contacts=parse_body_contacts(data['body_contacts'],bindings,baseline,profile,original_cache,fitted_timeline=fitted_timeline,
        fitted_cache=fitted_cache,cancel_check=cancel_check)
    if data['status']=='UNAVAILABLE':
        if data['polygons']!=[] or data['polygon_topology_sha256'] is not None:
            raise ValidationError('Unavailable body areas contain a partial face verdict')
        if data['reason']=='BODY_CONTACTS_UNAVAILABLE' and contacts.original.status=='CHECKED' and (not paired or contacts.fitted.status=='CHECKED'):
            raise ValidationError('Body-area unavailable reason contradicts contact inspection')
        return BodyContactAreas(contacts,'UNAVAILABLE',data['reason'],None,None,None,None,None)
    if contacts.original.status!='CHECKED' or (paired and contacts.fitted.status!='CHECKED'):
        raise ValidationError('Stable body areas require complete checked contact observations')
    membership=polygon_membership(data['polygons'],original_cache.vertex_count)
    digest=sha256(json.dumps(data['polygons'],separators=(',',':')).encode()).hexdigest()
    if data['polygon_topology_sha256']!=digest:raise ValidationError('Stable body polygon topology SHA differs')
    original=contact_polygons(original_cache,contacts.original,membership,cancel_check=cancel_check)
    fitted=contact_polygons(fitted_cache,contacts.fitted,membership,cancel_check=cancel_check) if paired else None
    new=tuple(i for i,(a,b) in enumerate(zip(original,fitted)) if b-a) if paired else None
    more=tuple(i for i,(a,b) in enumerate(zip(contacts.original.pairs,contacts.fitted.pairs)) if any(y>x for x,y in zip(a,b))) if paired else None
    return BodyContactAreas(contacts,'CHECKED','',digest,original,fitted,new,more)
