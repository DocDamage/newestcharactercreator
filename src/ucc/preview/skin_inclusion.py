"""Strict intake of reproduced outward-hand winding, separate from contact pairs."""
from dataclasses import dataclass
from hashlib import sha256
import math
import struct

from ucc.core.errors import ValidationError
from ucc.jobs.native_fit_evidence import FLAGS,read_json_record
from ucc.jobs.native_skin_evidence import validate_reopen_report
from .body_contacts import HASHES,expected_regions,validate_body_measurement,validate_body_receipt
from .skin_geometry import cached_skin_metrics

POLICY='CLOSED_SKIN_HAND_OUTWARD_WINDING_V1'
REASONS={'CENTRAL_BRANCH_UNAVAILABLE','WEIGHTED_REGIONS_UNAVAILABLE','SKIN_GEOMETRY_BUDGET','SKIN_INVALID_GEOMETRY',
    'SKIN_DEGENERATE_GEOMETRY','SKIN_DUPLICATE_FACE','SKIN_OPEN_OR_UNORIENTED','SKIN_NONMANIFOLD_VERTEX',
    'SKIN_UNSUPPORTED_TOPOLOGY','SKIN_NONPOSITIVE_VOLUME','SKIN_HAND_SELECTION_BUDGET','SKIN_HAND_SELECTION_OVERLAP','SKIN_RAY_BUDGET'}


@dataclass(frozen=True,slots=True)
class SkinInclusionVariant:
    status: str
    reason: str
    nonzero: tuple[tuple[frozenset[int],frozenset[int]],...] | None
    ambiguous: tuple[tuple[frozenset[int],frozenset[int]],...] | None


@dataclass(frozen=True,slots=True)
class SkinInclusion:
    original: SkinInclusionVariant
    fitted: SkinInclusionVariant | None


def validate_skin_measurement(report,bindings,baseline,paired):
    validate_body_measurement(report,bindings,baseline,paired,expected_status='REAL_NATIVE_SKIN_INCLUSION_MEASURED')


def skin_variant(data,cache,skin_hashes,triangle_hashes,baseline,profile,*,cancel_check=lambda:None) -> SkinInclusionVariant:
    fields={'policy','status','reason','hands','head','parents','deform_bones','world_matrix','region_bones','region_vertex_counts',
            'frame_count','frames','contact_quality_verified','engine_import_verified'}
    if (type(data) is not dict or set(data)!=fields or data['policy']!=POLICY or type(data['status']) is not str or
        data['status'] not in {'CHECKED','UNAVAILABLE'} or type(data['reason']) is not str or
        (data['reason']!='' if data['status']=='CHECKED' else data['reason'] not in REASONS) or
        data['contact_quality_verified'] is not False or data['engine_import_verified'] is not False or
        type(data['frame_count']) is not int or data['frame_count']!=cache.frame_count or type(data['frames']) is not list or
        len(data['frames'])!=cache.frame_count or type(data['world_matrix']) is not list or len(data['world_matrix'])!=16 or
        any(type(v) not in (int,float) or not math.isfinite(v) for v in data['world_matrix']) or data['world_matrix']!=list(cache.world_matrix)):
        raise ValidationError('Closed-skin policy, scope, transform, coverage or approval differs')
    hands={s:profile['landmarks'][s+'_hand']['target'] for s in ('left','right')};head=profile['landmarks']['head']['target']
    if data['hands']!=hands or data['head']!=head:raise ValidationError('Closed-skin mapped anatomy differs')
    known={p['target'] for p in baseline['mapped_pairs']}|set(baseline['neutral_target_helpers'])
    regions=expected_regions(data['parents'],hands,head,data['deform_bones'],known)
    if regions is None:
        if data['status']!='UNAVAILABLE' or data['reason']!='CENTRAL_BRANCH_UNAVAILABLE' or data['region_bones']!={}:
            raise ValidationError('Unavailable closed-skin anatomy claims partial observations')
    elif data['region_bones']!=regions or data['reason']=='CENTRAL_BRANCH_UNAVAILABLE':
        raise ValidationError('Closed-skin weighted branch identity differs')
    counts=data['region_vertex_counts']
    if (type(counts) is not dict or set(counts) not in (set(),{'left_hand','right_hand','central_body'}) or
        any(type(v) is not int or not 0<=v<=cache.vertex_count for v in counts.values()) or
        sum(counts.values())>cache.vertex_count or (data['status']=='CHECKED' and (len(counts)!=3 or not all(counts.values())))):
        raise ValidationError('Closed-skin weighted vertex counts differ')
    nonzero=[];ambiguous=[]
    for index,row in enumerate(data['frames']):
        cancel_check()
        if (type(row) is not dict or set(row)!={'frame','skin_sha256','triangle_sha256','observation'} or
            type(row['frame']) is not int or row['frame']!=index+1 or row['skin_sha256']!=skin_hashes[index] or
            row['triangle_sha256']!=triangle_hashes[index] or sha256(cache.frame(index)[1]).hexdigest()!=triangle_hashes[index]):
            raise ValidationError('Closed-skin frame/skin/pose-specific topology differs')
        obs=row['observation']
        if data['status']=='UNAVAILABLE':
            if obs is not None:raise ValidationError('Unavailable closed skin contains a partial verdict')
            continue
        if type(obs) is not dict or set(obs)!={'diagonal_world','offset_world','signed_volume_world','ray_queries','left','right'}:
            raise ValidationError('Incomplete closed-skin frame observation')
        diagonal,volume=cached_skin_metrics(cache,index,cancel_check=cancel_check)
        for key,expected in (('diagonal_world',diagonal),('offset_world',diagonal*1e-6),('signed_volume_world',volume)):
            value=obs[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not math.isclose(value,expected,rel_tol=1e-5,abs_tol=abs(expected)*1e-8):
                raise ValidationError('Closed-skin world geometry metrics do not reproduce from cache')
        selected=[];hand_vertices=[];nz=[];unknown=[];indices=cache.frame(index)[1]
        for side in ('left','right'):
            hit=obs[side]
            if type(hit) is not dict or set(hit)!={'selected_triangles','nonzero_triangles','ambiguous_triangles'}:
                raise ValidationError('Incomplete closed-skin hand selection')
            for key,ids in hit.items():
                if (type(ids) is not list or len(ids)>10000 or any(type(v) is not int or not 0<=v<cache.triangle_count for v in ids) or
                    ids!=sorted(set(ids))):raise ValidationError('Invalid closed-skin face identities')
            a,b,c=(set(hit[k]) for k in ('selected_triangles','nonzero_triangles','ambiguous_triangles'))
            if not a or not b<=a or not c<=a or b&c:raise ValidationError('Overlapping or unselected closed-skin observations')
            vertices={v for face in a for v in struct.unpack_from('<III',indices,face*12)}
            if len(vertices)>counts[side+'_hand']:raise ValidationError('Selected skin exceeds weighted hand vertices')
            hand_vertices.append(vertices)
            selected.append(a);nz.append(frozenset(b));unknown.append(frozenset(c))
        queries=obs['ray_queries']
        if selected[0]&selected[1] or hand_vertices[0]&hand_vertices[1] or type(queries) is not int or not 3*sum(map(len,selected))<=queries<=1000000:
            raise ValidationError('Closed-skin ray budget or hand separation differs')
        nonzero.append(tuple(nz));ambiguous.append(tuple(unknown))
    return SkinInclusionVariant(data['status'],data['reason'],tuple(nonzero) if data['status']=='CHECKED' else None,
        tuple(ambiguous) if data['status']=='CHECKED' else None)


def read_skin_inclusion(folder,report,verification,bindings,baseline,profile,original_cache,*,fitted_timeline=None,
                        fitted_cache=None,cancel_check=lambda:None) -> SkinInclusion:
    paired=fitted_timeline is not None
    if paired!=(fitted_cache is not None):raise ValidationError('Closed-skin comparison requires both fitted timeline and cache')
    validate_skin_measurement(report,bindings,baseline,paired)
    validate_body_receipt(verification,bindings,baseline,paired,report['report']['sha256'],expected_status='REAL_NATIVE_SKIN_INCLUSION_VERIFIED')
    data,_=read_json_record(folder,report['report'],'body_contacts.json',64*1024*1024,cancel_check=cancel_check)
    fields={'schema_version','policy','measurement','bindings','paired','source_frame_count','source_first_frame','fps',
            'original','fitted','original_review_verification','fitted_frames_verified','originals_unchanged'}|FLAGS
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        data['policy']!=POLICY or data['measurement']!='FRESH_SAVED_ACTION_CLOSED_SKIN_V1' or data['bindings']!=bindings or
        data['paired'] is not paired or type(data['source_frame_count']) is not int or data['source_frame_count']!=baseline['source_frame_count'] or
        type(data['source_first_frame']) is not int or data['source_first_frame']!=baseline['source_first_frame'] or
        type(data['fps']) not in (int,float) or data['fps']!=baseline['fps'] or
        type(data['fitted_frames_verified']) is not int or data['fitted_frames_verified']!=(data['source_frame_count'] if paired else 0) or
        data['originals_unchanged'] is not True or any(data[k] is not False for k in FLAGS)):
        raise ValidationError('Closed-skin provenance, complete coverage or approval differs')
    validate_reopen_report(data['original_review_verification'],{k:bindings[k] for k in HASHES},baseline)
    if (original_cache.surface_review is None or original_cache.frame_count!=data['source_frame_count'] or
        original_cache.fps!=data['fps'] or original_cache.source_first_frame!=data['source_first_frame']):
        raise ValidationError('Closed-skin observation requires complete original playback geometry')
    original=skin_variant(data['original'],original_cache,[r['evaluated_sha256'] for r in baseline['full_timeline_frames']],
        original_cache.surface_review.triangle_hashes,baseline,profile,cancel_check=cancel_check)
    fitted=None
    if paired:
        if (fitted_timeline['frame_count']!=data['source_frame_count'] or fitted_cache.frame_count!=data['source_frame_count'] or
            fitted_timeline['bindings']!={k:v for k,v in bindings.items() if k!='fit_report_sha256'} or
            fitted_cache.fps!=data['fps'] or fitted_cache.source_first_frame!=data['source_first_frame']):
            raise ValidationError('Closed-skin fitted geometry differs from complete bound sequence')
        fitted=skin_variant(data['fitted'],fitted_cache,[r['skin_sha256'] for r in fitted_timeline['frames']],
            [r['triangle_sha256'] for r in fitted_timeline['frames']],baseline,profile,cancel_check=cancel_check)
        for field in ('parents','deform_bones','world_matrix','region_bones','region_vertex_counts'):
            if data['original'][field]!=data['fitted'][field]:raise ValidationError('Fitted closed-skin anatomical selection changed')
    elif data['fitted'] is not None:raise ValidationError('Original-only closed skin contains a fitted verdict')
    return SkinInclusion(original,fitted)
