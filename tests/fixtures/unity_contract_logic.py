"""Scalar-only nonshipping request fixture; no character or integration evidence."""
from ucc.export.godot_candidate_contract import EngineInputPermission
from ucc.export.unity_contract import UnityExportRequest
from ucc.library.provenance import LicensePolicy


def request():
    sources=(('master','a'*64),('expression_library','b'*64),('body_material','c'*64),('part:ucc-hand-v1-test','d'*64))
    policy=LicensePolicy('UNIT_TEST_ONLY','UNIT_TEST_ONLY','urn:ucc:unit-test:unity-request',reviewed=True,
                         no_ai=True,can_use_non_unreal=True)
    return UnityExportRequest('1d23162c-15b6-4a76-8b65-20cb9f52892a','UNIT_TEST_ONLY',1,'e'*64,'f'*64,sources,
                              tuple(EngineInputPermission(name,digest,policy,False) for name,digest in sources))
