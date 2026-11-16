"""Scalar-only NONSHIPPING contract fixture; no character or engine evidence."""
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.unreal_contract import UnrealExportRequest
from ucc.library.provenance import LicensePolicy


def request():
    sources = (('master', 'a'*64), ('expression_library', 'b'*64),
        ('body_material', 'c'*64), ('part:ucc-hand-v1-test', 'd'*64))
    policy = LicensePolicy('UNIT_TEST_ONLY', 'UNIT_TEST_ONLY',
        'urn:ucc:unit-test:unreal-request', reviewed=True, no_ai=True, can_use_unreal=True)
    return UnrealExportRequest('1d23162c-15b6-4a76-8b65-20cb9f52892a', 'UNIT_TEST_ONLY', 1,
        'e'*64, 'f'*64, '1'*64, '2'*64, sources,
        tuple(EngineInputPermission(name, digest, policy, False) for name, digest in sources))
