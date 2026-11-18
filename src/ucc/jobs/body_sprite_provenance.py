"""Pinned historical original-source declaration; never a sprite-rights grant."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from ucc.core.errors import ValidationError, ProjectConflict
from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
from ucc.core.target_action_format import checked_sha, checked_text, checked_uuid, document_sha256, closed
from ucc.core.body_sprites import ORIGIN_POLICY as POLICY
from ucc.core.target_action import TargetActionBinding
from ucc.export.godot_native_recipe import validate_native_recipe
from ucc.library.provenance import LicensePolicy
from .target_action_context import protected

AUDIT_STATUS = 'REAL_PREPARED_MASTER_NATIVE300_INDEPENDENTLY_AUDITED_AFTER_HARNESS_KEY_ERROR'


def _qualified_audit_record(raw, role, source):
    """Read the exact old audit format, including its failed original script."""
    closed(raw, {'Blender_work_reexecuted_for_audit','all300_source_pose_skin_root_palm_observations_rechecked',
        'animation_visual_quality_verified','engine_import_verified','independent_target_workers','mapped_joints',
        'mapping_sha256','master_sha256','next_task','original_script63_exit_success','preserved_originals',
        'private_views_independently_decoded','recorded_at','recovered_preview_sha256','retargeting_verified',
        'saved_reopen_job_id','skin_deformation_policy','snapshot_sha256','source_bones','source_first_frame',
        'source_fps','source_frames','source_permission','source_sha256','status','timeline_sha256'})
    if (role != 'source_permission' or raw['status'] != AUDIT_STATUS
            or raw['original_script63_exit_success'] is not False
            or raw['all300_source_pose_skin_root_palm_observations_rechecked'] is not True
            or raw['Blender_work_reexecuted_for_audit'] is not False
            or any(raw[key] is not False for key in ('animation_visual_quality_verified','engine_import_verified','retargeting_verified'))
            or type(raw['source_first_frame']) is not int or raw['source_first_frame'] != 2
            or type(raw['source_frames']) is not int or raw['source_frames'] != 300
            or type(raw['source_fps']) not in (int,float) or raw['source_fps'] != 30
            or type(raw['private_views_independently_decoded']) is not int or raw['private_views_independently_decoded'] != 15
            or raw['skin_deformation_policy'] != 'BOUND_CORRECTIVE_SMOOTH_V1'
            or raw['source_sha256'] != source.source_sha256 or raw['snapshot_sha256'] != source.snapshot_sha256):
        raise ProjectConflict('Qualified original-origin audit differs from its exact finite scope or selected motion')
    for key in ('mapping_sha256','master_sha256','recovered_preview_sha256','timeline_sha256'): checked_sha(raw[key])
    ids = raw['independent_target_workers']
    if type(ids) is not list or len(ids)!=2 or any(type(value) is not str for value in ids) or len(set(ids))!=2:
        raise ValidationError('Qualified origin audit lacks two independent target worker identities')
    for value in (*ids,raw['saved_reopen_job_id']): checked_uuid(value)
    for key in ('mapped_joints','source_bones'):
        if type(raw[key]) is not int or not 1<=raw[key]<=256: raise ValidationError('Qualified origin audit coverage is invalid')
    checked_text(raw['next_task'],2048); checked_text(raw['recorded_at'],160)
    originals = raw['preserved_originals']
    if type(originals) is not dict or not 1<=len(originals)<=32:
        raise ValidationError('Qualified origin audit original-source bindings are missing')
    for name,digest in originals.items(): checked_text(name,8192); checked_sha(digest)
    if source.source_sha256 not in originals.values(): raise ProjectConflict('Qualified origin audit lacks its source preservation binding')
    return LicensePolicy.from_dict(raw['source_permission'])

@dataclass(frozen=True, slots=True)
class OriginalMotionProvenance:
    record_path: Path
    expected_sha256: str
    motion_role: str
    uri_aliases: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        checked_sha(self.expected_sha256); checked_text(self.motion_role,160)
        if (not isinstance(self.record_path,Path) or not (self.motion_role.startswith('motion:') or self.motion_role=='source_permission')
                or type(self.uri_aliases) is not tuple or len(self.uri_aliases)>1
                or any(type(row) is not tuple or len(row)!=2 for row in self.uri_aliases)):
            raise ValidationError('Select an exact pinned original-author record and motion role')
        for row in self.uri_aliases:
            for value in row: checked_text(value,2048)

    def read(self, request, current_policy: LicensePolicy, budget) -> dict:
        return self.read_binding(request.target_binding, current_policy, budget)

    def read_binding(self, binding: TargetActionBinding, current_policy: LicensePolicy, budget) -> dict:
        """Review origin metadata before (and independently of) sprite consent."""
        if type(binding) is not TargetActionBinding:
            raise ValidationError('Origin review requires the exact typed saved target binding')
        budget.check(); path = protected(self.record_path)
        if not path.is_file() or path.stat().st_nlink != 1 or not 1<=path.stat().st_size<=256*1024:
            raise ValidationError('Original-author record must be one bounded canonical local file')
        with path.open('rb') as stream:
            payload = stream.read(256*1024+1)
        if len(payload)>256*1024 or sha256(payload).hexdigest()!=self.expected_sha256:
            raise ProjectConflict('The explicitly pinned original-author record changed')
        try:
            raw = json.loads(payload,object_pairs_hook=_unique_project_fields,parse_constant=_nonfinite_project_number)
        except (ValueError,UnicodeError,RecursionError) as error:
            raise ValidationError('Malformed original-author record') from error
        # Reuse the old closed record parser only to authenticate its metadata.
        # Its historical engine grants never authorize this new sprite operation.
        source = binding.source
        if type(raw) is dict and raw.get('status') == AUDIT_STATUS:
            old = _qualified_audit_record(raw,self.motion_role,source)
            record_format = 'INDEPENDENT_PREPARED_NATIVE300_AUDIT_V1'; status = AUDIT_STATUS; original_success = False
            if self.uri_aliases or old != current_policy:
                raise ProjectConflict('Qualified origin audit requires its exact original source policy without aliases')
        else:
            record = validate_native_recipe(raw)
            selected = [row for row in record['permissions'] if row['asset_id']==self.motion_role]
            if (record['motion_asset_id']!=self.motion_role or len(selected)!=1
                    or record['source_bindings'].get(self.motion_role)!=source.source_sha256
                    or selected[0]['source_sha256']!=source.source_sha256
                    or record['evidence_bindings']['source_snapshot']!=source.snapshot_sha256):
                raise ProjectConflict('Pinned original-author role/source/snapshot differs from the registered motion')
            old = LicensePolicy.from_dict(selected[0]['policy'])
            record_format = 'LEGACY_NATIVE_SOURCE_REVIEW_V1'; status = record['policy']; original_success = None
        if not old.source_uri.startswith('ucc-original-diagnostic://'):
            raise ValidationError('This initial sample requires the explicit original diagnostic provenance family')
        expected_alias = () if old.source_uri==current_policy.source_uri else ((old.source_uri,current_policy.source_uri),)
        if self.uri_aliases!=expected_alias:
            raise ProjectConflict('Original-author and catalog URIs need an exact explicit bound alias')
        # Engine flags are deliberately excluded: they neither grant nor revoke
        # sprite rights. Current policy is separately enforced by source authority.
        fields = ('provider','license_name','reviewed','no_ai','ue_only','ai_input_allowed',
                  'redistribute_source_allowed','local_preview_allowed')
        if any(getattr(old,key)!=getattr(current_policy,key) for key in fields):
            raise ProjectConflict('Original-author declaration and current catalog policy lineage differ')
        if document_sha256(current_policy.to_dict())!=source.catalog_policy_sha256:
            raise ProjectConflict('Current original-motion policy differs from the registered Action')
        return {'policy':POLICY,'record_sha256':self.expected_sha256,'motion_role':self.motion_role,
            'record_format':record_format,'record_status':status,'original_script_exit_success':original_success,
            'source_sha256':source.source_sha256,'snapshot_sha256':source.snapshot_sha256,
            'record_policy_sha256':document_sha256(old.to_dict()),
            'catalog_policy_sha256':source.catalog_policy_sha256,
            'record_source_uri':old.source_uri,'catalog_source_uri':current_policy.source_uri,
            'uri_aliases':[list(row) for row in self.uri_aliases],
            'origin_declaration_only':True,'sprite_rights_inferred':False}


def review_original_motion_record(path: Path, binding: TargetActionBinding,
                                  current_policy: LicensePolicy, budget) -> tuple[OriginalMotionProvenance, dict]:
    """Pin one selected record and infer its unique role; never create grants."""
    budget.check(); path = protected(path)
    if not path.is_file() or path.stat().st_nlink != 1:
        raise ValidationError('Choose one canonical local original-origin record')
    with path.open('rb') as stream:
        payload = stream.read(256*1024+1)
    if not 1 <= len(payload) <= 256*1024:
        raise ValidationError('Original-origin record exceeds its metadata limit')
    try:
        raw = json.loads(payload, object_pairs_hook=_unique_project_fields,
                         parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed original-author record') from error
    if type(binding) is not TargetActionBinding:
        raise ValidationError('Origin review requires the exact typed saved target binding')
    if type(raw) is dict and raw.get('status') == AUDIT_STATUS:
        role = 'source_permission'
    else:
        record = validate_native_recipe(raw)
        roles = [row['asset_id'] for row in record['permissions']
                 if row['asset_id'].startswith('motion:')
                 and row['source_sha256'] == binding.source.source_sha256
                 and record['source_bindings'].get(row['asset_id']) == binding.source.source_sha256]
        if (len(roles) != 1 or record['motion_asset_id'] != roles[0]
                or record['evidence_bindings']['source_snapshot'] != binding.source.snapshot_sha256):
            raise ValidationError('Origin record must identify one exact selected motion role and snapshot')
        role = roles[0]
    origin = OriginalMotionProvenance(path, sha256(payload).hexdigest(), role)
    return origin, origin.read_binding(binding, current_policy, budget)
