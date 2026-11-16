"""Build/register real compatible hands through two independent Blender jobs."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.hand_parts import (
    POLICY, TARGETS, METADATA_SHA256, build_hand_library_recipe, build_hand_manifest,
    canonical_digest, is_sha256,
)
from ucc.core.storage import ProjectStore
from .geometry_evidence import EvidenceError
from .hand_storage import (
    HandLibrary, check_cancel, installed_inputs, safe_directory, publish_asset,
    publish_manifest, load_hand_library,
)
from .master_preview import _digest, _master_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class HandLibraryBuild:
    library: HandLibrary
    stage_job_id: str
    reopen_job_id: str
    observed: dict


def _validate_evidence(stage: dict, proof: dict, source_sha: str, recipe_sha: str) -> dict:
    stage_fields = {'schema_version', 'policy', 'recipe_sha256', 'source_master_sha256',
                    'blender_version', 'assets', 'visual_quality_approved', 'engine_import_verified'}
    proof_fields = {'schema_version', 'policy', 'verified_reopen', 'recipe_sha256', 'source_master_sha256',
                    'assets', 'skin_poses', 'all40_restores_exact', 'visual_quality_approved', 'engine_import_verified'}
    if type(stage) is not dict or set(stage) != stage_fields or type(proof) is not dict or set(proof) != proof_fields:
        raise EvidenceError('Hand library lacks complete two-worker evidence')
    for record in (stage, proof):
        if (type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['policy'] != POLICY or record['recipe_sha256'] != recipe_sha
                or record['source_master_sha256'] != source_sha
                or record['visual_quality_approved'] is not False or record['engine_import_verified'] is not False):
            raise EvidenceError('Hand evidence differs from the bound source/recipe/quality limits')
    if (type(stage['blender_version']) is not str or not stage['blender_version'].startswith('5.3.')
            or proof['verified_reopen'] is not True or proof['all40_restores_exact'] is not True
            or canonical_digest(stage['assets']) != canonical_digest(proof['assets'])):
        raise EvidenceError('Independent hand reconstruction did not reproduce both actual assets')
    rows = stage['assets']
    if type(rows) is not dict or set(rows) != {t.variant for t in TARGETS}:
        raise EvidenceError('Hand library requires both real variant assets')
    dimensions = {'vertices':1747, 'polygons':1735, 'border_vertices':22, 'joint_helper_vertices':112}
    assets = {}
    for variant, row in rows.items():
        if (type(row) is not dict or set(row) != {'scene_sha256', 'observation_sha256', 'metrics'}
                or not is_sha256(row['scene_sha256']) or not is_sha256(row['observation_sha256'])):
            raise EvidenceError('Hand asset lacks an immutable scene/observation identity')
        metrics = row['metrics']
        if (type(metrics) is not dict or set(metrics) != set(dimensions)|{
                'changed_skin_vertices_over_1um', 'maximum_world_displacement', 'actual_source_skin'}
                or any(type(metrics[k]) is not int or metrics[k] != v for k,v in dimensions.items())
                or metrics['actual_source_skin'] is not True
                or type(metrics['changed_skin_vertices_over_1um']) is not int
                or not 100 < metrics['changed_skin_vertices_over_1um'] <= 1747
                or type(metrics['maximum_world_displacement']) is not float
                or not 0 < metrics['maximum_world_displacement'] < .03):
            raise EvidenceError('Hand worker lacks bounded real-skin geometry evidence')
        assets[variant] = {'sha256': row['scene_sha256'], 'observation_sha256': row['observation_sha256']}
    poses = proof['skin_poses']
    expected = {(name, axis, angle) for name,axes in [('wrist.L',(0,1,2)),
                *[(f'finger{i}-1.L',(0,)) for i in range(1,6)],('finger2-2.L',(0,)),('finger5-2.L',(0,))]
                for axis in axes for angle in (-20,20)}
    if type(poses) is not dict or set(poses) != set(rows):
        raise EvidenceError('Hand library lacks independently reopened skin-pose checks')
    for records in poses.values():
        seen = set()
        if type(records) is not list or len(records) != 20:
            raise EvidenceError('Hand skin-pose coverage is incomplete')
        for row in records:
            if (type(row) is not dict or set(row) != {'bone','axis','degrees','moved_vertices_over_1um','maximum_displacement'}
                    or type(row['bone']) is not str or type(row['axis']) is not int or type(row['degrees']) is not int
                    or type(row['moved_vertices_over_1um']) is not int or not 16 <= row['moved_vertices_over_1um'] <= 1747
                    or type(row['maximum_displacement']) is not float or not 1e-6 < row['maximum_displacement'] < .5):
                raise EvidenceError('Invalid real hand skin-pose observation')
            seen.add((row['bone'],row['axis'],row['degrees']))
        if seen != expected:
            raise EvidenceError('Hand skin-pose checks duplicate or omit a required pose')
    return assets


def build_hand_library(
    store: ProjectStore, *, blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
    expected_project_id: str, expected_revision: int, expected_master_blend: str,
    cancel: Event | None = None, timeout_s: float = 300,
) -> HandLibraryBuild:
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before hand library preparation')
    if initial.master_blend is None:
        raise ValidationError('Generate an existing MPFB master before building hand assets')
    if type(timeout_s) not in (int,float) or not .05 <= timeout_s <= 3600 or not math.isfinite(timeout_s):
        raise ValidationError('Hand timeout_s is outside the supported range')
    check_cancel(cancel)
    executable, script = Path(blender_exe), Path(worker_script)
    if executable.is_symlink() or not executable.is_file() or script.is_symlink() or not script.is_file():
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    source, source_sha = _master_file(store, expected_master_blend)
    if _digest(source, cancel) != source_sha:
        raise ProjectStorageError('Hand source does not match its immutable master filename')
    recipe = build_hand_library_recipe(initial, source_sha)
    metadata_sha = _digest(store.file, cancel)
    installed = installed_inputs(mpfb_data_dir, cancel)
    jobs = safe_directory(store, '.ucc-jobs', create=True)
    inputs = jobs/('hand-inputs-'+str(uuid4())); inputs.mkdir(exist_ok=False)
    recipe_path = inputs/'hand_recipe.json'
    with recipe_path.open('x', encoding='utf-8') as stream:
        json.dump(recipe, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    recipe_sha = _digest(recipe_path, cancel)
    options = {'master_sha256':source_sha, 'recipe_sha256':recipe_sha, 'metadata_sha256':METADATA_SHA256,
               **{t.variant+'_target_sha256':t.sha256 for t in TARGETS}}
    staged = {'candidate.blend':source, 'hand_recipe.json':recipe_path,
              'basemesh_vertex_groups.json':installed['basemesh_vertex_groups.json'],
              **{t.filename:installed[t.filename] for t in TARGETS}}
    hashes = {'candidate.blend':source_sha, 'hand_recipe.json':recipe_sha,
              'basemesh_vertex_groups.json':METADATA_SHA256, **{t.filename:t.sha256 for t in TARGETS}}
    runner = BlenderJobRunner(executable, jobs, script)
    request = JobRequest.new('build_mpfb_hand_assets', input_project='candidate.blend', options=options)
    stage, stage_dir = runner.run(request, staged_inputs=staged, timeout_s=timeout_s, cancel=cancel)
    outputs = {**{'hand-'+t.variant+'.blend':stage_dir/('hand-'+t.variant+'.blend') for t in TARGETS},
               'hand_assets_report.json':stage_dir/'hand_assets_report.json'}
    for name,path in outputs.items():
        if path.is_symlink() or not path.is_file():
            raise EvidenceError('Hand asset worker produced no actual saved scene/report: '+name)
    output_hashes = {name:_digest(path,cancel) for name,path in outputs.items()}
    verify_options = dict(options, **{t.variant+'_asset_sha256':output_hashes['hand-'+t.variant+'.blend'] for t in TARGETS},
                          assets_report_sha256=output_hashes['hand_assets_report.json'])
    verification = JobRequest.new('verify_mpfb_hand_assets', input_project='candidate.blend', options=verify_options)
    verified, verify_dir = runner.run(verification, staged_inputs={**staged,**outputs}, timeout_s=timeout_s, cancel=cancel)
    assets = _validate_evidence(stage.details, verified.details, source_sha, recipe_sha)
    if any(assets[t.variant]['sha256'] != output_hashes['hand-'+t.variant+'.blend'] for t in TARGETS):
        raise EvidenceError('Hand evidence is not bound to the actual worker files')
    for name,path in {**staged,**outputs}.items():
        expected = {**hashes,**output_hashes}[name]
        for candidate in (path,stage_dir/name,verify_dir/name):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate,cancel) != expected:
                raise ProjectStorageError('Hand input/output changed before registration: '+name)
    installed_inputs(mpfb_data_dir,cancel)
    if store.load() != initial or _digest(store.file,cancel) != metadata_sha:
        raise ProjectConflict('Project changed during hand creation; original master remains authoritative')
    check_cancel(cancel)
    for target in TARGETS:
        publish_asset(store,outputs['hand-'+target.variant+'.blend'],assets[target.variant]['sha256'],stage_dir,cancel)
    if store.load() != initial or _digest(store.file,cancel) != metadata_sha:
        raise ProjectConflict('Project changed before hand registration')
    identity = publish_manifest(store,build_hand_manifest(recipe,assets),cancel)
    library = load_hand_library(store,identity,cancel)
    return HandLibraryBuild(library,request.job_id,verification.job_id,
                            {'verified_reopen':True,'actual_skin_poses':40,'original_project_and_master_preserved':True,
                             'visual_quality_approved':False,'engine_import_verified':False})
