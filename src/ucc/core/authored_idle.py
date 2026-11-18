"""Original procedural idle intent; pure metadata, never native/rights admission.

This fixed candidate is independently composed from semantic anatomy, not from
an existing motion. Private workers must measure the saved neutral rig, solve a
relaxed standing baseline, validate it, then apply the original periodic offsets.
No geometry, transforms, pose samples, executable expressions or standalone I/O
paths belong here. The full project snapshot retains its guarded relative
references. A matching digest does not prove authorship or permission.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

from .models import CharacterProject
from .target_action import TargetActionTarget
from .target_action_format import (
    CLOCK, canonical_bytes, checked_sha, checked_text, checked_uuid, closed,
    document_sha256, read_document, require,
)

POLICY = 'UCC_ORIGINAL_PROCEDURAL_IDLE_CANDIDATE_V1'
INSPECTION_POLICY = 'UCC_ORIGINAL_IDLE_NEUTRAL_INSPECTION_V1'
AUTHORING_USE = 'PRIVATE_LOCAL_IDLE_AUTHORING_AND_DERIVED_RIG_V1'
PROFILE = 'MPFB_RELAXED_STANDING_IDLE_V1'
CLEAR_IDLE_PROFILE = 'MPFB_CLEAR_STANDING_IDLE_V1'
FRAME_POLICY = 'MEASURED_RIGHT_HANDED_ANATOMICAL_FRAME_V1'
BASELINE_POLICY = 'MEASURED_T_POSE_TO_RELAXED_STANDING_V1'
PERIOD_POLICY = 'UNIQUE_300_SAMPLES_ANALYTIC_PERIODIC_V1'
_PROFILE_AMPLITUDES = {PROFILE: (0.5, -0.25, 0.5), CLEAR_IDLE_PROFILE: (3.0, -1.5, 3.0)}

_FIXED_FLAGS = (
    ('private_local_only', True),
    ('existing_motion_read_authorized', False),
    ('existing_motion_derivation_authorized', False),
    ('existing_motion_references_preserved', True),
    ('source_master_mutation_authorized', False),
    ('source_or_motion_redistribution_authorized', False),
    ('sprite_use_authorized', False),
    ('engine_use_authorized', False),
    ('cloud_transmission_authorized', False),
    ('ai_input_authorized', False),
    ('origin_declaration_is_authorship_proof', False),
    ('native_authoring_verified', False),
    ('saved_reopen_verified', False),
    ('quality_measurements_verified', False),
    ('human_visual_review_approved', False),
    ('loop_quality_approved', False),
    ('usable_action_approved', False),
)


def clock_spec() -> dict:
    """Stored clock is unchanged; periodic intent does not change transport."""
    return {
        'stored_clock': dict(CLOCK),
        'sample_count': 300,
        'sample_span_numerator_s': 299,
        'sample_span_denominator_s': 30,
        'nominal_coverage_numerator_s': 10,
        'nominal_coverage_denominator_s': 1,
        'period_policy': PERIOD_POLICY,
        'phase_numerator': 'target_frame_minus_one',
        'phase_denominator': 300,
        'duplicate_terminal_sample': False,
        'virtual_seam_target_frame': 301,
        'virtual_seam_source_frame': 302,
        'virtual_seam_is_stored_sample': False,
        'virtual_seam_is_phase_zero': True,
    }


def baseline_spec() -> dict:
    """Normative candidate parameters, not axes guessed from local Euler names.

    Worker interpretation: measure up from pelvis to neck; orthogonalize right
    from left-to-right shoulders against up; forward=up cross right. The
    right-handed basis order is (right, forward, up), not (right, up, forward).
    Corroborate anterior direction against actual neutral foot-to-toe anatomy;
    reject ambiguous/mirrored frames. Side means measured outward, not local X.
    Drop is downward from the measured lateral T direction. Forward tilt is
    toward measured forward; elbow flex bends toward forward. Palm orientation
    and digit-flex axes require measured hand anatomy, not copied rest roll.
    Solve using rotations through the real hierarchy, including helper bones;
    never translate/scale a child or silently use IK that violates these rules.
    """
    return {
        'policy': BASELINE_POLICY,
        'anatomical_frame_policy': FRAME_POLICY,
        'up_definition': 'PELVIS_TO_NECK',
        'right_definition': 'LEFT_TO_RIGHT_SHOULDERS_ORTHOGONAL_TO_UP',
        'forward_definition': 'UP_CROSS_RIGHT',
        'side_policy': 'MEASURED_OUTWARD_MIRRORED_SEMANTICS',
        'root_policy': 'FIX_ACTUAL_NEUTRAL_ROOT_TRANSFORM',
        'lower_chain_policy': 'FIX_ALL_NEUTRAL_PELVIS_LEG_FOOT_TOE_HELPERS',
        'upper_arm_drop_from_lateral_deg': 65.0,
        'upper_arm_forward_tilt_deg': 8.0,
        'elbow_forward_flex_deg': 15.0,
        'palm_facing': 'MEDIAL_TOWARD_THIGH_FROM_MEASURED_HAND_FRAME',
        'finger_flex_from_rest_deg': [12.0, 18.0, 10.0],
        'thumb_flex_from_rest_deg': 8.0,
        'torso_and_head_reference': 'MEASURED_NEUTRAL_STANDING',
        'unaddressed_bones': 'EXPLICIT_IDENTITY_ROTATION_RELATIVE_TO_NEUTRAL',
        'nonroot_translation': 'ZERO',
        'all_local_scales': 'UNIT',
        'constraints_or_drivers': 'REJECT_UNMODELED_EVALUATION_DEPENDENCIES',
        'fitting_failure': 'REJECT_NEVER_FALL_BACK_TO_T_POSE',
    }


def _check_profile(profile: str) -> None:
    require(type(profile) is str and profile in _PROFILE_AMPLITUDES, 'Choose a supported original idle recipe profile')


def periodic_spec(profile: str = PROFILE) -> dict:
    """A closed original motion function, with no expression evaluator.

    Offsets are anatomical rotations relative to the SOLVED relaxed baseline.
    Workers implement this named policy with their own math, not eval/exec.
    phase(k)=2*pi*k/300, k=target_frame-1. One ten-second cycle is sampled at
    k=0..299; k=300 is a quality probe, not an appended duplicate keyframe.
    """
    _check_profile(profile)
    torso, head, elbow = _PROFILE_AMPLITUDES[profile]
    return {
        'policy': PERIOD_POLICY,
        'basis': 'ONE_CYCLE_SINE_WITH_ZERO_PHASE',
        'rotation_composition': 'ANATOMICAL_OFFSETS_AFTER_SOLVED_BASELINE',
        'cycles_per_period': 1,
        'torso_forward_pitch_amplitude_deg': torso,
        'head_counter_pitch_amplitude_deg': head,
        'bilateral_elbow_flex_amplitude_deg': elbow,
        'other_offsets': 'ZERO',
        'root_and_lower_chain_offsets': 'ZERO',
        'quaternion_policy': 'NORMALIZED_SIGN_CONTINUOUS_THROUGH_VIRTUAL_SEAM',
        'bake_policy': 'ALL_300_NATIVE_SAMPLES_NO_OPTIMIZER',
        'candidate_wrap_interpolation': 'LAST_TO_FIRST_OVER_ONE_SAMPLE_INTERVAL',
        'wrap_interpolation_is_current_binding_transport': False,
    }


def required_quality_spec() -> dict:
    """Required future checks, NEVER measurements or an approval document."""
    return {
        'full_sample_count': 300,
        'root_reference': 'ACTUAL_NEUTRAL_WORLD_TRANSFORM',
        'root_max_translation_m': 0.000001,
        'root_max_rotation_rad': 0.000001,
        'foot_contact_reference': 'MEASURED_NEUTRAL_SOLE_PATCHES_BOTH_FEET',
        'max_sole_world_drift_m': 0.001,
        'seam_policy': 'COMPARE_ANALYTIC_PHASE_ZERO_AND_PHASE_ONE_PERIOD',
        'seam_derivatives': 'WRAPPED_SAMPLE_STEP_VELOCITIES_VS_ORIGINAL_ANALYTIC_REFERENCE',
        'analytic_periodicity': 'VALUE_AND_FIRST_DERIVATIVE_AT_ZERO_AND_TEN_SECONDS',
        'seam_max_position_residual_m': 0.000001,
        'seam_max_rotation_residual_rad': 0.000001,
        'velocity_residual_policy': 'SAME_SAMPLE_INTERVAL_REFERENCE_NOT_ZERO_OR_CONTINUOUS_DERIVATIVE',
        'stored_first_last_equality_required': False,
        'seam_is_not_duplicate_endpoint_hold': True,
        'all_frames_finite_unit_scale_no_nonroot_translation': True,
        'hand_quality': 'PALMS_DIGITS_BODY_CLEARANCE_AND_BOTH_SIDES_REVIEW',
        'human_review': 'RELAXED_STANCE_NATURAL_IDLE_LOOP_FEET_HANDS',
        'save_reopen_and_transport_required': True,
        'numeric_report_can_approve_usable_action': False,
    }


@dataclass(frozen=True, slots=True)
class IdleAuthoringPermission:
    """A new per-use declaration; host must recheck the actual current policy."""
    asset_id: str
    source_sha256: str
    source_policy_sha256: str
    note: str
    authoring_and_derived_rig_confirmed: bool

    def __post_init__(self) -> None:
        checked_text(self.asset_id, 200)
        checked_sha(self.source_sha256)
        checked_sha(self.source_policy_sha256)
        checked_text(self.note, 2000)
        require(self.authoring_and_derived_rig_confirmed is True,
                'Each consumed source needs separate idle authoring and derived-rig permission')

    def to_dict(self) -> dict:
        return {
            'asset_id': self.asset_id, 'source_sha256': self.source_sha256,
            'source_policy_sha256': self.source_policy_sha256, 'note': self.note,
            'authoring_and_derived_rig_confirmed': self.authoring_and_derived_rig_confirmed,
            'use': AUTHORING_USE, 'no_ai': True, 'private_local_only': True,
            'sprite_rights_inferred': False, 'engine_rights_inferred': False,
            'redistribution_rights_inferred': False,
        }

    @classmethod
    def from_dict(cls, raw: object) -> 'IdleAuthoringPermission':
        value = closed(raw, {'asset_id', 'source_sha256', 'source_policy_sha256', 'note',
            'authoring_and_derived_rig_confirmed', 'use', 'no_ai', 'private_local_only',
            'sprite_rights_inferred', 'engine_rights_inferred', 'redistribution_rights_inferred'})
        result = cls(*(value[name] for name in cls.__dataclass_fields__))
        require(canonical_bytes(value) == canonical_bytes(result.to_dict()),
                'Idle authoring use or policy flags were changed')
        return result


def saved_authoring_sources(project: CharacterProject) -> tuple[tuple[str, str], ...]:
    """Sources retained in the bounded neutral character, never motion inputs.

    No existing clip is consumed, even when its reference remains in the saved
    snapshot. Host admission must prove copied authoring inputs do not include
    or evaluate those Actions. Master-derived rig is explicitly a consumed use.
    """
    require(type(project) is CharacterProject,
            'Idle authoring needs the complete typed saved project')
    master = re.fullmatch(r'master/versions/([a-f0-9]{64})\.blend', project.master_blend or '')
    require(master is not None and project.geometry_state != 'not_generated'
            and project.appearance == (),
            'Initial idle authoring needs a content-addressed saved generated master without saved appearance')
    sources = {'master_and_derived_rig': master[1]}
    if project.expression is not None:
        sources['expression_library'] = project.expression.library_sha256
    require(len(project.parts) <= 1, 'Initial idle authoring supports at most the admitted left hand')
    for part in project.parts:
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        require(part.slot == 'hand.L' and part.visible is True and part.status == 'proposed'
                and match is not None, 'Idle authoring needs the exact supported hand identity')
        sources['part:'+part.part_asset_id] = match[1]
    return tuple(sorted(sources.items()))


def consumed_sources(project: CharacterProject, target: TargetActionTarget) -> tuple[tuple[str, str], ...]:
    """Post-measurement source set additionally bound to the actual neutral target."""
    sources = saved_authoring_sources(project)
    require(type(target) is TargetActionTarget,
            'Idle authoring needs the actual measured typed neutral target')
    require(project.project_id == target.project_id and project.revision == target.revision
            and dict(sources)['master_and_derived_rig'] == target.master_sha256
            and document_sha256(project.to_dict()) == target.project_sha256,
            'Idle neutral target differs from the complete saved project snapshot')
    return sources


def _saved_project(payload: bytes) -> CharacterProject:
    snapshot = read_document(payload)
    project = CharacterProject.from_dict(snapshot)
    require(canonical_bytes(project.to_dict()) == canonical_bytes(snapshot),
            'Idle authoring requires the entire canonical saved project snapshot')
    return project


def _authoring_review(permissions: tuple[IdleAuthoringPermission, ...],
        sources: tuple[tuple[str, str], ...], purpose: str,
        original_declared: bool, private_preview_confirmed: bool) -> None:
    checked_text(purpose, 2000)
    expected = dict(sources)
    require(type(permissions) is tuple and len(permissions) == len(expected)
            and all(type(item) is IdleAuthoringPermission for item in permissions)
            and len({item.asset_id for item in permissions}) == len(expected)
            and {item.asset_id: item.source_sha256 for item in permissions} == expected
            and tuple(item.asset_id for item in permissions) == tuple(sorted(expected)),
            'Review exactly every consumed source for this new authoring use, in canonical order')
    require(original_declared is True and private_preview_confirmed is True,
            'Declare the original recipe and explicitly authorize private preview of its derived output')


@dataclass(frozen=True, slots=True)
class AuthoredIdleInspectionRequest:
    """Authorize neutral rest measurement before target/frame digests exist.

    Actual files and policies still need host admission. This document cannot
    authorize Action creation, sample existing motion or claim a measurement.
    """
    job_id: str
    project_snapshot_json: bytes
    permissions: tuple[IdleAuthoringPermission, ...]
    purpose: str
    original_procedural_recipe_declared: bool
    private_authored_output_preview_confirmed: bool
    profile: str = PROFILE

    def __post_init__(self) -> None:
        checked_uuid(self.job_id)
        _check_profile(self.profile)
        project = _saved_project(self.project_snapshot_json)
        _authoring_review(self.permissions, saved_authoring_sources(project), self.purpose,
            self.original_procedural_recipe_declared, self.private_authored_output_preview_confirmed)
        canonical_bytes(self.to_dict())

    @property
    def project(self) -> CharacterProject:
        return _saved_project(self.project_snapshot_json)

    @property
    def sha256(self) -> str:
        return document_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            'schema_version': 1, 'policy': INSPECTION_POLICY, 'profile': self.profile,
            'job_id': self.job_id, 'project_snapshot': read_document(self.project_snapshot_json),
            'project_snapshot_sha256': sha256(self.project_snapshot_json).hexdigest(),
            'consumed_sources': dict(saved_authoring_sources(self.project)),
            'permissions': [item.to_dict() for item in self.permissions], 'purpose': self.purpose,
            'original_procedural_recipe_declared': self.original_procedural_recipe_declared,
            'private_authored_output_preview_confirmed': self.private_authored_output_preview_confirmed,
            'anatomical_frame_policy': FRAME_POLICY,
            'inspection_scope': 'NEUTRAL_REST_ANATOMY_NO_ACTION_EVALUATION_V1',
            'measurement_only': True, 'measurement_verified': False,
            'authoring_execution_authorized': False, 'animation_sampling_authorized': False,
            **dict(_FIXED_FLAGS),
        }

    @classmethod
    def from_dict(cls, raw: object) -> 'AuthoredIdleInspectionRequest':
        value = closed(raw, {'schema_version', 'policy', 'profile', 'job_id', 'project_snapshot',
            'project_snapshot_sha256', 'consumed_sources', 'permissions', 'purpose',
            'original_procedural_recipe_declared', 'private_authored_output_preview_confirmed',
            'anatomical_frame_policy', 'inspection_scope', 'measurement_only', 'measurement_verified',
            'authoring_execution_authorized', 'animation_sampling_authorized', *(key for key, _ in _FIXED_FLAGS)})
        require(type(value['permissions']) is list, 'Idle inspection needs an explicit permission list')
        result = cls(value['job_id'], canonical_bytes(value['project_snapshot']),
            tuple(IdleAuthoringPermission.from_dict(item) for item in value['permissions']),
            value['purpose'], value['original_procedural_recipe_declared'],
            value['private_authored_output_preview_confirmed'], profile=value['profile'])
        require(canonical_bytes(value) == canonical_bytes(result.to_dict()),
                'Idle inspection changed a closed input, use, phase or readiness field')
        return result

    @classmethod
    def from_bytes(cls, payload: bytes) -> 'AuthoredIdleInspectionRequest':
        return cls.from_dict(read_document(payload))


@dataclass(frozen=True, slots=True)
class AuthoredIdleRequest:
    job_id: str
    project_snapshot_json: bytes
    target: TargetActionTarget
    anatomical_frame_sha256: str
    permissions: tuple[IdleAuthoringPermission, ...]
    purpose: str
    original_procedural_recipe_declared: bool
    private_authored_output_preview_confirmed: bool
    profile: str = PROFILE

    def __post_init__(self) -> None:
        checked_uuid(self.job_id)
        checked_sha(self.anatomical_frame_sha256)
        project = _saved_project(self.project_snapshot_json)
        _authoring_review(self.permissions, consumed_sources(project, self.target), self.purpose,
            self.original_procedural_recipe_declared, self.private_authored_output_preview_confirmed)
        canonical_bytes(self.to_dict())

    @property
    def project(self) -> CharacterProject:
        return _saved_project(self.project_snapshot_json)

    @property
    def sha256(self) -> str:
        return document_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            'schema_version': 1, 'policy': POLICY, 'profile': self.profile,
            'job_id': self.job_id, 'project_snapshot': read_document(self.project_snapshot_json),
            'project_snapshot_sha256': sha256(self.project_snapshot_json).hexdigest(),
            'target': self.target.to_dict(), 'anatomical_frame_sha256': self.anatomical_frame_sha256,
            'consumed_sources': dict(consumed_sources(self.project, self.target)),
            'permissions': [item.to_dict() for item in self.permissions],
            'purpose': self.purpose,
            'original_procedural_recipe_declared': self.original_procedural_recipe_declared,
            'private_authored_output_preview_confirmed': self.private_authored_output_preview_confirmed,
            'clock': clock_spec(), 'baseline': baseline_spec(), 'periodic_motion': periodic_spec(self.profile),
            'required_quality': required_quality_spec(), **dict(_FIXED_FLAGS),
        }

    @classmethod
    def from_dict(cls, raw: object) -> 'AuthoredIdleRequest':
        value = closed(raw, {'schema_version', 'policy', 'profile', 'job_id', 'project_snapshot',
            'project_snapshot_sha256', 'target', 'anatomical_frame_sha256', 'consumed_sources',
            'permissions', 'purpose', 'original_procedural_recipe_declared',
            'private_authored_output_preview_confirmed', 'clock', 'baseline', 'periodic_motion',
            'required_quality', *(key for key, _ in _FIXED_FLAGS)})
        require(type(value['permissions']) is list, 'Idle permissions must be a closed explicit list')
        result = cls(value['job_id'], canonical_bytes(value['project_snapshot']),
            TargetActionTarget.from_dict(value['target']), value['anatomical_frame_sha256'],
            tuple(IdleAuthoringPermission.from_dict(item) for item in value['permissions']),
            value['purpose'], value['original_procedural_recipe_declared'],
            value['private_authored_output_preview_confirmed'], profile=value['profile'])
        require(canonical_bytes(value) == canonical_bytes(result.to_dict()),
                'Idle candidate changed its closed recipe, clock, source, target, or readiness policy')
        return result

    @classmethod
    def from_bytes(cls, payload: bytes) -> 'AuthoredIdleRequest':
        return cls.from_dict(read_document(payload))
