"""Non-shipping permission/source metadata only; no character/engine evidence."""
from ucc.jobs.static_export_sources import ExportReview,ExportSource
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.library.provenance import LicensePolicy
from ucc.export.static_godot_contract import StaticGodotRequest


def review():
    return ExportReview('UNIT_DIAGNOSTIC_PROJECT',1,'e'*64,tuple(ExportSource(name,h,name) for name,h in
        [('master','a'*64),('expression_library','b'*64),('body_material','c'*64)]))


def request():
    sources=review()
    policy=LicensePolicy('UNIT_NOT_REAL_RIGHTS','UNIT_TEST_DECLARATION','ucc-unit://not-real-assets',reviewed=True,
        no_ai=True,can_use_non_unreal=True,redistribute_source_allowed=False)
    permissions=tuple(EngineInputPermission(s.asset_id,s.sha256,policy,source_only=False) for s in sources.sources)
    return StaticGodotRequest('11111111-2222-4333-8444-555555555555',sources.project_id,sources.revision,sources.project_sha256,
        tuple((s.asset_id,s.sha256) for s in sources.sources),permissions)


def write_unit_engine_outputs(folder):
    """Transaction-only byte markers, NEVER Godot/GLB/image evidence."""
    from hashlib import sha256
    for name in ('character.tscn','character_preview.tscn','export_verification.json','character.png','face-expression.png'):
        (folder/name).write_bytes(('UNIT_NOT_REAL_ENGINE_OUTPUT:'+name).encode())
    return {'saved_scene_sha256':sha256((folder/'character.tscn').read_bytes()).hexdigest(),
        'preview_scene_sha256':sha256((folder/'character_preview.tscn').read_bytes()).hexdigest()}


def write_unit_morph_reference(glb,folder):
    (folder/'morph_reference.bin').write_bytes(b'UNIT_NOT_REAL_MORPHS')
    (folder/'morph_reference.json').write_text('{"UNIT_NOT_REAL_MORPHS":true}')
