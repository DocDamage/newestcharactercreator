"""Synthetic metadata only; never Blender, animation or render proof."""
from ucc.core.sprite_render import canonical
from ucc.core.facial_sprites import FacialSpriteRequest
from ucc.core.expression_clip import _recipe
from fixtures.sprite_render_logic import request as source_request


def request():
    review=source_request();bindings=dict(review.source_bindings)
    clip=_recipe({'project_id':review.project_id,'revision':review.revision,'project_snapshot_sha256':'d'*64,
        'master_sha256':bindings['master'],'library_sha256':bindings['expression_library']},
        {'eye_left_closure':.5,'eye_right_closure':.5,'mouth_corners':.5,'mouth_open':.5})
    return FacialSpriteRequest(review,canonical(clip))
