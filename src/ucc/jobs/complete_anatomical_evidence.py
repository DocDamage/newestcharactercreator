"""Strict three-report receipt and cache intake; no Blender or Qt imports."""
from dataclasses import dataclass

from ucc.animations.contact_fit import HASHES
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from ucc.preview.central_enclosure import CentralEnclosure,validate_anatomical_measurement,read_central_enclosure
from ucc.preview.central_surface import CompleteTrunkSurfaces,POLICY,_parse_variant
from ucc.preview.contact_areas import BodyContactAreas,parse_body_contact_areas
from .native_fit_evidence import FLAGS,read_json_record

RECORDS={'report':('body_contacts.json','body_review_sha256',40*1024*1024),
         'enclosure_report':('central_enclosure.json','enclosure_review_sha256',64*1024*1024),
         'full_trunk_report':('full_trunk_contacts.json','full_trunk_review_sha256',64*1024*1024)}


@dataclass(frozen=True,slots=True)
class CompleteAnatomicalEvidence:
    areas: BodyContactAreas
    enclosure: CentralEnclosure
    full_trunk: CompleteTrunkSurfaces


def validate_complete_measurement(report,bindings,baseline,paired):
    fields={'status','bindings','frames','report','enclosure_report','full_trunk_report','originals_unchanged'}|FLAGS
    expected=HASHES|({'fit_sha256','fitted_sha256','fit_report_sha256'} if paired else set())
    if (type(bindings) is not dict or set(bindings)!=expected or any(not is_sha256(v) for v in bindings.values()) or
        type(report) is not dict or set(report)!=fields or report['status']!='REAL_COMPLETE_ANATOMICAL_SAFETY_MEASURED'):
        raise ValidationError('Complete anatomical measurement lacks exact source/report identities')
    for key,(name,_,limit) in RECORDS.items():
        record=report[key]
        if (type(record) is not dict or set(record)!={'name','bytes','sha256'} or record['name']!=name or
            type(record['bytes']) is not int or not 0<record['bytes']<=limit or not is_sha256(record['sha256'])):
            raise ValidationError('Invalid complete anatomical report record')
    legacy={k:v for k,v in report.items() if k!='full_trunk_report'}
    legacy['status']='REAL_ANATOMICAL_SAFETY_MEASURED'
    validate_anatomical_measurement(legacy,bindings,baseline,paired)


def validate_complete_receipt(receipt,report,bindings,baseline,paired):
    validate_complete_measurement(report,bindings,baseline,paired)
    fields={'status','bindings','frames_verified','paired','originals_unchanged'}|FLAGS
    expected={**bindings,**{hash_key:report[key]['sha256'] for key,(_,hash_key,_) in RECORDS.items()}}
    if (type(receipt) is not dict or set(receipt)!=fields or receipt['status']!='REAL_COMPLETE_ANATOMICAL_SAFETY_VERIFIED' or
        receipt['bindings']!=expected or type(receipt['frames_verified']) is not int or
        receipt['frames_verified']!=baseline['source_frame_count'] or receipt['paired'] is not paired or
        receipt['originals_unchanged'] is not True or any(receipt[k] is not False for k in FLAGS)):
        raise ValidationError('All three anatomical reports must be independently reproduced together')


def read_complete_anatomy(folder,report,receipt,bindings,baseline,profile,original_cache,*,
                          fitted_timeline=None,fitted_cache=None,cancel_check=lambda:None):
    paired=fitted_cache is not None
    if paired!=(fitted_timeline is not None):raise ValidationError('Complete anatomical comparison needs fitted cache and timeline')
    validate_complete_receipt(receipt,report,bindings,baseline,paired)
    records={key:read_json_record(folder,report[key],name,limit,cancel_check=cancel_check)[0]
             for key,(name,_,limit) in RECORDS.items()}
    areas_data=records['report'];volume=records['enclosure_report'];full=records['full_trunk_report']
    areas=parse_body_contact_areas(areas_data,bindings,baseline,profile,original_cache,
        fitted_timeline=fitted_timeline,fitted_cache=fitted_cache,cancel_check=cancel_check)
    # Validate the existing observations using views of the already validated
    # stronger receipt. The bound report bytes and hashes are never rewritten.
    legacy_report={k:v for k,v in report.items() if k!='full_trunk_report'}
    legacy_report['status']='REAL_ANATOMICAL_SAFETY_MEASURED'
    legacy_receipt={**receipt,'status':'REAL_ANATOMICAL_SAFETY_VERIFIED',
        'bindings':{k:v for k,v in receipt['bindings'].items() if k!='full_trunk_review_sha256'}}
    enclosure=read_central_enclosure(folder,legacy_report,legacy_receipt,bindings,baseline,profile,original_cache,areas_data,
        fitted_cache=fitted_cache,cancel_check=cancel_check)
    fields={'schema_version','policy','bindings','source_frame_count','paired','polygon_topology_sha256',
            'original','fitted','originals_unchanged'}|FLAGS
    if (type(full) is not dict or set(full)!=fields or type(full['schema_version']) is not int or full['schema_version']!=1 or
        full['policy']!=POLICY or full['bindings']!=bindings or full['paired'] is not paired or
        type(full['source_frame_count']) is not int or full['source_frame_count']!=baseline['source_frame_count'] or
        full['polygon_topology_sha256']!=areas_data['polygon_topology_sha256'] or full['originals_unchanged'] is not True or
        any(full[k] is not False for k in FLAGS)):
        raise ValidationError('Complete trunk policy, provenance, topology or approval differs')
    original=_parse_variant(full['original'],original_cache,volume['original'],areas_data['polygons'],cancel_check=cancel_check)
    fitted=None;new=None;more=None
    if paired:
        fitted=_parse_variant(full['fitted'],fitted_cache,volume['fitted'],areas_data['polygons'],cancel_check=cancel_check)
        new=tuple(i for i in range(original_cache.frame_count) if any(
            b-a for key in ('hand_polygons','body_polygons')
            for a,b in zip(getattr(original,key)[i],getattr(fitted,key)[i])))
        more=tuple(i for i,(a,b) in enumerate(zip(original.surface.pairs,fitted.surface.pairs))
                   if any(y>x for x,y in zip(a,b)))
    elif full['fitted'] is not None:raise ValidationError('Undeclared fitted complete trunk observations')
    return CompleteAnatomicalEvidence(areas,enclosure,CompleteTrunkSurfaces(original,fitted,new,more))
