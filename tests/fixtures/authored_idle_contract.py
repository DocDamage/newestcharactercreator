"""NONSHIPPING invented metadata; no asset, motion, pose, rights, or native proof."""
from dataclasses import replace
from uuid import UUID

from ucc.core.authored_idle import (
    AuthoredIdleInspectionRequest, AuthoredIdleRequest, IdleAuthoringPermission,
    consumed_sources, saved_authoring_sources,
)
from ucc.core.expressions import ExpressionState
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import canonical_bytes, document_sha256


def saved_project(*, hand=True, expression=True):
    return CharacterProject(
        'synthetic-idle-project', 'NONSHIPPING authored-idle metadata fixture',
        master_blend='master/versions/'+'a'*64+'.blend',
        geometry_state='generated_unverified', revision=7,
        parts=(PartInstance('synthetic-hand', 'ucc-hand-v1-'+'b'*64+'-shorter', 'hand.L'),) if hand else (),
        animations=('never-read-synthetic-source#clip-0000',),
        created_utc='2026-11-17T00:00:00+00:00',
        schema_version=3 if expression else 1,
        expression=ExpressionState('c'*64, (('eye_left_closure', 0.0),
            ('eye_right_closure', 0.0), ('mouth_corners', 0.0), ('mouth_open', 0.1))) if expression else None,
    )


def metadata(*, hand=True, expression=True):
    project = saved_project(hand=hand, expression=expression)
    target = TargetActionTarget(project.project_id, project.revision,
        document_sha256(project.to_dict()), 'a'*64, 'd'*64, 'e'*64)
    return project, target


def inspection(*, hand=True, expression=True):
    """No target or anatomical digest is fabricated to create this first phase."""
    project = saved_project(hand=hand, expression=expression)
    permissions = tuple(IdleAuthoringPermission(name, digest, 'f'*64,
        'SYNTHETIC_TEST_ONLY_NOT_ACTUAL_SOURCE_PERMISSION', True)
        for name, digest in saved_authoring_sources(project))
    return AuthoredIdleInspectionRequest(str(UUID(int=400)), canonical_bytes(project.to_dict()),
        permissions, 'NONSHIPPING neutral-only measurement intent', True, True)


def request(*, hand=True, expression=True):
    project, target = metadata(hand=hand, expression=expression)
    permissions = tuple(IdleAuthoringPermission(name, digest, 'f'*64,
        'SYNTHETIC_TEST_ONLY_NOT_ACTUAL_SOURCE_PERMISSION', True)
        for name, digest in consumed_sources(project, target))
    return AuthoredIdleRequest(str(UUID(int=401)), canonical_bytes(project.to_dict()),
        target, '1'*64, permissions, 'NONSHIPPING original idle candidate metadata', True, True)


def with_project(candidate, project):
    """Bind a complete alternate synthetic project, preserving no stale digest."""
    return replace(candidate, project_snapshot_json=canonical_bytes(project.to_dict()),
        target=replace(candidate.target, project_sha256=document_sha256(project.to_dict())))


def synthetic_mpfb_axes():
    """Invented unit-scale landmarks for PUBLIC MPFB sign convention only.

    Anatomical left is +X, up is +Z, and front is -Y. These are not any saved
    human's measurements and provide no native anatomy/quality evidence.
    """
    return {'left_shoulder': (1.0, 0.0, 1.0),
            'right_shoulder': (-1.0, 0.0, 1.0),
            'up': (0.0, 0.0, 1.0), 'anterior': (0.0, -1.0, 0.0)}
