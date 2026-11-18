"""Private sample intent over an existing registered Action; no native admission.

The full target binding remains intact. A selected window changes only which
absolute frames are requested as images. Rights and original-authored provenance
must still be independently checked by a future host before any rendering.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

from .models import CharacterProject
from .skin_material import SkinMaterialSpec
from .sprite_render import SpritePermission, SpriteSettings
from .target_action import TargetActionBinding
from .target_action_format import (
    CLOCK, canonical_bytes, checked_sha, checked_text, checked_uuid, closed, document_sha256,
    read_document, require,
)

POLICY = 'UCC_PRIVATE_REGISTERED_BODY_SPRITE_SAMPLE_V1'
MATERIAL_POLICY = 'COPIES_ONLY_REQUEST_BOUND_MATTE_V1'
ORIGIN_POLICY = 'PINNED_ORIGINAL_MOTION_DECLARATION_V1'
STAGE = 'stage_registered_body_sprites'
VERIFY = 'verify_registered_body_sprites'
WORKER_FIELDS = frozenset({'master_sha256', 'recipe_sha256', 'target_binding_sha256',
                           'review_sha256', 'snapshot_sha256', 'mapping_sha256', 'timeline_sha256'})
MAX_SAMPLE_FRAMES = 32
_CLOCK = dict(CLOCK)
_OFFSET = _CLOCK['source_first_frame']-_CLOCK['target_first_frame']
_FLAGS = (
    ('private_sample_only', True),
    ('source_material_slots_must_be_empty', True),
    ('project_publication_authorized', False),
    ('project_metadata_changed', False),
    ('animation_clip_delivery_authorized', False),
    ('source_redistribution_authorized', False),
    ('sprite_redistribution_authorized', False),
    ('cloud_transmission_authorized', False),
    ('ai_input_authorized', False),
    ('rendering_verified', False),
    ('engine_import_verified', False),
    ('visual_quality_approved', False),
    ('usable_action_approved', False),
    ('loop_quality_approved', False),
    ('distribution_license_review_complete', False),
)


@dataclass(frozen=True, slots=True)
class BodySpriteWindow:
    """Inclusive absolute target frames, preserving the binding's source clock."""
    target_first_frame: int
    target_last_frame: int

    def __post_init__(self) -> None:
        require(type(self.target_first_frame) is int and type(self.target_last_frame) is int
                and _CLOCK['target_first_frame'] <= self.target_first_frame
                <= self.target_last_frame <= _CLOCK['target_last_frame']
                and self.sample_count <= MAX_SAMPLE_FRAMES,
                'Select one contiguous body-sprite window of 1-32 target frames within 1-300')

    @property
    def sample_count(self) -> int:
        return self.target_last_frame-self.target_first_frame+1

    @property
    def target_frames(self) -> tuple[int, ...]:
        return tuple(range(self.target_first_frame, self.target_last_frame+1))

    @property
    def source_frames(self) -> tuple[int, ...]:
        return tuple(frame+_OFFSET for frame in self.target_frames)

    def to_dict(self) -> dict:
        fps = _CLOCK['fps_numerator']/_CLOCK['fps_denominator']
        return {
            'target_first_frame': self.target_first_frame,
            'target_last_frame': self.target_last_frame,
            'source_first_frame': self.target_first_frame+_OFFSET,
            'source_last_frame': self.target_last_frame+_OFFSET,
            'sample_count': self.sample_count,
            'fps_numerator': _CLOCK['fps_numerator'],
            'fps_denominator': _CLOCK['fps_denominator'],
            'sample_span_s': (self.sample_count-1)/fps,
            'nominal_coverage_s': self.sample_count/fps,
        }

    @classmethod
    def from_dict(cls, raw: object) -> 'BodySpriteWindow':
        value = closed(raw, {'target_first_frame', 'target_last_frame', 'source_first_frame',
                             'source_last_frame', 'sample_count', 'fps_numerator',
                             'fps_denominator', 'sample_span_s', 'nominal_coverage_s'})
        result = cls(value['target_first_frame'], value['target_last_frame'])
        require(canonical_bytes(value) == canonical_bytes(result.to_dict()),
                'Body-sprite selected clock cannot shift, retime or resample the registered Action')
        return result


def body_sprite_sources(project: CharacterProject, binding: TargetActionBinding) -> tuple[tuple[str, str], ...]:
    """Derive the complete rendered-source review set from immutable metadata."""
    require(type(project) is CharacterProject and type(binding) is TargetActionBinding,
            'Body sprites require the complete typed project and registered target binding')
    target = binding.target
    require(project.project_id == target.project_id and project.revision == target.revision
            and project.master_blend == 'master/versions/'+target.master_sha256+'.blend'
            and project.geometry_state != 'not_generated' and project.expression is not None
            and project.appearance == () and binding.source.clip_id in project.animations,
            'Body-sprite sources must match the saved prepared character and registered Action without saved materials')
    require(len(project.parts) <= 1,
            'This body-sprite sample supports at most the existing registered left-hand part')
    sources = {'master': target.master_sha256,
               'expression_library': project.expression.library_sha256,
               'motion:'+binding.source.clip_id: binding.source.source_sha256}
    for part in project.parts:
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        require(part.slot == 'hand.L' and part.visible is True and part.status == 'proposed'
                and match is not None, 'Body sprites require the existing exact registered left-hand identity')
        sources['part:'+part.part_asset_id] = match[1]
    return tuple(sorted(sources.items()))


@dataclass(frozen=True, slots=True)
class BodySpriteRequest:
    job_id: str
    project_snapshot_json: bytes
    target_binding: TargetActionBinding
    window: BodySpriteWindow
    settings: SpriteSettings
    temporary_matte: SkinMaterialSpec
    permissions: tuple[SpritePermission, ...]
    purpose: str
    original_authored_motion_confirmed: bool

    def __post_init__(self) -> None:
        checked_uuid(self.job_id); checked_text(self.purpose, 2000)
        snapshot = read_document(self.project_snapshot_json)
        require(canonical_bytes(self.project.to_dict()) == canonical_bytes(snapshot),
                'Body sprites require the complete canonical saved project snapshot')
        sources = dict(body_sprite_sources(self.project, self.target_binding))
        require(type(self.window) is BodySpriteWindow and type(self.settings) is SpriteSettings
                and type(self.temporary_matte) is SkinMaterialSpec
                and self.temporary_matte.roughness == 1.0,
                'Body sprites require the bounded existing camera grid and explicit temporary matte parameters')
        require(self.original_authored_motion_confirmed is True,
                'This initial body-sprite sample requires an explicit original-authored motion declaration')
        require(type(self.permissions) is tuple and len(self.permissions) == len(sources)
                and all(type(permission) is SpritePermission for permission in self.permissions)
                and len({permission.asset_id for permission in self.permissions}) == len(sources)
                and {permission.asset_id: permission.source_sha256 for permission in self.permissions} == sources,
                'Separately review the exact master, expression, hand and selected motion for this private sprite use')
        canonical_bytes(self.to_dict())

    @property
    def project(self) -> CharacterProject:
        return CharacterProject.from_dict(read_document(self.project_snapshot_json))

    @property
    def source_bindings(self) -> tuple[tuple[str, str], ...]:
        return body_sprite_sources(self.project, self.target_binding)

    @property
    def image_count(self) -> int:
        return self.window.sample_count*self.settings.directions

    @property
    def sha256(self) -> str:
        return document_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            'schema_version': 1, 'policy': POLICY, 'job_id': self.job_id,
            'project_snapshot': read_document(self.project_snapshot_json),
            'project_snapshot_sha256': sha256(self.project_snapshot_json).hexdigest(),
            'target_binding': self.target_binding.to_dict(),
            'target_binding_sha256': self.target_binding.sha256,
            'full_clock': dict(CLOCK), 'window': self.window.to_dict(),
            'settings': self.settings.to_dict(), 'image_count': self.image_count,
            'temporary_material_policy': MATERIAL_POLICY,
            'temporary_matte': self.temporary_matte.to_dict(),
            'temporary_matte_sha256': self.temporary_matte.sha256,
            'source_bindings': dict(self.source_bindings),
            'permissions': [permission.to_dict() for permission in self.permissions],
            'purpose': self.purpose,
            'original_authored_motion_confirmed': self.original_authored_motion_confirmed,
            **dict(_FLAGS),
        }

    @classmethod
    def from_dict(cls, raw: object) -> 'BodySpriteRequest':
        value = closed(raw, {'schema_version', 'policy', 'job_id', 'project_snapshot',
                             'project_snapshot_sha256',
                             'target_binding', 'target_binding_sha256', 'full_clock', 'window',
                             'settings', 'image_count', 'temporary_material_policy', 'temporary_matte',
                             'temporary_matte_sha256', 'source_bindings', 'permissions', 'purpose',
                             'original_authored_motion_confirmed', *(name for name, _ in _FLAGS)})
        require(type(value['permissions']) is list, 'Body-sprite permissions must be an explicit list')
        result = cls(value['job_id'], canonical_bytes(value['project_snapshot']),
                     TargetActionBinding.from_dict(value['target_binding']),
                     BodySpriteWindow.from_dict(value['window']), SpriteSettings.from_dict(value['settings']),
                     SkinMaterialSpec.from_dict(value['temporary_matte']),
                     tuple(SpritePermission.from_dict(item) for item in value['permissions']),
                     value['purpose'], value['original_authored_motion_confirmed'])
        require(canonical_bytes(value) == canonical_bytes(result.to_dict()),
                'Body-sprite request changed a closed source, clock, material or readiness field')
        return result

    @classmethod
    def from_bytes(cls, payload: bytes) -> 'BodySpriteRequest':
        return cls.from_dict(read_document(payload))


def validate_recipe(raw: object) -> dict:
    value = closed(raw, {'schema_version', 'policy', 'request', 'source_admission'})
    request = BodySpriteRequest.from_dict(value['request'])
    admission = closed(value['source_admission'],
                       {'source_sha256', 'snapshot_sha256', 'worker_job_ids', 'worker_records', 'original_motion_provenance'})
    require(admission['source_sha256'] == request.target_binding.source.source_sha256
            and admission['snapshot_sha256'] == request.target_binding.source.snapshot_sha256,
            'Fresh body-sprite source admission differs from its registered motion')
    ids = admission['worker_job_ids']; records = admission['worker_records']
    require(type(ids) is list and len(ids) == 2 and type(records) is list and len(records) == 2,
            'Body-sprite source admission requires two fresh actual intake workers')
    for identity in ids: checked_uuid(identity)
    require(len(set(ids)) == 2 and not set(ids).intersection(request.target_binding.producer.worker_job_ids),
            'Body-sprite source workers must be fresh and distinct from the retained producer')
    for record in records:
        closed(record, {'request_sha256', 'result_sha256'})
        for digest in record.values(): checked_sha(digest)
    require(all(len({record[key] for record in records}) == 2 for key in ('request_sha256','result_sha256')),
            'Body-sprite source admission cannot reuse one worker record twice')
    origin = closed(admission['original_motion_provenance'], {'policy','record_sha256','motion_role',
        'record_format','record_status','original_script_exit_success',
        'source_sha256','snapshot_sha256','record_policy_sha256','catalog_policy_sha256',
        'record_source_uri','catalog_source_uri','uri_aliases','origin_declaration_only','sprite_rights_inferred'})
    for key in ('record_sha256','record_policy_sha256','catalog_policy_sha256'): checked_sha(origin[key])
    checked_text(origin['motion_role'],160)
    for key in ('record_source_uri','catalog_source_uri'): checked_text(origin[key],2048)
    aliases = [] if origin['record_source_uri']==origin['catalog_source_uri'] else [[origin['record_source_uri'],origin['catalog_source_uri']]]
    declared = (origin['record_format']=='LEGACY_NATIVE_SOURCE_REVIEW_V1'
        and origin['record_status']=='MPFB_NATIVE_RUNTIME_SOURCE_V1' and origin['original_script_exit_success'] is None
        and origin['motion_role'].startswith('motion:')) or (
        origin['record_format']=='INDEPENDENT_PREPARED_NATIVE300_AUDIT_V1'
        and origin['record_status']=='REAL_PREPARED_MASTER_NATIVE300_INDEPENDENTLY_AUDITED_AFTER_HARNESS_KEY_ERROR'
        and origin['original_script_exit_success'] is False and origin['motion_role']=='source_permission')
    require(origin['policy']==ORIGIN_POLICY and declared
            and origin['record_source_uri'].startswith('ucc-original-diagnostic://')
            and origin['source_sha256']==admission['source_sha256'] and origin['snapshot_sha256']==admission['snapshot_sha256']
            and origin['catalog_policy_sha256']==request.target_binding.source.catalog_policy_sha256
            and origin['origin_declaration_only'] is True and origin['sprite_rights_inferred'] is False
            and canonical_bytes(origin['uri_aliases'])==canonical_bytes(aliases),
            'Body-sprite source admission lost its exact pinned original declaration and separate sprite-rights scope')
    expected = {'schema_version': 1, 'policy': POLICY, 'request': request.to_dict(),
                'source_admission': admission}
    require(canonical_bytes(value) == canonical_bytes(expected), 'Malformed closed registered body-sprite recipe')
    return expected


def worker_bindings(request: BodySpriteRequest, recipe_sha256: str) -> dict[str, str]:
    require(type(request) is BodySpriteRequest, 'Body-sprite workers require their typed exact request')
    checked_sha(recipe_sha256)
    binding = request.target_binding
    return {
        'master_sha256': binding.target.master_sha256, 'recipe_sha256': recipe_sha256,
        'target_binding_sha256': binding.sha256,
        'review_sha256': binding.file_map['body_first/review_motion.blend'].sha256,
        'snapshot_sha256': binding.source.snapshot_sha256,
        'mapping_sha256': binding.mapping_sha256,
        'timeline_sha256': binding.file_map['body_first/target_timeline.json'].sha256,
    }


def validate_job(operation: str, input_project: object, options: object) -> None:
    fields = set(WORKER_FIELDS) | ({'scene_sha256', 'stage_sha256'} if operation == VERIFY else set())
    require(operation in (STAGE, VERIFY) and input_project == 'candidate.blend'
            and type(options) is dict and set(options) == fields,
            'Body-sprite workers require fixed staged files and complete closed hash bindings')
    for value in options.values(): checked_sha(value)
