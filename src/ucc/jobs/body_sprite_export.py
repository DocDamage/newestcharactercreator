"""Registered Action → fresh source/FK/render/reopen → private sprite sample."""
from dataclasses import dataclass
from pathlib import Path
import shutil

from ucc.core.body_sprites import BodySpriteRequest, POLICY, STAGE, VERIFY, validate_recipe, worker_bindings
from ucc.core.errors import ValidationError, ProjectStorageError
from ucc.core.target_action_format import canonical_bytes, CLOCK
from ucc.sprites.body_evidence import (frame_names, atlas_side, checked_body_evidence,
                                      annotate_body_atlas, checked_body_atlas)
from ucc.sprites.plan import CameraProfile, build_plan
from ucc.sprites.atlas import pack_frames
from .body_sprite_sources import prepare_body_sprite_context
from .body_sprite_provenance import OriginalMotionProvenance
from .body_sprite_transactions import write_journal, file_inventory, BodySpritePublication
from .target_action_context import operation_budget, protected
from .expression_storage import safe_directory
from .export_destination import ExportDestination, plan_destination
from .godot_candidate_inputs import regular_file
from .master_preview import _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True, slots=True)
class BodySpriteExport:
    destination: Path
    receipt_sha256: str
    image_count: int
    selected_target_frames: tuple[int, ...]
    selected_source_frames: tuple[int, ...]
    source_intake_job_ids: tuple[str, str]
    stage_job_id: str
    reopen_job_id: str
    workdir: Path


def export_body_sprite_sample(store, *, request: BodySpriteRequest, database_path: Path,
                              destination: ExportDestination, blender_exe: Path, worker_script: Path,
                              original_author_record: Path, original_author_record_sha256: str,
                              original_motion_role: str, original_motion_uri_aliases: tuple=(),
                              cancel=None, timeout_s: float=3600) -> BodySpriteExport:
    if type(request) is not BodySpriteRequest or type(destination) is not ExportDestination:
        raise ValidationError('Body-sprite export needs its explicit reviewed request and exclusive destination')
    if plan_destination(destination.path, store.root) != destination or destination.path.is_relative_to(store.root/'animations'):
        raise ValidationError('Body-sprite destination cannot alter the registered Action source namespace')
    with operation_budget(cancel, timeout_s) as budget:
        provenance = OriginalMotionProvenance(Path(original_author_record),original_author_record_sha256,
                                             original_motion_role,original_motion_uri_aliases)
        return _export(store, request, Path(database_path), destination,
                       Path(blender_exe), Path(worker_script), budget, provenance)


def _export(store, request, database, destination, blender, worker, budget, provenance):
    context = prepare_body_sprite_context(store, request, database, blender, worker, budget, provenance)
    context.guard(); destination.unchanged()
    work = safe_directory(store, '.ucc-jobs', create=True)/('body-sprites-'+request.job_id)
    work.mkdir(exist_ok=False); publication = None; stage = None
    journal = lambda state, **values: write_journal(work, request.sha256, state, **values)
    try:
        recipe = work/'body_sprite_recipe.json'
        value = validate_recipe({'schema_version':1,'policy':POLICY,'request':request.to_dict(),
                                 'source_admission':context.source_admission})
        recipe.write_bytes(canonical_bytes(value)); recipe_sha = _digest(recipe, budget.cancel)
        options = worker_bindings(request, recipe_sha)
        retained = context.loaded.directory
        initial = {'candidate.blend':dict(context.sources)['master'], 'body_sprite_recipe.json':recipe,
                   'review_motion.blend':retained/'body_first/review_motion.blend',
                   'source_snapshot.json':context.snapshot,'native_mapping.json':retained/'native_mapping.json',
                   'target_timeline.json':retained/'body_first/target_timeline.json'}
        expected = {'candidate.blend':options['master_sha256'],'body_sprite_recipe.json':options['recipe_sha256'],
                    'review_motion.blend':options['review_sha256'],'source_snapshot.json':options['snapshot_sha256'],
                    'native_mapping.json':options['mapping_sha256'],'target_timeline.json':options['timeline_sha256']}
        def staged_guard(inputs):
            budget.check(); context.guard()
            for name, digest in expected.items():
                if _digest(protected(inputs[name]), budget.cancel) != digest:
                    raise ProjectStorageError('Body-sprite staged source or recipe changed: '+name)
        staged_guard(initial); journal('FRESH_SOURCE_ADMITTED_RENDERING')
        runner = BlenderJobRunner(blender, safe_directory(store, '.ucc-jobs'), worker)
        result, rendered = runner.run(JobRequest.new(STAGE, input_project='candidate.blend', options=options),
            staged_inputs=initial, timeout_s=budget.remaining(), cancel=budget.cancel)
        context.guard()
        expected_result = {'policy':POLICY, 'scene_sha256':result.details.get('scene_sha256'),
                           'stage_sha256':result.details.get('stage_sha256')}
        if result.details != expected_result:
            raise ValidationError('Body-sprite render worker returned an incomplete closed result')
        options = {**options, **{key:result.details[key] for key in ('scene_sha256','stage_sha256')}}
        names = frame_names(request)
        inputs = {name:regular_file(rendered/name, rendered, 128*1024*1024)
                  for name in (*initial, 'body_sprite_scene.blend','body_sprite_stage.json', *names)}
        staged_guard(inputs)
        hashes = {name:_digest(path, budget.cancel) for name, path in inputs.items()}
        if hashes['body_sprite_scene.blend'] != options['scene_sha256'] or hashes['body_sprite_stage.json'] != options['stage_sha256']:
            raise ProjectStorageError('Body-sprite rendered scene or report changed before independent reopening')
        journal('RECONSTRUCTING_SOURCE_AND_RERENDERING_SAVED_SCENE')
        verified, reopened = runner.run(JobRequest.new(VERIFY, input_project='candidate.blend', options=options),
            staged_inputs=inputs, timeout_s=budget.remaining(), cancel=budget.cancel)
        context.guard(); staged_guard({name:reopened/name for name in initial})
        for name, digest in hashes.items():
            if _digest(inputs[name], budget.cancel) != digest or _digest(protected(reopened/name), budget.cancel) != digest:
                raise ProjectStorageError('Body-sprite verification changed its immutable input evidence')
        proof_sha = _digest(regular_file(reopened/'body_sprite_verification.json', reopened, 4*1024*1024), budget.cancel)
        report, proof = checked_body_evidence(reopened, request, options, context.loaded.cache, proof_sha256=proof_sha)
        if canonical_bytes(verified.details) != canonical_bytes(proof):
            raise ValidationError('Body-sprite verifier reply differs from the admitted saved proof')
        frame_root = work/'atlas-inputs'; atlas = work/'atlas'
        for direction in range(request.settings.directions):
            directory = frame_root/f'body_sample/dir-{direction:02d}'; directory.mkdir(parents=True, exist_ok=False)
            for index, target in enumerate(request.window.target_frames):
                shutil.copy2(reopened/f'body-{direction:02d}-{target:04d}.png', directory/f'frame-{index:04d}.png')
        camera_scale = next(row['camera']['ortho_scale'] for row in report['configuration']['objects'].values() if 'camera' in row)
        camera = CameraProfile(yaw_deg=request.settings.yaw_deg, pitch_deg=request.settings.pitch_deg,
                               orthographic_scale=camera_scale, directions=request.settings.directions)
        plan = build_plan({'body_sample':request.window.sample_count}, camera,
                          width=request.settings.resolution, height=request.settings.resolution, fps=30)
        packed = pack_frames(plan, frame_root, atlas, max_sheet_side=atlas_side(request),
                             pivot_x=report['pivot'][0], pivot_y=report['pivot'][1])
        annotate_body_atlas(atlas, request)
        atlas_hashes = {name:_digest(regular_file(atlas/name,atlas,32*1024*1024),budget.cancel)
                        for name in ('sprite_atlas.json', *packed.sheet_files)}
        atlas_report = checked_body_atlas(atlas, reopened, request, report)
        if any(_digest(atlas/name,budget.cancel) != digest for name,digest in atlas_hashes.items()):
            raise ProjectStorageError('Body-sprite atlas changed during independent pixel validation')
        context.guard(); stage = destination.stage(request.job_id)
        output_names = {*names, 'body_sprite_stage.json','body_sprite_verification.json','body_sprite_recipe.json',
                        'sprite_atlas.json', *(row['file'] for row in atlas_report['sheets'])}
        validated_hashes = {row['file']:row['sha256'] for row in report['frames']}
        validated_hashes.update({'body_sprite_stage.json':options['stage_sha256'],
            'body_sprite_verification.json':proof_sha, 'body_sprite_recipe.json':options['recipe_sha256'],
            **atlas_hashes})
        for name in output_names:
            source = atlas/name if name == 'sprite_atlas.json' or name.startswith('sprite_sheet_') else reopened/name
            if _digest(protected(source), budget.cancel) != validated_hashes[name]:
                raise ProjectStorageError('Verified body-sprite output changed before destination copy')
            shutil.copy2(source, stage/name)
            if _digest(stage/name, budget.cancel) != validated_hashes[name]:
                raise ProjectStorageError('Body-sprite destination copy differs from verified bytes')
        (stage/'README.txt').write_text(
            'Private registered body-motion sprite SAMPLE\n\n'
            f'Selected target frames {request.window.target_first_frame}-{request.window.target_last_frame}; '
            f'source frames {request.window.source_frames[0]}-{request.window.source_frames[-1]} at 30 fps.\n'
            'The complete source clip clock remains separate in the recipe and atlas metadata.\n'
            'Sample span excludes the final sample dwell; nominal coverage includes it.\n'
            'Temporary matte exists only on private render copies and was not adopted into the saved character.\n'
            'No editable source, animation clip, public distribution, quality or engine approval is included.\n', encoding='utf-8')
        output_names.add('README.txt'); files = file_inventory(stage, output_names, budget.cancel)
        receipt = {'schema_version':1,'policy':POLICY,'request_sha256':request.sha256,'bindings':options,
            'files':files,'full_clock':dict(CLOCK),'selected_window':request.window.to_dict(),
            'source_admission':context.source_admission,'source_intake_job_ids':context.source_admission['worker_job_ids'],
            'blender_stage_job_id':result.job_id,'blender_reopen_job_id':verified.job_id,
            'blender_executable_sha256':context.executable_sha256,
            'worker_dependencies':{str(path):_digest(path,budget.cancel) for path in context.worker_files},
            'original_source_verified':True,'saved_scene_rerender_verified':True,'image_count':request.image_count,
            'material_adopted':False,'project_metadata_changed':False,'source_redistribution_authorized':False,
            'sprite_redistribution_authorized':False,'ai_input_authorized':False,'cloud_transmission_authorized':False,
            'visual_quality_approved':False,'usable_action_approved':False,'engine_import_verified':False}
        receipt_path = stage/'body_sprite_receipt.json'; receipt_path.write_bytes(canonical_bytes(receipt))
        receipt_sha = _digest(receipt_path, budget.cancel); output_names.add(receipt_path.name)
        publication = BodySpritePublication(store, destination, stage, output_names, budget)
        journal('DESTINATION_STAGED'); publication.commit(context.guard, budget)
        context.guard(); journal('PRIVATE_BODY_SPRITE_SAMPLE_PUBLISHED', receipt_sha256=receipt_sha); budget.check()
        return BodySpriteExport(destination.path, receipt_sha, request.image_count, request.window.target_frames,
            request.window.source_frames, tuple(context.source_admission['worker_job_ids']), result.job_id, verified.job_id, work)
    except BaseException as error:
        if publication is not None: publication.withdraw(error)
        try: journal('FAILED', error_type=type(error).__name__, error=str(error)[:1500],
                     retained_stage=None if stage is None else str(stage))
        except (OSError, ProjectStorageError) as journal_error: error.add_note('Body-sprite journal failure: '+str(journal_error))
        raise
