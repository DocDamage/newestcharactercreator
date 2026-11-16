"""UNIT metadata only; no Blender scene or model verification evidence."""
from ucc.core.sprite_render import SpriteRenderRequest,SpritePermission,SpriteSettings
from fixtures.godot_export_logic import request as engine_request


def request(settings=None):
    source=engine_request()
    return SpriteRenderRequest(source.job_id,source.project_id,source.revision,source.project_sha256,source.source_bindings,
        tuple(SpritePermission(name,digest,'UNIT_ONLY_PRIVATE_SPRITE_PERMISSION_NOT_REAL_ASSET_APPROVAL',True,True) for name,digest in source.source_bindings),settings or SpriteSettings())


def incomplete_evidence_metadata(bindings):
    """No images: malformed proof must reject before any image/frame admission."""
    from ucc.core.sprite_render import POLICY
    report={'schema_version':1,'policy':POLICY,**bindings,'source_state_sha256':'e'*64,'shader_sha256':'f'*64,
        'configuration':{'engine':'CYCLES','device':'CPU','samples':32,'resolution':[256,256,100],'transparent':True,'format':['PNG','RGBA','8',15],'frame':1},
        'pivot':[.5,.9],'frames':[],'blender_version':'5.3.0','blender_build_hash':'UNIT_NOT_BUILD_PROOF','animation_clips':False,'visual_quality_approved':False}
    proof={'schema_version':1,'policy':POLICY,'bindings':{},'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':'e'*64,'shader_sha256':'f'*64,'frame_count':4,'exact_rerender_pixels':True,'visual_quality_approved':False}
    return report,proof
