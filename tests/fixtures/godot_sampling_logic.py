"""Metadata/float-record unit fixtures; not real Blender/MPFB evidence."""
from ucc.export.godot_native_samples import POLICY,COUNT,REFERENCE_BYTES,interaction_cases,ROLES,OUTPUTS


def sample_report() -> dict:
    return {'schema_version':1,'policy':POLICY,'status':'FRESH_NATIVE_INTERACTION_REFERENCES_MEASURED',
        'request_sha256':'a'*64,'production_receipt_sha256':'b'*64,'recipe_sha256':'c'*64,'native_verification_sha256':'d'*64,
        'vertices':13380,'samples':COUNT,'cases':interaction_cases(),
        'views':[{'center':[0.,0.,1.],'size':3.,'distance':4.} for _ in range(COUNT)],
        'race_mix':{'african':.33,'asian':.33,'caucasian':.33},'roles':list(ROLES),
        'files':{name:{'sha256':'e'*64,'bytes':REFERENCE_BYTES} for name in OUTPUTS},
        'blender_version':'UNIT_METADATA_ONLY','source_reopened_without_repair':True,'source_files_unchanged':True,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
