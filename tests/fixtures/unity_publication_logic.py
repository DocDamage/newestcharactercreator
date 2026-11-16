"""Nonshipping byte-marker payload; never a Unity project or engine evidence."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from fixtures.unity_contract_logic import request
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.unity_export_payload import engine_payload, PRIVATE_INPUTS


def payload_fixture(root: Path):
    reviewed = request()
    engine = root/'UNIT_NOT_A_UNITY_PROJECT'
    engine.mkdir()
    saved = {}
    for name in sorted(engine_payload() | PRIVATE_INPUTS):
        path = engine/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('UNIT_NONSHIPPING_NOT_ENGINE_EVIDENCE:'+name).encode())
        saved[name] = sha256(path.read_bytes()).hexdigest()
    spec = SkinMaterialSpec((.3, .2, .1), .6)
    reference = engine/'Assets/UCC/source_reference.json'
    reference.write_bytes(canonical_bytes({'material_spec':spec.to_dict()}))
    saved['Assets/UCC/source_reference.json'] = sha256(reference.read_bytes()).hexdigest()
    (root/'native-import-receipt.json').write_bytes(canonical_bytes({'saved_files': saved}))
    (engine/'request.json').write_bytes(canonical_bytes(reviewed.to_dict()))
    recipe = {'schema_version':1, 'policy':'UCC_UNITY_EDITOR_JOB_V1',
        'request_sha256':reviewed.sha256, 'master_sha256':dict(reviewed.source_bindings)['master'],
        'weights_sha256':saved['Assets/UCC/source_weights.json'],
        'fbx_sha256':saved['Assets/UCC/character.fbx'],
        'source_reference_sha256':saved['Assets/UCC/source_reference.json'],
        'native_mesh_sha256':'c'*64, 'topology_sha256':'d'*64,
        'color_srgb':dict(zip('rgba', (*spec.base_color_srgb, 1.))), 'roughness':spec.roughness}
    (engine/'engine_recipe.json').write_bytes(canonical_bytes(recipe))
    stage = root/'UNIT_DESTINATION'
    stage.mkdir()
    return SimpleNamespace(directory=engine, native_mesh_sha256='c'*64, topology_sha256='d'*64,
        receipt_sha256=sha256((root/'native-import-receipt.json').read_bytes()).hexdigest()), reviewed, stage
