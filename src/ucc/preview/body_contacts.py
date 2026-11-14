"""Independent semantics for freshly reproduced hand/central-body observations."""
from dataclasses import dataclass
from hashlib import sha256

from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from ucc.jobs.native_fit_evidence import FLAGS,read_json_record
from ucc.jobs.native_skin_evidence import validate_reopen_report
from .motion_cache import HASHES,MotionCache
from .surface_review import SurfaceReview

POLICY='HAND_CENTRAL_BODY_TRIANGLES_V1'
FIT_HASHES=HASHES|{'fit_sha256','fitted_sha256','fit_report_sha256'}
REGIONS={'left_hand','right_hand','central_body'}
REASONS={'CENTRAL_BRANCH_UNAVAILABLE','WEIGHTED_REGIONS_UNAVAILABLE','SURFACE_WORKLOAD_EXCEEDED',
         'SURFACE_PAIR_BUDGET_EXCEEDED','SURFACE_HIGHLIGHTS_EXCEEDED'}


@dataclass(frozen=True,slots=True)
class BodyContacts:
    original: SurfaceReview
    fitted: SurfaceReview | None
    more_pair_frames: tuple[int,...] | None


def expected_regions(parents,hands,head,deform,known):
    if (type(parents) is not dict or set(parents)!=known or len(known)>256 or
        any(type(n) is not str or (p is not None and (type(p) is not str or p not in known)) for n,p in parents.items()) or
        sum(p is None for p in parents.values())!=1 or head not in known):
        raise ValidationError('Body review lacks the complete target hierarchy')
    paths={}
    for name in parents:
        path=[];current=name
        while current is not None:
            if current in path:raise ValidationError('Body review hierarchy contains a cycle')
            path.append(current);current=parents[current]
        paths[name]=path
    if (type(deform) is not list or not 1<=len(deform)<=256 or any(type(n) is not str or n not in known for n in deform) or
        deform!=sorted(set(deform))):raise ValidationError('Invalid actual deform-bone list')
    if any(n not in known for n in hands.values()):raise ValidationError('Body review hand is outside the actual rig')
    common=next((n for n in paths[hands['left']] if n in paths[hands['right']]),None)
    if common is None or any(paths[hands[s]].index(common)<2 for s in ('left','right')):return None
    regions={s+'_hand':{n for n in deform if hands[s] in paths[n]} for s in ('left','right')}
    for side in ('left','right'):
        path=paths[hands[side]];branch=path[path.index(common)-1]
        if not ({n for n in deform if branch in paths[n]}-regions[side+'_hand']):return None
    regions['central_body']=set(paths[head])&set(deform)
    if not all(regions.values()) or any(regions[a]&regions[b] for a in regions for b in regions if a<b):return None
    return {k:sorted(v) for k,v in regions.items()}


def parse_body_variant(data,cache: MotionCache,skin_hashes,triangle_hashes,baseline,profile,*,cancel_check=lambda:None):
    fields={'policy','status','reason','hands','head','parents','deform_bones','world_matrix','region_bones','region_vertex_counts',
            'frame_count','frames','contact_quality_verified','engine_import_verified'}
    count=cache.frame_count
    if (type(data) is not dict or set(data)!=fields or data['policy']!=POLICY or type(data['status']) is not str or data['status'] not in {'CHECKED','UNAVAILABLE'} or
        type(data['reason']) is not str or (data['reason']!='' if data['status']=='CHECKED' else data['reason'] not in REASONS) or
        type(data['frame_count']) is not int or data['frame_count']!=count or type(data['frames']) is not list or len(data['frames'])!=count or
        data['contact_quality_verified'] is not False or data['engine_import_verified'] is not False or
        type(data['world_matrix']) is not list or len(data['world_matrix'])!=16 or
        any(type(v) not in (int,float) or not -10000<=v<=10000 for v in data['world_matrix']) or
        data['world_matrix']!=list(cache.world_matrix)):
        raise ValidationError('Body review policy, complete coverage, world transform or approval differs')
    hands={s:profile['landmarks'][s+'_hand']['target'] for s in ('left','right')};head=profile['landmarks']['head']['target']
    if data['hands']!=hands or data['head']!=head:raise ValidationError('Body review anatomical identity differs from the bound map')
    known={p['target'] for p in baseline['mapped_pairs']}|set(baseline['neutral_target_helpers'])
    regions=expected_regions(data['parents'],hands,head,data['deform_bones'],known)
    if regions is None:
        if data['status']!='UNAVAILABLE' or data['reason']!='CENTRAL_BRANCH_UNAVAILABLE' or data['region_bones']!={}:
            raise ValidationError('Incompatible central-body anatomy claims a partial verdict')
    elif data['region_bones']!=regions or data['reason']=='CENTRAL_BRANCH_UNAVAILABLE':
        raise ValidationError('Central-body regions do not follow actual anatomical ancestry')
    sizes=data['region_vertex_counts']
    if (type(sizes) is not dict or set(sizes) not in (set(),REGIONS) or
        any(type(n) is not int or not 0<=n<=cache.vertex_count for n in sizes.values()) or sum(sizes.values())>cache.vertex_count or
        (regions is not None and set(sizes)!=REGIONS) or
        (data['status']=='CHECKED' and (set(sizes)!=REGIONS or not all(sizes.values())))):
        raise ValidationError('Invalid or incomplete central-body weighted regions')
    if len(skin_hashes)!=count or len(triangle_hashes)!=count:raise ValidationError('Body review lacks complete independent geometry references')
    triangles=[];pairs=[];hashes=[];total=0
    for frame,(row,skin,topology) in enumerate(zip(data['frames'],skin_hashes,triangle_hashes),1):
        cancel_check()
        if (type(row) is not dict or set(row)!={'frame','skin_sha256','triangle_sha256','left','right'} or
            type(row['frame']) is not int or row['frame']!=frame or row['skin_sha256']!=skin or row['triangle_sha256']!=topology):
            raise ValidationError('Body review skin/topology differs from the verified playback geometry')
        ids=set();numbers=[]
        for side in ('left','right'):
            hit=row[side]
            if data['status']=='UNAVAILABLE':
                if hit is not None:raise ValidationError('Unavailable body review contains partial contact observations')
                numbers.append(0);continue
            if (type(hit) is not dict or set(hit)!={'pair_count','pair_sha256','hand_triangles','central_triangles'} or
                type(hit['pair_count']) is not int or not 0<=hit['pair_count']<=250000 or not is_sha256(hit['pair_sha256'])):
                raise ValidationError('Invalid central-body triangle-pair record')
            hand,body=hit['hand_triangles'],hit['central_triangles']
            for value in (hand,body):
                if (type(value) is not list or len(value)>cache.triangle_count or any(type(v) is not int or not 0<=v<cache.triangle_count for v in value) or
                    value!=sorted(set(value)) or len(value)>hit['pair_count'] or bool(value)!=bool(hit['pair_count'])):
                    raise ValidationError('Invalid central-body highlight triangle indices')
                ids.update(value);total+=len(value)
            if set(hand)&set(body) or (not hit['pair_count'] and hit['pair_sha256']!=sha256().hexdigest()):
                raise ValidationError('Central-body hand/surface pair identity differs')
            numbers.append(hit['pair_count'])
        triangles.append(tuple(sorted(ids)));pairs.append(tuple(numbers));hashes.append(topology)
    if total>1_000_000:raise ValidationError('Body highlight coverage exceeds its complete-workload bound')
    return SurfaceReview(data['status'],data['reason'],tuple(triangles),tuple(pairs),tuple(hashes),POLICY)


def validate_body_measurement(report,bindings,baseline,paired):
    fields={'status','bindings','frames','report','originals_unchanged'}|FLAGS
    if (type(bindings) is not dict or set(bindings)!=(FIT_HASHES if paired else HASHES) or any(not is_sha256(v) for v in bindings.values()) or
        type(report) is not dict or set(report)!=fields or report['status']!='REAL_NATIVE_BODY_CONTACTS_MEASURED' or
        report['bindings']!=bindings or type(report['frames']) is not int or report['frames']!=baseline['source_frame_count'] or
        report['originals_unchanged'] is not True or any(report[k] is not False for k in FLAGS)):
        raise ValidationError('Body contact measurement lacks the requested unapproved complete result')


def read_body_contacts(folder,report,verification,bindings,baseline,profile,original_cache,*,fitted_timeline=None,
                       fitted_cache=None,cancel_check=lambda:None) -> BodyContacts:
    paired=fitted_timeline is not None
    if paired!=(fitted_cache is not None):raise ValidationError('Body comparison needs both fitted geometry and its verified timeline')
    validate_body_measurement(report,bindings,baseline,paired)
    data,_=read_json_record(folder,report['report'],'body_contacts.json',32*1024*1024,cancel_check=cancel_check)
    vf={'status','bindings','frames_verified','paired','originals_unchanged'}|FLAGS
    if (type(verification) is not dict or set(verification)!=vf or verification['status']!='REAL_NATIVE_BODY_CONTACTS_VERIFIED' or
        verification['bindings']!={**bindings,'body_review_sha256':report['report']['sha256']} or verification['paired'] is not paired or
        type(verification['frames_verified']) is not int or verification['frames_verified']!=baseline['source_frame_count'] or
        verification['originals_unchanged'] is not True or any(verification[k] is not False for k in FLAGS)):
        raise ValidationError('Body contact observations were not independently reproduced')
    fields={'schema_version','policy','measurement','bindings','paired','source_frame_count','source_first_frame','fps',
            'original','fitted','original_review_verification','fitted_frames_verified','originals_unchanged'}|FLAGS
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        data['policy']!=POLICY or data['measurement']!='FRESH_SAVED_ACTION_BODY_SURFACES_V1' or data['bindings']!=bindings or data['paired'] is not paired or
        type(data['source_frame_count']) is not int or data['source_frame_count']!=baseline['source_frame_count'] or
        type(data['source_first_frame']) is not int or data['source_first_frame']!=baseline['source_first_frame'] or
        type(data['fps']) not in (int,float) or not 1<=data['fps']<=240 or data['fps']!=baseline['fps'] or
        type(data['fitted_frames_verified']) is not int or data['fitted_frames_verified']!=(data['source_frame_count'] if paired else 0) or
        data['originals_unchanged'] is not True or any(data[k] is not False for k in FLAGS)):
        raise ValidationError('Body contact provenance, timing or scene verification differs')
    validate_reopen_report(data['original_review_verification'],{k:bindings[k] for k in HASHES},baseline)
    if (original_cache.frame_count!=data['source_frame_count'] or original_cache.surface_review is None or
        original_cache.fps!=data['fps'] or original_cache.source_first_frame!=data['source_first_frame']):
        raise ValidationError('Body review has no complete original skin/topology cache')
    source=parse_body_variant(data['original'],original_cache,[r['evaluated_sha256'] for r in baseline['full_timeline_frames']],
        original_cache.surface_review.triangle_hashes,baseline,profile,cancel_check=cancel_check)
    fitted=None;more=None
    if paired:
        if (fitted_timeline['frame_count']!=data['source_frame_count'] or fitted_cache.frame_count!=data['source_frame_count'] or
            fitted_timeline['bindings']!={k:v for k,v in bindings.items() if k!='fit_report_sha256'} or
            fitted_cache.fps!=data['fps'] or fitted_cache.source_first_frame!=data['source_first_frame']):
            raise ValidationError('Body comparison does not cover the same complete fitted clip')
        fitted=parse_body_variant(data['fitted'],fitted_cache,[r['skin_sha256'] for r in fitted_timeline['frames']],
            [r['triangle_sha256'] for r in fitted_timeline['frames']],baseline,profile,cancel_check=cancel_check)
        for field in ('parents','deform_bones','world_matrix','region_bones','region_vertex_counts'):
            if data['original'][field]!=data['fitted'][field]:raise ValidationError('Fitted body inspection changed original region geometry or anatomical identity')
        if source.status=='CHECKED' and fitted.status=='CHECKED':more=tuple(i for i,(a,b) in enumerate(zip(source.pairs,fitted.pairs)) if sum(b)>sum(a))
    elif data['fitted'] is not None:raise ValidationError('Original-only body review contains an undeclared fitted variant')
    return BodyContacts(source,fitted,more)
