"""NONSHIPPING immutable body-sprite request metadata; no native or rights proof."""
from uuid import UUID
from fixtures.target_action_contract import metadata_pair
from ucc.core.body_sprites import BodySpriteRequest,BodySpriteWindow,body_sprite_sources
from ucc.core.expressions import ExpressionState
from ucc.core.models import CharacterProject,PartInstance
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.sprite_render import SpritePermission,SpriteSettings
from ucc.core.target_action_format import canonical_bytes

def request(*, hand=True, window=None, settings=None):
    _, binding = metadata_pair()
    parts = (PartInstance('unit-hand', 'ucc-hand-v1-'+'d'*64+'-shorter', 'hand.L'),) if hand else ()
    project = CharacterProject('unit-project', 'NONSHIPPING body-sprite contract fixture',
        master_blend='master/versions/'+'b'*64+'.blend', geometry_state='generated_unverified',
        revision=4, schema_version=3, parts=parts,
        animations=('unit-asset#clip-0000', 'other-source#clip-0000'),
        created_utc='2026-11-17T00:00:00+00:00',
        expression=ExpressionState('c'*64, (('eye_left_closure', .1), ('eye_right_closure', .2),
                                           ('mouth_corners', .3), ('mouth_open', .4))))
    permissions = tuple(SpritePermission(name, digest,
        'UNIT_ONLY_EXPLICIT_PRIVATE_SPRITE_REVIEW_NOT_REAL_SOURCE_APPROVAL', True, True)
        for name, digest in body_sprite_sources(project, binding))
    return BodySpriteRequest(str(UUID(int=100)), canonical_bytes(project.to_dict()), binding,
        window or BodySpriteWindow(149, 152), settings or SpriteSettings(128, 4),
        SkinMaterialSpec((.56, .60, .67), 1.), permissions,
        'UNIT_ONLY body-sprite contract validation', True)
