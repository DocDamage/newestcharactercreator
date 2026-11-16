"""Prepare a real editable material revision without admitting an incoherent graph.

The selected hand's existing material recipe remains authoritative until the
following graph transaction rebuilds it. Success here retains a verified private
candidate; it never changes the project/master pointer or appearance metadata.
"""
from dataclasses import dataclass
import math,os,shutil,time,tempfile
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ValidationError,ProjectConflict,ProjectStorageError
from ucc.core.skin_material import SkinMaterialSpec,material_recipe,RECIPE_POLICY,canonical_bytes
from ucc.core.storage import ProjectStore,_lock
from ucc.export.skin_material_evidence import verify_material_glb
from .expression_storage import safe_directory
from .expression_verification import verify_saved_expression_master
from .godot_candidate_inputs import project_sources,regular_file,read_json,identity
from .master_preview import _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner,WorkerFailure
from .worker_resources import worker_dependency_files

OUTPUTS={'material_human.blend':512*1024*1024,'character.glb':512*1024*1024,
    'material_stage.json':4*1024*1024,'material_verification.json':4*1024*1024}


@dataclass(frozen=True,slots=True)
class PreparedSkinMaterialRevision:
    directory: Path
    source_master_sha256: str
    material_master_sha256: str
    spec_sha256: str
    verification_sha256: str
    stage_job_id: str
    reopen_job_id: str

    @property
    def project_pointer_changed(self) -> bool:return False


class _BudgetCancel(Event):
    def __init__(self,user: Event | None,deadline: float):
        super().__init__();self.user=user;self.deadline=deadline

    def is_set(self) -> bool:
        return super().is_set() or (self.user is not None and self.user.is_set()) or time.monotonic()>=self.deadline


def checked_material_reports(stage: dict,verified: dict,*,source_sha: str,recipe_sha: str,spec: SkinMaterialSpec,
                             master_sha: str,glb_sha: str,stage_sha: str) -> None:
    from ucc.core.expressions import is_sha256
    stage_fields={'schema_version','policy','recipe_sha256','source_master_sha256','material_master_sha256','glb_sha256','spec_sha256',
        'nonmaterial_state_sha256','shader_sha256','shape_key_count','full_vertices','visible_vertices','bones','changed','blender_version','export',
        'project_pointer_changed','engine_import_verified','visual_quality_approved','distribution_license_review_complete'}
    verify_fields={'schema_version','policy','stage_report_sha256','recipe_sha256','source_master_sha256','material_master_sha256','glb_sha256',
        'spec_sha256','nonmaterial_state_sha256','shader_sha256','export','verified_reopen','saved_output_rebuilt_or_repaired',
        'project_pointer_changed','engine_import_verified','visual_quality_approved','distribution_license_review_complete'}
    for report,fields in ((stage,stage_fields),(verified,verify_fields)):
        if (type(report) is not dict or set(report)!=fields or type(report['schema_version']) is not int or report['schema_version']!=1
                or report['policy']!=RECIPE_POLICY or report['recipe_sha256']!=recipe_sha or report['source_master_sha256']!=source_sha
                or report['material_master_sha256']!=master_sha or report['glb_sha256']!=glb_sha or report['spec_sha256']!=spec.sha256
                or any(report[name] is not False for name in ('project_pointer_changed','engine_import_verified','visual_quality_approved','distribution_license_review_complete'))
                or any(not is_sha256(report[name]) for name in ('nonmaterial_state_sha256','shader_sha256'))):
            raise ValidationError('Material worker evidence changed its source, definition or unapproved flags')
    if (stage['nonmaterial_state_sha256']!=verified['nonmaterial_state_sha256'] or stage['shader_sha256']!=verified['shader_sha256']
            or canonical_bytes(stage['export'])!=canonical_bytes(verified['export']) or verified['stage_report_sha256']!=stage_sha
            or verified['verified_reopen'] is not True or verified['saved_output_rebuilt_or_repaired'] is not False
            or type(stage['changed']) is not bool or stage['changed']!=(source_sha!=master_sha)
            or (stage['full_vertices'],stage['visible_vertices'],stage['bones'])!=(19158,13380,163)
            or type(stage['shape_key_count']) is not int or not 13<=stage['shape_key_count']<=256
            or type(stage['blender_version']) is not str or not stage['blender_version'].startswith('5.3.')):
        raise ValidationError('Fresh material verification lacks exact source/nonmaterial/shader preservation')
    exported=stage['export']
    if type(exported) is not dict or set(exported)!={'pbr','uv','maximum_relative_weight_error','maximum_morph_delta_error_m'}:
        raise ValidationError('Material export evidence is incomplete')
    for field in ('maximum_relative_weight_error','maximum_morph_delta_error_m'):
        value=exported[field]
        if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1e-6:
            raise ValidationError('Material export changed original skin or facial controls')
    uv=exported['uv']
    if (type(uv) is not dict or uv.get('policy')!='UCC_NATIVE_SOURCE_CORNER_UV_V1'
            or (uv.get('source_corners'),uv.get('source_polygons'),uv.get('imported_vertices'))!=(53512,13378,14517)
            or type(uv.get('maximum_uv_component_error')) not in (int,float) or not 0<=uv['maximum_uv_component_error']<=1e-6
            or uv.get('material_appearance_verified') is not False or uv.get('engine_import_verified') is not False):
        raise ValidationError('Material export lost original UV coverage')


def prepare_skin_material_revision(store: ProjectStore,*,spec: SkinMaterialSpec,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None=None,timeout_s: float=600) -> PreparedSkinMaterialRevision:
    if not isinstance(spec,SkinMaterialSpec) or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Material preparation requires explicit parameters and a bounded total deadline')
    deadline=time.monotonic()+timeout_s
    try:
        return _prepare_skin_material_revision(store,spec=spec,blender_exe=blender_exe,worker_script=worker_script,
            mpfb_data_dir=mpfb_data_dir,expected_project_id=expected_project_id,expected_revision=expected_revision,
            expected_master_blend=expected_master_blend,cancel=cancel,deadline=deadline)
    except (ProjectStorageError,WorkerFailure) as error:
        if time.monotonic()>=deadline:raise WorkerFailure('Material preparation exceeded its total deadline') from error
        raise


def _prepare_skin_material_revision(store: ProjectStore,*,spec: SkinMaterialSpec,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None,deadline: float) -> PreparedSkinMaterialRevision:
    budget=_BudgetCancel(cancel,deadline)
    def check() -> float:
        if time.monotonic()>=deadline:raise WorkerFailure('Material preparation exceeded its total deadline')
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Material preparation cancelled; saved master unchanged')
        return max(.05,deadline-time.monotonic())
    check();store._check_safety();initial=store.load()
    if (type(expected_revision) is not int or initial.project_id!=expected_project_id or initial.revision!=expected_revision
            or initial.master_blend!=expected_master_blend):raise ProjectConflict('Saved character changed before material preparation')
    metadata_sha=_digest(store.file,budget);sources=project_sources(store,initial,budget)
    executable=regular_file(Path(blender_exe),Path(blender_exe).parent,512*1024*1024)
    worker=regular_file(Path(worker_script),Path(worker_script).parent,256*1024)
    bindings={name:_digest(path,budget) for name,path in sources.items()};recipe=material_recipe(initial,metadata_sha,bindings,spec)
    watched={store.file,executable,*sources.values(),*worker_dependency_files(worker),*Path(__file__).resolve().parents[1].rglob('*.py')}
    hashes={p:_digest(p,budget) for p in watched};identities={p:identity(p) for p in watched}
    def unchanged() -> None:
        check()
        if store.load()!=initial or _digest(store.file,budget)!=metadata_sha:raise ProjectConflict('Saved character changed during material preparation')
        if project_sources(store,initial,budget)!=sources:raise ProjectStorageError('Registered material source closure changed')
        for path,sha in hashes.items():
            check()
            if path.is_symlink() or not path.is_file() or path.resolve()!=path or identity(path)!=identities[path] or _digest(path,budget)!=sha:
                raise ProjectStorageError('Material source, executable or adapter changed')
    unchanged();jobs=safe_directory(store,'.ucc-jobs',create=True);work=jobs/('skin-material-'+str(uuid4()));work.mkdir()
    recipe_path=work/'material_recipe.json';recipe_path.write_bytes(canonical_bytes(recipe));recipe_sha=_digest(recipe_path,budget)
    runner=BlenderJobRunner(executable,jobs,worker);destination=None;staging=work/'retained';job_ids=[]
    def journal(state: str,**details) -> None:
        path=work/'job_status.json'
        if path.is_symlink():raise ProjectStorageError('Material job journal redirected')
        fd,name=tempfile.mkstemp(prefix='status-',suffix='.tmp',dir=work);temporary=Path(name)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(canonical_bytes({'schema_version':1,'state':state,'recipe_sha256':recipe_sha,'job_ids':job_ids,
                    'project_pointer_changed':False,**details}));stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    try:
        journal('SOURCE_ADMISSION')
        verify_saved_expression_master(store,blender_exe=executable,worker_script=worker,mpfb_data_dir=mpfb_data_dir,
            expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend,
            cancel=budget,timeout_s=check());unchanged()
        options={'master_sha256':bindings['master'],'recipe_sha256':recipe_sha}
        stage_job=JobRequest.new('stage_mpfb_skin_material',input_project='candidate.blend',options=options);job_ids.append(stage_job.job_id)
        stage_result,folder=runner.run(stage_job,staged_inputs={'candidate.blend':sources['master'],'material_recipe.json':recipe_path},timeout_s=check(),cancel=budget);unchanged()
        master=regular_file(folder/'material_human.blend',folder,OUTPUTS['material_human.blend']);glb=regular_file(folder/'character.glb',folder,OUTPUTS['character.glb'])
        stage_path=regular_file(folder/'material_stage.json',folder,OUTPUTS['material_stage.json'])
        master_sha,glb_sha,stage_sha=_digest(master,budget),_digest(glb,budget),_digest(stage_path,budget)
        if stage_result.details!={'policy':RECIPE_POLICY,'stage_report_sha256':stage_sha,'material_master_sha256':master_sha,'glb_sha256':glb_sha,'engine_import_verified':False}:
            raise ValidationError('Material stage result differs from its saved outputs')
        verify_job=JobRequest.new('verify_mpfb_skin_material',input_project='candidate.blend',options={**options,
            'material_master_sha256':master_sha,'glb_sha256':glb_sha,'stage_report_sha256':stage_sha});job_ids.append(verify_job.job_id)
        inputs={'candidate.blend':sources['master'],'material_recipe.json':recipe_path,'material_human.blend':master,'character.glb':glb,'material_stage.json':stage_path}
        verified,reopened=runner.run(verify_job,staged_inputs=inputs,timeout_s=check(),cancel=budget);unchanged()
        verification_path=regular_file(reopened/'material_verification.json',reopened,OUTPUTS['material_verification.json']);verification_sha=_digest(verification_path,budget)
        if verified.details!={'policy':RECIPE_POLICY,'verification_sha256':verification_sha,'material_master_sha256':master_sha,'glb_sha256':glb_sha,'engine_import_verified':False}:
            raise ValidationError('Material reopening result differs from complete saved verification')
        stage=read_json(stage_path,OUTPUTS['material_stage.json']);fresh=read_json(verification_path,OUTPUTS['material_verification.json'])
        checked_material_reports(stage,fresh,source_sha=bindings['master'],recipe_sha=recipe_sha,spec=spec,master_sha=master_sha,glb_sha=glb_sha,stage_sha=stage_sha)
        if canonical_bytes(verify_material_glb(glb,spec))!=canonical_bytes(stage['export']['pbr']):raise ValidationError('Material PBR evidence differs from independent GLB decoding')
        for name,path in inputs.items():
            if _digest(path,budget)!=_digest(reopened/name,budget):raise ProjectStorageError('Material verification changed staged source/output bytes')
        staging.mkdir();retained={'material_human.blend':master,'character.glb':glb,'material_stage.json':stage_path,
            'material_verification.json':verification_path,'material_recipe.json':recipe_path}
        expected={name:_digest(path,budget) for name,path in retained.items()}
        for name,path in retained.items():
            check();shutil.copy2(path,staging/name)
            if _digest(staging/name,budget)!=expected[name]:raise ProjectStorageError('Material candidate changed while retaining')
        (staging/'.gdignore').write_bytes(b'')
        (staging/'candidate.json').write_bytes(canonical_bytes({'schema_version':1,'policy':RECIPE_POLICY,'recipe_sha256':recipe_sha,
            'files':expected,'project_pointer_changed':False,'project_publication_authorized':False,'engine_import_verified':False,'visual_quality_approved':False}))
        root=safe_directory(store,'.ucc-candidates','skin-material',create=True);destination=root/str(uuid4())
        with _lock(store.root/'.project.ucc.lock',timeout_s=min(3.,check())):
            unchanged();check()
            if destination.exists() or destination.is_symlink():raise ProjectStorageError('Material candidate identity already exists')
            os.rename(staging,destination)
        check();journal('PRIVATE_MATERIAL_REVISION_PREPARED',candidate=str(destination),verification_sha256=verification_sha)
        return PreparedSkinMaterialRevision(destination,bindings['master'],master_sha,spec.sha256,verification_sha,stage_job.job_id,verify_job.job_id)
    except BaseException as error:
        if destination is not None and not staging.exists() and destination.is_dir() and not destination.is_symlink():
            try:os.rename(destination,staging)
            except OSError as rollback_error:error.add_note('Material retention rollback failed: '+str(rollback_error))
        try:journal('FAILED',error_type=type(error).__name__,error=str(error)[:1500])
        except (OSError,ProjectStorageError) as journal_error:error.add_note('Material failure journal could not be retained: '+str(journal_error))
        if time.monotonic()>=deadline:raise WorkerFailure('Material preparation exceeded its total deadline') from error
        raise
