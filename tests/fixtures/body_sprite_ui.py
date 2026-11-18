"""Invented dialog metadata only; not source rights or native rendering proof."""
from pathlib import Path
from fixtures.body_sprite_contract import request
from ucc.jobs.body_sprite_provenance import OriginalMotionProvenance


def ui_request(*, hand=True):
    return request(hand=hand)


def ui_origin(path: Path):
    return OriginalMotionProvenance(path, '7' * 64, 'source_permission')
