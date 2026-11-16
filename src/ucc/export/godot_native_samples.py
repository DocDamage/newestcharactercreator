"""Closed native interaction coverage; independent of Blender/model runtimes."""
from ucc.core.errors import ValidationError
from .godot_candidate_contract import canonical_bytes,_hash

POLICY='MPFB_NATIVE_RUNTIME_INTERACTIONS_V1'
OPERATION='sample_native_godot_runtime'
ROLES=('eye_left_closure','eye_right_closure','mouth_corners','mouth_open')
FAMILIES=frozenset({'african','asian','caucasian'})
COUNT=2697
VERTICES=13380
REFERENCE_BYTES=COUNT*VERTICES*16
OUTPUTS=frozenset({'expected_vec4.f32','expected_normals_vec4.f32'})


def interaction_cases() -> list[dict]:
    rows=[{'profile':'neutral_integer','frame':i,'subframe':0.,'facial_parameters':{}} for i in range(1,301)]
    rows += [{'profile':'temporal_neutral_face','frame':i,'subframe':part,'facial_parameters':{}}
             for i in range(1,300) for part in (.25,.5,.75)]
    for role in ROLES:
        rows += [{'profile':'face_'+role,'frame':i,'subframe':0.,'facial_parameters':{role:.5}} for i in range(1,301)]
    rows += [{'profile':'face_all_roles','frame':i,'subframe':0.,'facial_parameters':{role:.5 for role in ROLES}} for i in range(1,301)]
    return rows


def validate_sample_report(raw: object,*,request_sha256: str,production_sha256: str,
                           recipe_sha256: str,verification_sha256: str) -> dict:
    fields={'schema_version','policy','status','request_sha256','production_receipt_sha256','recipe_sha256',
        'native_verification_sha256','vertices','samples','cases','views','race_mix','roles','files','blender_version',
        'source_reopened_without_repair','source_files_unchanged','engine_import_verified','visual_quality_approved',
        'distribution_license_review_complete'}
    if (type(raw) is not dict or set(raw)!=fields or type(raw.get('schema_version')) is not int or raw['schema_version']!=1
            or raw.get('policy')!=POLICY or raw.get('status')!='FRESH_NATIVE_INTERACTION_REFERENCES_MEASURED'
            or raw.get('request_sha256')!=request_sha256 or raw.get('production_receipt_sha256')!=production_sha256
            or raw.get('recipe_sha256')!=recipe_sha256 or raw.get('native_verification_sha256')!=verification_sha256
            or type(raw.get('vertices')) is not int or raw['vertices']!=VERTICES
            or type(raw.get('samples')) is not int or raw['samples']!=COUNT
            or canonical_bytes(raw.get('cases'))!=canonical_bytes(interaction_cases()) or raw.get('roles')!=list(ROLES)
            or raw.get('source_reopened_without_repair') is not True or raw.get('source_files_unchanged') is not True
            or any(raw.get(k) is not False for k in ('engine_import_verified','visual_quality_approved','distribution_license_review_complete'))):
        raise ValidationError('Native interaction evidence changed its source, complete coverage or unapproved flags')
    import math
    race=raw['race_mix']
    if (type(race) is not dict or set(race)!=FAMILIES or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in race.values())
            or not .98<=sum(race.values())<=1.02):raise ValidationError('Native interaction race weights are invalid; never renormalize them')
    if type(raw['views']) is not list or len(raw['views'])!=COUNT:raise ValidationError('Missing native interaction views')
    for view in raw['views']:
        if (type(view) is not dict or set(view)!={'center','size','distance'} or type(view['center']) is not list or len(view['center'])!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100 for v in view['center'])
                or any(type(view[k]) not in (int,float) or not math.isfinite(view[k]) or not 0<view[k]<=100 for k in ('size','distance'))):
            raise ValidationError('Native interaction view is malformed or unbounded')
    if type(raw['files']) is not dict or set(raw['files'])!=OUTPUTS:raise ValidationError('Native reference closure is incomplete')
    for record in raw['files'].values():
        if (type(record) is not dict or set(record)!={'sha256','bytes'} or not _hash(record['sha256'])
                or type(record['bytes']) is not int or record['bytes']!=REFERENCE_BYTES):
            raise ValidationError('Native interaction reference byte binding is invalid')
    return raw
