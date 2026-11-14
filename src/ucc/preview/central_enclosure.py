"""Strict reproduced trunk-enclosure intake, with independent cache geometry."""
from dataclasses import dataclass
from hashlib import sha256
import struct

from ucc.core.errors import ValidationError
from ucc.jobs.native_fit_evidence import FLAGS,read_json_record
from .central_metrics import require_metrics
from .central_scope import expected_volume_regions,checked_ids
from .contact_areas import polygon_membership

POLICY='MEASURED_TRUNK_CAP_FREE_HAND_ENCLOSURE_V1'


@dataclass(frozen=True,slots=True)
class EnclosureVariant:
    inside: tuple[tuple[frozenset[int],frozenset[int]],...]
    ambiguous: tuple[tuple[frozenset[int],frozenset[int]],...]


@dataclass(frozen=True,slots=True)
class CentralEnclosure:
    original: EnclosureVariant
    fitted: EnclosureVariant | None


def validate_anatomical_measurement(report,bindings,baseline,paired):
    from .body_contacts import validate_body_measurement
    if type(report) is not dict or 'enclosure_report' not in report:raise ValidationError('Missing enclosure evidence record')
    validate_body_measurement({k:v for k,v in report.items() if k!='enclosure_report'},bindings,baseline,paired,
        expected_status='REAL_ANATOMICAL_SAFETY_MEASURED')


def validate_anatomical_receipt(receipt,bindings,baseline,paired,report):
    fields={'status','bindings','frames_verified','paired','originals_unchanged'}|FLAGS
    if (type(receipt) is not dict or set(receipt)!=fields or receipt['status']!='REAL_ANATOMICAL_SAFETY_VERIFIED' or
        receipt['bindings']!={**bindings,'body_review_sha256':report['report']['sha256'],
                             'enclosure_review_sha256':report['enclosure_report']['sha256']} or
        type(receipt['frames_verified']) is not int or receipt['frames_verified']!=baseline['source_frame_count'] or
        receipt['paired'] is not paired or receipt['originals_unchanged'] is not True or any(receipt[k] is not False for k in FLAGS)):
        raise ValidationError('Anatomical evidence was not independently reproduced together')


def _variant(data,cache,body,polygons,profile,*,cancel_check=lambda:None):
    fields={'world_matrix','limb_roots','region_bones','region_vertex_ids','frames'}
    if (type(data) is not dict or set(data)!=fields or data['world_matrix']!=list(cache.world_matrix) or
        any(type(v) not in (int,float) for v in data['world_matrix']) or
        type(data['frames']) is not list or len(data['frames'])!=cache.frame_count):
        raise ValidationError('Enclosure transform or complete frame coverage differs')
    regions,roots=expected_volume_regions(profile,body['parents'],set(body['deform_bones']))
    if data['region_bones']!=regions or data['limb_roots']!=roots:raise ValidationError('Enclosure mapped branch identity differs')
    members=data['region_vertex_ids']
    if type(members) is not dict or set(members)!=set(regions):raise ValidationError('Enclosure weighted partition missing')
    groups={k:checked_ids(v,cache.vertex_count,nonempty=True) for k,v in members.items()}
    if any(groups[a]&groups[b] for a in groups for b in groups if a<b):raise ValidationError('Enclosure weighted regions overlap')
    for side in ('left','right'):
        if len(groups[side+'_hand'])!=body['region_vertex_counts'][side+'_hand']:
            raise ValidationError('Enclosure hand membership differs from independently measured surface region')
    membership=polygon_membership(polygons,cache.vertex_count)
    body_polygons={i for i,p in enumerate(polygons) if set(p)<=groups['central_body']}
    inside=[];ambiguous=[]
    for index,(row,reference) in enumerate(zip(data['frames'],body['frames'])):
        cancel_check();vertices,indices=cache.frame(index);triangles=list(struct.iter_unpack('<III',indices))
        if (type(row) is not dict or set(row)!={'frame','skin_sha256','triangle_sha256','observation'} or
            type(row['frame']) is not int or row['frame']!=index+1 or
            any(row[k]!=reference[k] for k in ('frame','skin_sha256','triangle_sha256')) or
            sha256(indices).hexdigest()!=row['triangle_sha256']):
            raise ValidationError('Enclosure pose/skin/topology differs from verified body playback')
        polygon_ids=[]
        for tri in triangles:
            candidates=set.intersection(*(membership.get(v,set()) for v in tri))
            if len(candidates)!=1:raise ValidationError('Enclosure triangle lacks a unique actual polygon')
            polygon_ids.append(next(iter(candidates)))
        counts={}
        for poly in polygon_ids:counts[poly]=counts.get(poly,0)+1
        if any(counts.get(i)!=len(p)-2 for i,p in enumerate(polygons)):
            raise ValidationError('Enclosure omits polygon triangulation')
        obs=row['observation']
        fields={'diagonal_world','offset_world','signed_volume_world','pivot_local','origin_world','bounds','cap_boxes','boundaries',
                'body_triangle_ids','body_surface_audit','ray_queries','left','right'}
        if type(obs) is not dict or set(obs)!=fields:raise ValidationError('Incomplete enclosure observation')
        ids=checked_ids(obs['body_triangle_ids'],cache.triangle_count,nonempty=True)
        if ids!={i for i,p in enumerate(polygon_ids) if p in body_polygons}:
            raise ValidationError('Enclosure body selection is not the complete weighted polygon patch')
        require_metrics(obs,cache,index,ids,triangles,cancel_check=cancel_check)
        nz=[];unknown=[];hands=[];nonzero_count=0
        for side in ('left','right'):
            hit=obs[side]
            if type(hit) is not dict or set(hit)!={'selected_triangles','nonzero_triangles','ambiguous_triangles',
                                                 'inside_polygons','ambiguous_polygons','classification_sha256'}:
                raise ValidationError('Incomplete enclosure hand verdict')
            selected,nonzero,uncertain=(checked_ids(hit[k],cache.triangle_count,limit=10000) for k in
                                       ('selected_triangles','nonzero_triangles','ambiguous_triangles'))
            expected={i for i,t in enumerate(triangles) if set(t)<=groups[side+'_hand']}
            if not selected or selected!=expected or not nonzero<=selected or not uncertain<=selected or nonzero&uncertain:
                raise ValidationError('Enclosure hand selection or uncertain verdict differs')
            nonzero_count+=len(nonzero)
            trace=sha256()
            for ti in sorted(selected):trace.update(struct.pack('<IB',ti,1 if ti in nonzero else 2 if ti in uncertain else 0))
            if hit['classification_sha256']!=trace.hexdigest():raise ValidationError('Enclosure classification digest differs')
            for key,tri_ids in (('inside_polygons',nonzero),('ambiguous_polygons',uncertain)):
                polys=checked_ids(hit[key],len(polygons))
                if polys!={polygon_ids[i] for i in tri_ids}:raise ValidationError('Enclosure stable polygon verdict differs')
            nz.append(frozenset(hit['inside_polygons']));unknown.append(frozenset(hit['ambiguous_polygons']));hands.append(selected)
        queries=obs['ray_queries']
        if hands[0]&hands[1] or type(queries) is not int or not 6*nonzero_count<=queries<=1000000:
            raise ValidationError('Enclosure hand separation or fixed ray workload differs')
        inside.append(tuple(nz));ambiguous.append(tuple(unknown))
    return EnclosureVariant(tuple(inside),tuple(ambiguous))


def read_central_enclosure(folder,report,receipt,bindings,baseline,profile,original_cache,areas_data,*,fitted_cache=None,
                           cancel_check=lambda:None):
    paired=fitted_cache is not None
    validate_anatomical_measurement(report,bindings,baseline,paired)
    validate_anatomical_receipt(receipt,bindings,baseline,paired,report)
    data,_=read_json_record(folder,report['enclosure_report'],'central_enclosure.json',64*1024*1024,cancel_check=cancel_check)
    fields={'schema_version','policy','bindings','source_frame_count','paired','polygon_topology_sha256',
            'original','fitted','originals_unchanged'}|FLAGS
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        data['policy']!=POLICY or data['bindings']!=bindings or data['paired'] is not paired or
        type(data['source_frame_count']) is not int or data['source_frame_count']!=baseline['source_frame_count'] or
        data['polygon_topology_sha256']!=areas_data['polygon_topology_sha256'] or data['originals_unchanged'] is not True or
        any(data[k] is not False for k in FLAGS) or areas_data['status']!='CHECKED'):
        raise ValidationError('Enclosure policy, provenance, scope or approval differs')
    bodies=areas_data['body_contacts'];polygons=areas_data['polygons']
    original=_variant(data['original'],original_cache,bodies['original'],polygons,profile,cancel_check=cancel_check)
    fitted=None
    if paired:
        fitted=_variant(data['fitted'],fitted_cache,bodies['fitted'],polygons,profile,cancel_check=cancel_check)
        for key in ('world_matrix','limb_roots','region_bones','region_vertex_ids'):
            if data['original'][key]!=data['fitted'][key]:raise ValidationError('Fitted enclosure changed anatomical membership')
    elif data['fitted'] is not None:raise ValidationError('Undeclared fitted enclosure')
    return CentralEnclosure(original,fitted)
