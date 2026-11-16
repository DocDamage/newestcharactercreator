"""Read-only admission and mutation watches for a private Godot candidate.

This admits staged verification inputs, not a new Blender master or shipping
export. The production Blender producer/reopen integration is still required.
"""
from array import array
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
import stat as stat_types
import struct
import sys
from threading import Event

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expressions import TARGETS
from ucc.core.storage import ProjectStore, _unique_project_fields, _nonfinite_project_number
from ucc.export.godot_candidate_contract import GodotCandidateRequest, canonical_bytes
from ucc.export.godot_skin_plan import build_skin_plan
from .expression_verification import registered_expression_source
from .hand_storage import load_hand_library
from .master_preview import _master_file, _digest

LIMITS = {'character.glb': 512*1024*1024, 'skin_plan.json': 64*1024*1024,
          'blender_stage.json': 4*1024*1024, 'source_positions.bin': 25*13380*3*4,
          'bind_source_indices.json': 4*1024*1024, 'bind_positions.bin': 13380*3*4,
          'blender_verification.json': 4*1024*1024}


def check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ProjectStorageError('Godot candidate cancelled; project and master remain authoritative')


def read_json(path: Path, maximum: int) -> dict:
    if path.is_symlink() or not path.is_file() or not 2 <= path.stat().st_size <= maximum:
        raise ValidationError('Missing or oversized candidate JSON: '+path.name)
    try:
        raw = path.read_bytes()
        if len(raw) > maximum:
            raise ValidationError('Candidate JSON grew beyond its limit')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                           parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed candidate JSON: '+path.name) from error
    if type(value) is not dict:
        raise ValidationError('Candidate JSON must be an object: '+path.name)
    return value


def regular_file(path: Path, root: Path, maximum: int) -> Path:
    if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
        raise ProjectStorageError('Candidate authorized directory was redirected')
    if path.is_symlink() or not path.is_file() or not path.is_relative_to(root):
        raise ProjectStorageError('Candidate input is missing, redirected or outside its selected directory')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink() or parent.resolve(strict=True) != parent:
            raise ProjectStorageError('Candidate input parent was redirected')
    if path.resolve(strict=True) != path or not 1 <= path.stat().st_size <= maximum:
        raise ProjectStorageError('Candidate input escaped its directory or exceeds its bounded size')
    return path


def validate_candidate_files(folder: Path, request: GodotCandidateRequest, cancel: Event | None) -> dict[str, str]:
    for name, expected in request.files:
        path = regular_file(folder/name, folder, LIMITS[name])
        if _digest(path, cancel) != expected:
            raise ProjectStorageError('Staged Godot candidate input changed: '+name)
    report = read_json(folder/'blender_stage.json', LIMITS['blender_stage.json'])
    validate_bind_profile(report)
    names = {target.key_name for target in TARGETS}
    if (type(report.get('schema_version')) is not int or report['schema_version'] != 1
            or report.get('profile') != 'MPFB_GODOT_BIND_MESH_V1'
            or report.get('master_sha256') != request.master_sha256
            or report.get('glb_sha256') != dict(request.files)['character.glb']
            or report.get('positions_sha256') != dict(request.files)['source_positions.bin']
            or type(report.get('visible_vertices')) is not int or report['visible_vertices'] != 13380
            or type(report.get('fps')) is not int or report['fps'] != 24
            or type(report.get('frames')) is not int or report['frames'] != 25
            or report.get('engine_import_verified') is not False
            or report.get('visual_quality_approved') is not False
            or type(report.get('expression_peaks')) is not dict or set(report['expression_peaks']) != names
            or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= .5
                   for value in report['expression_peaks'].values())):
        raise ValidationError('Godot candidate report differs from its source/profile/complete facial controls')
    rebuilt = build_skin_plan(folder/'character.glb')
    if canonical_bytes(read_json(folder/'skin_plan.json', LIMITS['skin_plan.json'])) != canonical_bytes(rebuilt.to_dict()):
        raise ValidationError('Godot candidate skin plan differs from independent GLB inspection')
    positions = (folder/'source_positions.bin').read_bytes()
    if len(positions) != LIMITS['source_positions.bin']:
        raise ValidationError('Candidate original full-surface reference is incomplete')
    values = array('f'); values.frombytes(positions)
    if sys.byteorder != 'little':
        values.byteswap()
    if any(not math.isfinite(value) for value in values):
        raise ValidationError('Candidate reference contains nonfinite positions')
    indices = read_json(folder/'bind_source_indices.json', LIMITS['bind_source_indices.json'])
    if (len(indices) != 13380 or any(re.fullmatch(r'[0-9a-f]{24}', key) is None for key in indices)
            or any(type(value) is not int for value in indices.values())
            or set(indices.values()) != set(range(13380))):
        raise ValidationError('Candidate source correspondence is incomplete or ambiguous')
    bind = (folder/'bind_positions.bin').read_bytes()
    if len(bind) != LIMITS['bind_positions.bin']:
        raise ValidationError('Candidate bind positions are incomplete')
    actual_indices = {}
    for index in range(13380):
        point = struct.unpack_from('<3f', bind, index*12)
        if not all(math.isfinite(value) for value in point):
            raise ValidationError('Candidate bind reference contains nonfinite positions')
        key = struct.pack('<3f', *(0. if value == 0 else value for value in point)).hex()
        if key in actual_indices:
            raise ValidationError('Candidate bind correspondence needs a separately admitted ambiguous-position profile')
        actual_indices[key] = index
    if indices != actual_indices:
        raise ValidationError('Candidate source mapping differs from actual bound Blender positions')
    verification = read_json(folder/'blender_verification.json', LIMITS['blender_verification.json'])
    motion_hashes = [sha for name, sha in request.source_bindings if name.startswith('motion:')]
    supplemental = {}
    if 'producer_policy' in report or 'producer_policy' in verification:
        from .godot_producer_evidence import validate_producer_chain, EXTRA_LIMITS, evidence_folder
        validate_producer_chain(folder, request, report, verification, cancel)
        supplemental = {name: _digest(evidence_folder(folder)/name, cancel) for name in EXTRA_LIMITS}
        review_sha = report.get('review_scene_sha256')
    else:
        review_sha = motion_hashes[0] if len(motion_hashes) == 1 else None
    frames = verification.get('frames')
    if (verification.get('status') != 'FRESH_SAVED_COMBINED_ACTION_AND_FULL_SURFACE_VERIFIED'
            or verification.get('independent_source_bytes_exact') is not True
            or verification.get('engine_import_verified') is not False
            or verification.get('source_vertices') != 13380 or len(motion_hashes) != 1
            or type(verification.get('bound_files')) is not dict
            or verification['bound_files'].get('source_review.blend') != review_sha
            or any(verification['bound_files'].get(name) != dict(request.files)[name]
                   for name in ('character.glb', 'source_positions.bin', 'bind_positions.bin'))
            or type(frames) is not list or len(frames) != 25
            or any(type(row) is not dict or row.get('frame') != index+1
                   or type(row.get('converted_max_error_m')) not in (int, float)
                   or not math.isfinite(row['converted_max_error_m']) or not 0 <= row['converted_max_error_m'] <= 1e-6
                   for index, row in enumerate(frames))):
        raise ValidationError('Godot candidate lacks complete fresh saved-source/action verification')
    check_cancel(cancel)
    return supplemental


def validate_bind_profile(report: dict) -> None:
    """Never silently discard Blender-only deformation or reinterpret masks."""
    modifiers = report.get('source_modifiers')
    armature_fields = {'name', 'type', 'rig_object', 'use_vertex_groups', 'use_bone_envelopes',
                       'use_deform_preserve_volume', 'use_multi_modifier', 'show_viewport', 'show_render'}
    mask_fields = {'name', 'type', 'mode', 'vertex_group', 'invert_vertex_group', 'threshold',
                   'use_smooth', 'show_viewport', 'show_render', 'source_mesh_vertices', 'vertex_group_sha256'}
    if type(modifiers) is not list or not 1 <= len(modifiers) <= 5 or type(modifiers[0]) is not dict:
        raise ValidationError('Godot candidate has no supported source modifier stack')
    armature = modifiers[0]
    expected = {'use_vertex_groups': True, 'use_bone_envelopes': False,
                'use_deform_preserve_volume': False, 'use_multi_modifier': False,
                'show_viewport': True, 'show_render': True}
    if (set(armature) != armature_fields or armature.get('type') != 'ARMATURE'
            or any(armature.get(key) is not value for key, value in expected.items())):
        raise ValidationError('Blender-only or non-linear skin deformation requires separately verified exact baking')
    for key in ('name', 'rig_object'):
        if type(armature[key]) is not str or not 1 <= len(armature[key]) <= 128 or any(ord(c) < 32 for c in armature[key]):
            raise ValidationError('Invalid original source armature identity')
    for mask in modifiers[1:]:
        if (type(mask) is not dict or set(mask) != mask_fields or mask.get('type') != 'MASK'
                or mask.get('mode') != 'VERTEX_GROUP' or mask.get('use_smooth') is not False
                or mask.get('show_viewport') is not True or mask.get('show_render') is not True
                or type(mask.get('invert_vertex_group')) is not bool
                or type(mask.get('threshold')) not in (int, float) or not math.isfinite(mask['threshold'])
                or not 0 <= mask['threshold'] <= 1 or type(mask.get('source_mesh_vertices')) is not int
                or mask['source_mesh_vertices'] != 19158
                or type(mask.get('vertex_group_sha256')) is not str
                or re.fullmatch(r'[0-9a-f]{64}', mask['vertex_group_sha256']) is None
                or any(type(mask.get(key)) is not str or not mask[key] or len(mask[key]) > 128
                       or any(ord(c) < 32 for c in mask[key]) for key in ('name', 'vertex_group'))):
            raise ValidationError('Godot candidate cannot reinterpret unsupported or nonstatic source modifiers')
    if report.get('static_masks_baked') is not True or report.get('body_and_hand_targets_baked') is not True:
        raise ValidationError('Godot candidate must preserve complete active body, hand and static-mask states')


def project_sources(store: ProjectStore, project, cancel: Event | None) -> dict[str, Path]:
    if project.animations:
        raise ValidationError('Source-only project animation references require separate target/export admission')
    master, _ = _master_file(store, project.master_blend)
    library, _ = registered_expression_source(store, project, cancel)
    files = {'master': master, 'expression_library': library.manifest_path}
    for part in project.parts:
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        if match is None:
            raise ValidationError('Godot candidate has an unsupported or unregistered attached part')
        hand = load_hand_library(store, match[1], cancel)
        files['part:'+part.part_asset_id] = hand.manifest_path
    return files


def identity(path: Path) -> tuple[int, int, int, int]:
    try:
        stat = path.stat()
    except OSError as error:
        raise ProjectStorageError('Godot source or directory is missing') from error
    if stat_types.S_ISDIR(stat.st_mode):
        return stat.st_dev, stat.st_ino, 0, 0
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


@dataclass(frozen=True, slots=True)
class CandidateInputs:
    store: ProjectStore
    request: GodotCandidateRequest
    candidate_folder: Path
    source_files: dict[str, Path]
    roots: tuple[Path, ...]
    identities: dict[Path, tuple[int, int, int, int]]
    supplemental_files: dict[str, str] = field(default_factory=dict)

    def unchanged(self, cancel: Event | None) -> None:
        check_cancel(cancel)
        project = self.store.load()
        if (project.project_id != self.request.project_id or project.revision != self.request.revision
                or _digest(self.store.file, cancel) != self.request.project_file_sha256):
            raise ProjectConflict('Saved character changed during Godot candidate verification')
        for path, previous in self.identities.items():
            if path.is_symlink() or not path.exists() or identity(path) != previous:
                raise ProjectStorageError('Godot source or directory identity changed during verification')
        expected_sources = project_sources(self.store, project, cancel)
        if any(self.source_files.get(name) != path for name, path in expected_sources.items()):
            raise ProjectStorageError('Registered Godot character source changed')
        for name, path in self.source_files.items():
            root = next((root for root in self.roots if path.is_relative_to(root)), None)
            if root is None:
                raise ProjectStorageError('Godot source escaped its authorized directories')
            regular_file(path, root, 512*1024*1024)
            if _digest(path, cancel) != dict(self.request.source_bindings)[name]:
                raise ProjectStorageError('Godot source content changed: '+name)
        for permission in self.request.permissions:
            permission.require_godot()
        validate_candidate_files(self.candidate_folder, self.request, cancel)


def admit_inputs(store: ProjectStore, request: GodotCandidateRequest, candidate_folder: Path,
                 *, motion_sources: dict[str, Path] | None, cancel: Event | None) -> CandidateInputs:
    check_cancel(cancel)
    store._check_safety()
    if candidate_folder.is_symlink() or not candidate_folder.is_dir() or candidate_folder.resolve() != candidate_folder:
        raise ProjectStorageError('Select a canonical existing candidate staging directory')
    project = store.load()
    if project.master_blend != 'master/versions/'+request.master_sha256+'.blend':
        raise ProjectConflict('Godot request names another saved character master')
    sources = dict(project_sources(store, project, cancel))
    if type(motion_sources) is not dict or len(motion_sources) != 1:
        raise ValidationError('This combined candidate needs one explicit verified target-motion scene')
    for name, path in (motion_sources or {}).items():
        if not name.startswith('motion:') or name in sources or not isinstance(path, Path):
            raise ValidationError('Additional Godot input must be an explicitly selected motion source')
        sources[name] = path
    if set(sources) != set(dict(request.source_bindings)):
        raise ValidationError('Godot permissions do not cover the exact registered and selected sources')
    roots = (store.root, candidate_folder)
    paths = {store.file, *roots, *sources.values(), *(candidate_folder/name for name in LIMITS)}
    # Watch each directory in the authorized path, not unrelated disk contents.
    for path in tuple(paths):
        root = next((root for root in roots if path.is_relative_to(root)), None)
        if root is None:
            raise ProjectStorageError('Selected motion source is outside the explicit project/candidate directories')
        for parent in path.parents:
            if parent == root:
                break
            if not parent.is_relative_to(root):
                break
            paths.add(parent)
    for permission in request.permissions:
        # The registered generated libraries retain their NoAI/source policy.
        # An engine-use review cannot silently remove that restriction.
        if permission.asset_id != 'master' and not permission.asset_id.startswith('motion:'):
            manifest = read_json(sources[permission.asset_id], 4*1024*1024)
            if manifest.get('rights', {}).get('no_ai') and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                raise ValidationError('Engine-use review must retain the registered library NoAI restriction')
    admitted = CandidateInputs(store, request, candidate_folder, sources, roots,
                               {path: identity(path) for path in paths})
    admitted.unchanged(cancel)
    supplemental = validate_candidate_files(candidate_folder, request, cancel)
    if type(supplemental) is dict:
        admitted.supplemental_files.update(supplemental)
    return admitted
