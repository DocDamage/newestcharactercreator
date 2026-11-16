"""Atomic prepared-expression/material/compatible-hand publication."""
from dataclasses import dataclass,replace
import math,time
from pathlib import Path
from threading import Event
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.expressions import validate_expression_part_rebind
from ucc.core.master_versions import MasterRevision,stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from .expression_storage import install_master_copy
from .expression_keys import installed_expression_inputs
from .expression_inspection import _inspect_expression_copy
from .expression_revisions import publish_expression_receipt,read_expression_receipt
from .expression_verification import verify_saved_expression_master,registered_expression_source
from .reference_expression_context import prepare_reference_expression_context,publish_expression_edit
from .expression_hands import RebuiltExpressionHand,publish_rebuilt_hand
from .hand_library import build_hand_library
from .hand_revision import apply_hand_revision
from .hand_storage import load_hand_library,load_hand_receipt,installed_inputs
from .master_preview import _master_file,_digest
from .neutral_master import inspect_saved_neutral_master
from .skin_material_preparation import prepare_skin_material_revision,_BudgetCancel
from .skin_material_storage import POLICY,install_binding,registered_material_binding,copy_binding
from .godot_candidate_inputs import project_sources,identity,regular_file,read_json
from .worker_resources import worker_dependency_files
from .runner import WorkerFailure


@dataclass(frozen=True,slots=True)
class SkinMaterialRevision:
    revision: MasterRevision
    binding_sha256: str
    material_master_sha256: str
    hand_manifest_sha256: str | None
    observed: dict


@dataclass(frozen=True,slots=True)
class MaterialMasterNoOp:
    project: CharacterProject
    operation: str
    observed: dict
    private_transaction: Path


def revise_material_bound_master(store: ProjectStore,*,operation: str,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None=None,timeout_s: float=1200) -> SkinMaterialRevision | MaterialMasterNoOp:
    """Retain the admitted chosen shader through a body/face edit, without new UI.

    Pending desired dimensions are never substituted for old physical provenance.
    Only a private projection may reset the hand or omit its publication binding.
    """
    if type(operation) is not str or operation not in {'body_generation','body_refit','face_revision'}:
        raise ValidationError('Select body generation, body refit or face revision for material preservation')
    return _material_graph(store,spec=None,master_operation=operation,blender_exe=blender_exe,worker_script=worker_script,
        mpfb_data_dir=mpfb_data_dir,expected_project_id=expected_project_id,expected_revision=expected_revision,
        expected_master_blend=expected_master_blend,cancel=cancel,timeout_s=timeout_s)


def apply_skin_material_revision(store,*,spec: SkinMaterialSpec,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None=None,timeout_s: float=1200) -> SkinMaterialRevision | MaterialMasterNoOp:
    if not isinstance(spec,SkinMaterialSpec):raise ValidationError('Material graph publication requires explicit material parameters')
    return _material_graph(store,spec=spec,master_operation=None,blender_exe=blender_exe,worker_script=worker_script,
        mpfb_data_dir=mpfb_data_dir,expected_project_id=expected_project_id,expected_revision=expected_revision,
        expected_master_blend=expected_master_blend,cancel=cancel,timeout_s=timeout_s)


def _material_graph(store,*,spec: SkinMaterialSpec | None,master_operation: str | None,blender_exe: Path,worker_script: Path,
        mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None,timeout_s: float) -> SkinMaterialRevision | MaterialMasterNoOp:
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Material graph publication requires explicit parameters and a bounded deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if time.monotonic()>=deadline:raise WorkerFailure('Material graph publication exceeded its total deadline')
        if cancel is not None and cancel.is_set():raise ProjectStorageError('Material graph publication cancelled; old project remains authoritative')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load()
    if (type(expected_revision) is not int or initial.project_id!=expected_project_id or initial.revision!=expected_revision
            or initial.master_blend!=expected_master_blend):raise ProjectConflict('Saved character changed before material graph publication')
    if initial.expression is None or initial.master_blend is None or initial.animations:
        raise ValidationError('Material graph publication currently requires a prepared character without source-animation references')
    context=prepare_reference_expression_context(store,initial,budget) if master_operation else None
    physical=context.project if context else initial
    original_binding=registered_material_binding(store,physical,budget)
    if master_operation:
        if original_binding is None:raise ValidationError('Material-preserving editing requires an admitted published material')
        spec=SkinMaterialSpec.from_dict(original_binding['spec'])
    sources=project_sources(store,physical,budget)
    watched={store.file,*sources.values(),Path(blender_exe).resolve(),*worker_dependency_files(Path(worker_script)),
        *Path(__file__).resolve().parents[1].rglob('*.py')}
    protected={p:(_digest(p,budget),identity(p)) for p in watched}
    def unchanged():
        remaining()
        if store.load()!=initial or project_sources(store,physical,budget)!=sources:raise ProjectConflict('Material graph source changed before publication')
        for path,(sha,old_identity) in protected.items():
            if path.is_symlink() or not path.is_file() or identity(path)!=old_identity or _digest(path,budget)!=sha:
                raise ProjectStorageError('Material graph source, adapter or executable changed')
        if registered_material_binding(store,physical,budget)!=original_binding:raise ProjectStorageError('Original appearance binding changed')
    def runtime():return dict(blender_exe=blender_exe,worker_script=worker_script,mpfb_data_dir=mpfb_data_dir,cancel=budget,timeout_s=remaining())
    if context is None:
        if original_binding is not None and SkinMaterialSpec.from_dict(original_binding['spec'])==spec:
            prepared=prepare_skin_material_revision(store,spec=spec,**runtime(),expected_project_id=initial.project_id,
                expected_revision=initial.revision,expected_master_blend=initial.master_blend)
            source_sha=Path(initial.master_blend).stem
            stage_path=regular_file(prepared.directory/'material_stage.json',prepared.directory,4*1024*1024)
            proof=regular_file(prepared.directory/'material_verification.json',prepared.directory,4*1024*1024)
            model=regular_file(prepared.directory/'material_human.blend',prepared.directory,512*1024*1024)
            if (prepared.source_master_sha256!=source_sha or prepared.material_master_sha256!=source_sha
                    or read_json(stage_path,4*1024*1024).get('changed') is not False
                    or _digest(proof,budget)!=prepared.verification_sha256 or _digest(model,budget)!=source_sha):
                raise ProjectStorageError('Saved shader differs from the selected material; an unchanged Apply cannot repair or publish it')
            unchanged()
            return MaterialMasterNoOp(initial,'skin_material_revision',{'verified_noop':True,'material_parameters_preserved':True,
                'fresh_saved_source_verified':True,'fresh_owned_shader_verified':True,'verification_sha256':prepared.verification_sha256,
                'stage_job_id':prepared.stage_job_id,'reopen_job_id':prepared.reopen_job_id,
                'engine_import_verified':False,'visual_quality_approved':False},prepared.directory)
        verify_saved_expression_master(store,**runtime(),expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend)
        context=prepare_reference_expression_context(store,initial,budget)
    unchanged();private=context.store
    if master_operation:copy_binding(store,private,physical,budget)
    # Only this private projection drops the old publication binding. It still
    # physically reconstructs the old hand and verifies its exact shader state.
    current=private.load();appearance=tuple((k,v) for k,v in current.appearance if k!=APPEARANCE_KEY)
    if appearance!=current.appearance:
        private.save(replace(current,appearance=appearance,revision=current.revision+1),expected_project=current,expected_revision=current.revision)
    def expected():
        current=private.load()
        return dict(expected_project_id=current.project_id,expected_revision=current.revision,expected_master_blend=current.master_blend)
    if context.old_hand:
        verify_saved_expression_master(private,**runtime(),**expected())
        reset=apply_hand_revision(private,manifest_sha256=context.old_hand.sha256,selection='neutral',**runtime(),**expected())
        if reset.revision is None or reset.project.parts:raise ProjectStorageError('Original hand did not reset in the private material transaction')
    _,source_sha=_master_file(private,private.load().master_blend)
    body_source_sha=source_sha;body_sha=source_sha;body_observed={}
    if master_operation:
        from .expression_mutation import preserve_expressions
        current=private.load()
        desired=replace(current,parameters=initial.parameters,facial_parameters=initial.facial_parameters,height_m=initial.height_m)
        if desired!=current:private.save(replace(desired,revision=current.revision+1),expected_project=current,expected_revision=current.revision)
        edited=preserve_expressions(private,operation=master_operation,**runtime(),**expected())
        body_path,body_sha=_master_file(private,private.load().master_blend)
        if edited.revision is None:
            if body_sha!=body_source_sha:raise ProjectStorageError('Verified material-bound face no-op changed its master')
            unchanged();context.recheck(store,budget)
            return MaterialMasterNoOp(initial,master_operation,{'verified_noop':True,'material_parameters_preserved':True,
                'engine_import_verified':False,'visual_quality_approved':False},private.root)
        body_observed=getattr(edited,'observed',None) or {'body':edited.body_observed,'face':edited.face_observed}
        source_sha=body_sha
    prepared=prepare_skin_material_revision(private,spec=spec,**runtime(),**expected());unchanged();context.recheck(store,budget)
    material=prepared.directory/'material_human.blend';material_sha=prepared.material_master_sha256
    install_master_copy(private,material,material_sha,prepared.directory,budget)
    relative='master/versions/'+material_sha+'.blend'
    checked=_inspect_expression_copy(private,master_blend=relative,**runtime())
    if checked.sha256!=material_sha:raise ProjectStorageError('Inspected material master differs from its fresh candidate')
    if material_sha!=source_sha:
        publish_expression_receipt(private,context.expression_library,source_sha,checked,'skin_material_revision',budget)
    current=private.load()
    stage_unverified_master(private,material,authorized_source_root=prepared.directory,expected_project=current,
        expected_revision=current.revision,expected_sha256=material_sha,cancel=budget)
    rebuilt=None
    if context.old_hand:
        built=build_hand_library(private,**runtime(),**expected())
        selected=apply_hand_revision(private,manifest_sha256=built.library.sha256,selection=context.selection,**runtime(),**expected())
        if selected.revision is None or not selected.project.parts:raise ProjectStorageError('Material revision did not receive a freshly rebuilt compatible hand')
        parts=(replace(selected.project.parts[0],part_id=initial.parts[0].part_id),)
        validate_expression_part_rebind(initial.parts,parts)
        scene,sha=_master_file(private,selected.project.master_blend)
        receipt=load_hand_receipt(private,built.library,sha,context.selection,budget)
        rebuilt=RebuiltExpressionHand(private,built.library,scene,sha,receipt,parts,{'selection':context.selection,'rebuilt_library':built.observed})
    final=private.load();output,output_sha=_master_file(private,final.master_blend)
    expected_final=replace(initial,appearance=appearance,animations=(),master_blend=final.master_blend,parts=final.parts,
        revision=final.revision,geometry_state='generated_unverified',rig_profile=None)
    if final!=expected_final:raise ProjectStorageError('Material graph transaction changed unrelated character intent')
    verify_saved_expression_master(private,**runtime(),**expected())
    rt=runtime();rt.pop('mpfb_data_dir');inspect_saved_neutral_master(private,**rt,**expected())
    metadata_sha=_digest(private.file,budget);proposed_parts=rebuilt.parts if rebuilt else final.parts
    hashes={p:_digest(p,budget) for p in [output,material,*prepared.directory.glob('*.json'),
        *([body_path] if master_operation else [])]}
    def recheck():
        unchanged();context.recheck(store,budget)
        if private.load()!=final or _digest(private.file,budget)!=metadata_sha:raise ProjectStorageError('Private material graph changed before commit')
        for path,sha in hashes.items():
            if path.is_symlink() or not path.is_file() or _digest(path,budget)!=sha:raise ProjectStorageError('Verified material graph output changed before commit')
        registered_expression_source(private,final,budget)
        if rebuilt:
            load_hand_library(private,rebuilt.library.sha256,budget)
            if load_hand_receipt(private,rebuilt.library,output_sha,context.selection,budget)!=rebuilt.receipt:raise ProjectStorageError('Rebuilt material hand receipt changed')
        installed_expression_inputs(mpfb_data_dir,budget)
        if rebuilt:installed_inputs(mpfb_data_dir,budget)
    recheck()
    if master_operation:
        publish_expression_edit(store,private,initial.expression.library_sha256,body_source_sha,body_sha,master_operation,budget)
    publish_expression_edit(store,private,initial.expression.library_sha256,source_sha,material_sha,'skin_material_revision',budget)
    if rebuilt:publish_rebuilt_hand(store,rebuilt,budget)
    record={'schema_version':1,'policy':POLICY,'project_id':initial.project_id,'spec':spec.to_dict(),'source_master_sha256':source_sha,
        'material_master_sha256':material_sha,'final_master_sha256':output_sha,'expression_library_sha256':initial.expression.library_sha256,
        'hand_manifest_sha256':rebuilt.library.sha256 if rebuilt else None,'recipe_sha256':_digest(prepared.directory/'material_recipe.json',budget),
        'stage_sha256':_digest(prepared.directory/'material_stage.json',budget),'verification_sha256':prepared.verification_sha256,
        'glb_sha256':_digest(prepared.directory/'character.glb',budget),'visual_quality_approved':False,'engine_import_verified':False,'source_rights_changed':False}
    binding=install_binding(store,record,prepared.directory,budget)
    values=dict(initial.appearance);values[APPEARANCE_KEY]=binding;proposed_appearance=tuple(sorted(values.items()))
    def at_commit():
        recheck()
        candidate=replace(initial,master_blend='master/versions/'+output_sha+'.blend',parts=proposed_parts,appearance=proposed_appearance)
        registered_expression_source(store,candidate,budget)
        if registered_material_binding(store,candidate,budget)!=record:raise ProjectStorageError('Installed material binding differs before atomic publication')
    revision=stage_unverified_master(store,output,authorized_source_root=private.root,expected_project=initial,expected_project_id=initial.project_id,
        expected_revision=initial.revision,expected_sha256=output_sha,proposed_parts=proposed_parts,proposed_appearance=proposed_appearance,
        cancel=budget,before_project_save=at_commit)
    return SkinMaterialRevision(revision,binding,material_sha,record['hand_manifest_sha256'],
        {'original_master_preserved':True,'registered_hand_rebuilt':rebuilt is not None,'expression_strengths_preserved':True,
         'atomic_appearance_and_master_publication':True,'engine_import_verified':False,'visual_quality_approved':False,
         **({'operation':master_operation,'material_parameters_preserved':True,'body_edit':body_observed,
             'body_master_sha256':body_sha,'material_reapplication_required':material_sha!=body_sha} if master_operation else {})})
