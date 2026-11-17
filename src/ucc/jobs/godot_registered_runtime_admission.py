"""Read-only current authority and actual V2 producer graph for retention/load."""
from __future__ import annotations
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.core.target_action import TargetActionBinding
from .target_action_storage import PreparedTargetAction
from .target_action_context import Budget

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import checked_sha, checked_uuid
from ucc.export.godot_candidate_contract import canonical_bytes, EngineInputPermission
from ucc.export.godot_registered_runtime_contract import (RegisteredInputSelection,
    RetainedProofReference, PROOF_ROLES, METADATA_LIMITS)
from ucc.export.godot_registered_native_recipe import validate_registered_native_recipe
from ucc.export.godot_runtime_contract import NativeRuntimeRequest, FILES, CODE_FILES
from ucc.export.godot_runtime_data import validate_runtime_files
from .godot_registered_native_producer import (PreparedRegisteredNativeSource, RECEIPT_POLICY,
    _result_report, _outputs)
from .godot_registered_native_inputs import _registered_sources
from .target_action_context import source_review, require_review, protected, check_target_action_catalog
from .target_action_storage import load_target_action, read_target_action_binding, ancestry, source_state
from .target_action_resources import host_code_snapshot
from .master_preview import _digest
from .godot_candidate_inputs import identity
from .protocol import JobRequest, JobResult
from .target_action_evidence import _worker
from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from .native_evidence import read_native_timeline
from .native_skin_evidence import validate_reopen_report
from .godot_registered_runtime_files import read_metadata, hash_file
from .expression_storage import safe_directory
from .export_guards import bounded_paths


def permission_bytes(permissions: tuple[EngineInputPermission,...]) -> bytes:
    if (type(permissions) is not tuple or not 3<=len(permissions)<=4
            or any(type(p) is not EngineInputPermission for p in permissions)
            or len({p.asset_id for p in permissions})!=len(permissions)):
        raise ValidationError("Registered retention needs distinct explicit typed permissions")
    for permission in permissions:permission.require_godot()
    return canonical_bytes([p.to_dict() for p in sorted(permissions,key=lambda p:p.asset_id)])


@dataclass(frozen=True, slots=True)
class CurrentRegisteredInputs:
    selection: RegisteredInputSelection
    project: CharacterProject
    binding: TargetActionBinding
    prepared_target: PreparedTargetAction
    sources: dict[str,Path]
    source_hashes: dict[str,str]
    guard: Callable[[],None]


def current_inputs(store: ProjectStore, selection: RegisteredInputSelection, database_path: Path,
        permissions: tuple[EngineInputPermission,...], budget: Budget,
        progress: Callable[[str],None] | None=None) -> CurrentRegisteredInputs:
    if type(selection) is not RegisteredInputSelection:
        raise ValidationError("Registered retention requires an explicit typed selection")
    permission_bytes(permissions)
    database=protected(Path(database_path))
    callback=None if progress is None else lambda name:progress("LOAD_TARGET_ACTION_"+str(name))
    prepared=load_target_action(store,database_path=database,**selection.loader_args(),
        cancel=budget.cancel,timeout_s=min(300,budget.remaining()),progress=callback)
    binding=read_target_action_binding(store,selection.binding_sha256,cancel=budget.cancel)
    project=store.load()
    def review_now():
        value=source_review(store,database,selection.clip_id,selection.project_id,selection.revision,
            "master/versions/"+selection.master_sha256+".blend",selection.project_sha256,budget)
        require_review(value,selection.source_binding_sha256,selection.catalog_record_sha256)
        return value
    review=review_now()
    if binding.source!=review.source or binding.target.project_sha256!=selection.project_sha256:
        raise ProjectConflict("Retained registered source context changed")
    sources=_registered_sources(store,project,budget.cancel)
    motion=[p for p in permissions if p.asset_id.startswith("motion:")]
    if len(motion)!=1 or motion[0].source_sha256!=binding.source.source_sha256:
        raise ValidationError("Registered retention needs exactly the selected original motion permission")
    sources[motion[0].asset_id]=review.source_path
    source_hashes={name:_digest(protected(path),budget.cancel) for name,path in sources.items()}
    if {p.asset_id:p.source_sha256 for p in permissions}!=source_hashes:
        raise ValidationError("Registered retention permission content differs from actual sources")
    def rights(current):
        if (current.policy.ue_only or current.policy.no_ai and
                (not motion[0].policy.no_ai or motion[0].policy.ai_input_allowed)):
            raise ValidationError("Registered retention cannot override source UE-only/NoAI")
        by_role={permission.asset_id:permission for permission in permissions}
        for name,path in sources.items():
            if name in {"master",motion[0].asset_id}:continue
            manifest,_,_=read_metadata(path,4*1024*1024,budget,expected_sha256=source_hashes[name])
            stored=manifest.get("rights",{})
            if type(stored) is not dict:
                raise ValidationError("Registered source rights metadata is malformed")
            permission=by_role[name]
            if stored.get("no_ai") and (not permission.policy.no_ai or permission.policy.ai_input_allowed):
                raise ValidationError("Registered retention cannot remove library/part NoAI")
    rights(review)
    hashes=dict(prepared.watched_inputs)
    for name,path in sources.items():
        if path in hashes and hashes[path]!=source_hashes[name]:
            raise ProjectStorageError("Registered source hashes disagree with loaded target authority")
        hashes[path]=source_hashes[name]
    authorities=ancestry((*hashes,database))
    authorities.update(dict(prepared.watched_identities))
    authorities[database]=(*identity(database)[:2],0,0)
    baseline=source_state(store,budget)
    host=host_code_snapshot(budget)
    def guard():
        budget.check()
        if host_code_snapshot(budget)!=host:
            raise ProjectStorageError("Registered retention host namespace changed")
        current=review_now();rights(current)
        if current!=review or store.load()!=project or source_state(store,budget)!=baseline:
            raise ProjectConflict("Registered retention current source/project/proof state changed")
        check_target_action_catalog(database,binding.source,
            expected_database_identity=authorities[database][:2],expected_parent_identity=authorities[database.parent][:2])
        for path,stamp in authorities.items():
            now=identity(protected(path))
            if (now[:2]!=stamp[:2] if path==database else now!=stamp):
                raise ProjectStorageError("Registered retention source/catalog ancestry changed")
        for path,digest in hashes.items():
            if _digest(protected(path),budget.cancel)!=digest:
                raise ProjectStorageError("Registered retention source/proof bytes changed")
        if _registered_sources(store,store.load(),budget.cancel)!={name:path for name,path in sources.items()
                if name!=motion[0].asset_id}:
            raise ProjectConflict("Registered retention prepared source registration changed")
    guard()
    return CurrentRegisteredInputs(selection,project,binding,prepared,sources,source_hashes,guard)


def proof_references(binding: TargetActionBinding) -> tuple[RetainedProofReference,...]:
    return tuple(RetainedProofReference(role,name,binding.file_map[name].sha256,binding.file_map[name].bytes)
                 for role,name in sorted(PROOF_ROLES.items()))


def preparation_paths(store: ProjectStore, preparation: PreparedRegisteredNativeSource) -> dict[str,Path]:
    if type(preparation) is not PreparedRegisteredNativeSource:
        raise ValidationError("Retention needs the typed completed V2 preparation locator")
    jobs=safe_directory(store,".ucc-jobs")
    for value in (preparation.stage_job_id,preparation.reopen_job_id):checked_uuid(value)
    work=protected(Path(preparation.workdir))
    if (work.parent!=jobs or not work.name.startswith("registered-native-source-")
            or preparation.production_receipt!=work/"native_production_receipt.json"
            or preparation.directory!=jobs/preparation.reopen_job_id):
        raise ProjectStorageError("Registered preparation escaped its exact project jobs")
    checked_uuid(work.name.removeprefix("registered-native-source-"))
    paths={name:Path(preparation.directory)/name for name in FILES}
    paths.update({"native_recipe.json":work/"native_recipe.json",
        "source_receipt.json":Path(preparation.production_receipt),
        "runtime_request.json":work/"runtime_request.json",
        "source_byte_validation.json":work/"byte_validation.json",
        "runtime_code_provenance.json":work/"runtime_code_provenance.json"})
    for prefix,job in (("stage",preparation.stage_job_id),("reopen",preparation.reopen_job_id)):
        paths[prefix+"_request.json"]=jobs/job/"request.json"
        paths[prefix+"_result.json"]=jobs/job/"result.json"
    paths["native_stage.json"]=jobs/preparation.stage_job_id/"native_stage.json"
    paths["native_verification.json"]=jobs/preparation.reopen_job_id/"native_verification.json"
    return paths


def _native_timeline(context: CurrentRegisteredInputs,budget: Budget) -> tuple[dict,dict]:
    binding=context.binding;directory=context.prepared_target.directory
    details=_worker(directory,"source_intake_first",binding.producer.source_intake_worker_job_ids[0],
        "inspect_fbx_animation",{"source_sha256":binding.source.source_sha256},binding,budget.check,input_project=None)
    source,_=read_snapshot(directory,details,binding.source.source_sha256,cancel_check=budget.check)
    profile,_=read_native_profile(directory/"native_mapping.json",binding.source.source_sha256,
        binding.source.snapshot_sha256,binding.target.master_sha256)
    base={"master_sha256":binding.target.master_sha256,"source_sha256":binding.source.source_sha256,
        "snapshot_sha256":binding.source.snapshot_sha256,"mapping_sha256":binding.mapping_sha256}
    details=_worker(directory,"body_first",binding.producer.body_worker_job_ids[0],
        "verify_native_fbx_body",base|{"render_private_frames":True},binding,budget.check)
    timeline,_=read_native_timeline(directory/"body_first",details,source,profile,base,cancel_check=budget.check)
    records=binding.file_map
    return timeline,base|{"review_sha256":records[PROOF_ROLES["native_review"]].sha256,
                          "timeline_sha256":records[PROOF_ROLES["native_timeline"]].sha256}


def validate_graph(paths: dict[str,Path],context: CurrentRegisteredInputs,receipt_sha: str,
        permissions: tuple[EngineInputPermission,...],budget: Budget,*,
        anchors: PreparedRegisteredNativeSource | None=None,
        check_source_outputs: bool=False) -> tuple[dict,dict,NativeRuntimeRequest,dict[str,str]]:
    """Recheck exact metadata, worker lineage and bytes; never execute code/apps."""
    checked_sha(receipt_sha)
    docs={};raws={};hashes={}
    for name,maximum in METADATA_LIMITS.items():
        docs[name],raws[name],hashes[name]=read_metadata(paths[name],maximum,budget,
            expected_sha256=receipt_sha if name=="source_receipt.json" else None)
    recipe=validate_registered_native_recipe(docs["native_recipe.json"])
    receipt=docs["source_receipt.json"]
    request=NativeRuntimeRequest.from_bytes(raws["runtime_request.json"])
    if (recipe["source_bindings"]!=context.source_hashes
            or canonical_bytes(recipe["project_snapshot"])!=canonical_bytes(context.project.to_dict())
            or recipe["target_action_binding_sha256"]!=context.selection.binding_sha256
            or canonical_bytes(recipe["target_action_binding"])!=canonical_bytes(context.binding.to_dict())
            or permission_bytes(permissions)!=permission_bytes(tuple(EngineInputPermission.from_dict(p) for p in recipe["permissions"]))
            or permission_bytes(permissions)!=permission_bytes(request.permissions)):
        raise ProjectConflict("Registered retained recipe differs from current selection/permissions")
    stage_id=receipt.get("stage_job_id");fresh_id=receipt.get("reopen_job_id")
    checked_uuid(stage_id);checked_uuid(fresh_id)
    if stage_id==fresh_id or {stage_id,fresh_id}&set(context.binding.producer.worker_job_ids):
        raise ValidationError("Registered native producer workers are not distinct from historical identities")
    expected={"schema_version":1,"policy":RECEIPT_POLICY,
        "status":"REGISTERED_SOURCE_AND_FRESH_REOPEN_VERIFIED_NOT_EXECUTED",
        "recipe_sha256":hashes["native_recipe.json"],"request_sha256":request.sha256,
        "target_action_binding_sha256":context.selection.binding_sha256,
        "stage_job_id":stage_id,"reopen_job_id":fresh_id,
        "native_stage_sha256":hashes["native_stage.json"],"native_verification_sha256":hashes["native_verification.json"],
        "byte_validation_sha256":hashes["source_byte_validation.json"],"frames_verified":300,
        **{name:False for name in ("runtime_code_provenance_verified","runtime_execution_verified",
            "engine_import_verified","visual_quality_approved","distribution_license_review_complete",
            "public_export_published","source_redistribution_authorized","cloud_transmission_authorized")}}
    if canonical_bytes(receipt)!=canonical_bytes(expected):
        raise ValidationError("Registered source receipt changed its closed admission/anchors")
    if anchors is not None and (anchors.recipe_sha256!=hashes["native_recipe.json"]
            or anchors.runtime_request_sha256!=request.sha256 or anchors.stage_job_id!=stage_id
            or anchors.reopen_job_id!=fresh_id or anchors.target_action_binding_sha256!=context.selection.binding_sha256):
        raise ValidationError("Registered preparation locator differs from its completed receipt")
    evidence=recipe["evidence_bindings"];bound=recipe["source_bindings"]
    if (request.project_id!=context.selection.project_id or request.revision!=context.selection.revision
            or request.project_file_sha256!=context.selection.project_sha256 or request.master_sha256!=context.selection.master_sha256
            or dict(request.source_bindings)!=bound or request.requested_capability!=recipe["requested_capability"]
            or dict(request.evidence_bindings)!={name:evidence[name] for name in ("native_review","native_timeline")}
            or hashes["runtime_code_provenance.json"]!=recipe["runtime_code_provenance_sha256"]):
        raise ValidationError("Registered byte request/provenance differs from source recipe")
    options={"master_sha256":bound["master"],"source_sha256":bound[recipe["motion_asset_id"]],
        "review_sha256":evidence["native_review"],"timeline_sha256":evidence["native_timeline"],
        "snapshot_sha256":evidence["source_snapshot"],"mapping_sha256":evidence["native_mapping"],
        "native_recipe_sha256":hashes["native_recipe.json"],"target_action_binding_sha256":context.selection.binding_sha256}
    reports=[]
    for prefix,job,operation,stage in (("stage",stage_id,"stage_registered_native_godot_runtime",True),
                                     ("reopen",fresh_id,"verify_registered_native_godot_runtime",False)):
        expected_job=JobRequest(job,operation,"candidate.blend",options if stage else options|{"native_stage_sha256":hashes["native_stage.json"]})
        actual_job=JobRequest.from_dict(docs[prefix+"_request.json"])
        result=JobResult.from_dict(docs[prefix+"_result.json"])
        if (canonical_bytes(actual_job.as_dict())!=canonical_bytes(expected_job.as_dict())
                or result.job_id!=job or result.operation!=operation or result.status!="ok"):
            raise ValidationError("Registered retained worker identity/operation changed")
        status=("REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED" if stage else
                "FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED")
        report,_=_result_report(result,paths["native_stage.json" if stage else "native_verification.json"].parent,
            hashes["native_recipe.json"],status,stage=stage,check=budget.check)
        saved=docs["native_stage.json" if stage else "native_verification.json"]
        if canonical_bytes(report)!=canonical_bytes(saved):
            raise ProjectStorageError("Registered report parser read different captured metadata")
        reports.append(saved)
    stage,fresh=reports
    timeline,native_bindings=_native_timeline(context,budget)
    for report in reports:validate_reopen_report(report["native_reopen"],native_bindings,timeline)
    if (fresh["native_stage_sha256"]!=hashes["native_stage.json"]
            or fresh["saved_output_rebuilt_or_repaired"] is not False
            or fresh["master_state_sha256"]!=stage["master_state_sha256"]):
        raise ValidationError("Registered retained source reopen lineage differs")
    if check_source_outputs:_outputs(paths["character.glb"].parent,stage["files"],budget.check,budget.cancel)
    for name,digest in request.files:
        if stage["files"].get(name,{}).get("sha256")!=digest:
            raise ValidationError("Registered retained byte request changed staged output hashes")
        if name in CODE_FILES and (recipe["implementation"][name]!=digest
                or paths[name].stat().st_size!=recipe["runtime_code_lengths"][name]):
            raise ValidationError("Registered private code identities differ from recipe")
    observed=validate_runtime_files(paths["character.glb"].parent,request,budget.check)
    if canonical_bytes(observed)!=canonical_bytes(docs["source_byte_validation.json"]):
        raise ValidationError("Registered runtime byte validation changed")
    context.guard()
    return recipe,receipt,request,hashes


def watch_preparation(preparation: PreparedRegisteredNativeSource,recipe: dict,receipt: dict,
        hashes: dict[str,str],budget: Budget) -> Callable[[],None]:
    """Seal completed source inputs/outputs and their canonical job ancestry."""
    from ucc.export.godot_native_recipe import INPUTS
    stage=Path(preparation.workdir).parent/preparation.stage_job_id
    fresh=Path(preparation.directory)
    stage_report,_,_=read_metadata(stage/"native_stage.json",4*1024*1024,budget,
                                   expected_sha256=receipt["native_stage_sha256"])
    bound=recipe["source_bindings"];evidence=recipe["evidence_bindings"]
    input_hashes={"master_sha256":bound["master"],"source_sha256":bound[recipe["motion_asset_id"]],
        "review_sha256":evidence["native_review"],"timeline_sha256":evidence["native_timeline"],
        "snapshot_sha256":evidence["source_snapshot"],"mapping_sha256":evidence["native_mapping"]}
    common={name:input_hashes[key] for name,key in INPUTS.items()}
    common.update(recipe["implementation"])
    for name,row in stage_report["files"].items():
        if name in common and common[name]!=row["sha256"]:
            raise ValidationError("Completed source code/input/output anchors disagree")
        common[name]=row["sha256"]
    common.update({"native_recipe.json":hashes["native_recipe.json"],
                   "native_stage.json":receipt["native_stage_sha256"]})
    expected={}
    def collect(directory,names):
        with closing(bounded_paths(directory,budget.cancel,maximum_entries=len(names)+2,
                                   allowed_directories=frozenset())) as paths:
            for path in paths:
                budget.check()
                if path==directory:continue
                name=path.name
                if name not in names or path.parent!=directory or path in expected or not path.is_file():
                    raise ProjectStorageError("Completed source job has an unknown/duplicate input/log/output")
                limit=(256*1024 if name in CODE_FILES or name=="native_recipe.json" else
                       4*1024*1024 if name.endswith('.json') and name not in {'target_timeline.json','source_snapshot.json'} else
                       16*1024*1024 if name in {'stdout.log','stderr.log'} else 512*1024*1024)
                digest,size=hash_file(path,limit,budget)
                if names[name] is not None and digest!=names[name]:
                    raise ProjectStorageError("Completed source job differs from its admission")
                expected[path]=(digest,size)
        if {path.name for path in expected if path.parent==directory}!=set(names):
            raise ProjectStorageError("Completed source job inventory is incomplete")
    for prefix,directory in (("stage",stage),("reopen",fresh)):
        names=common|{"request.json":hashes[prefix+"_request.json"],"result.json":hashes[prefix+"_result.json"],
                      "stdout.log":None,"stderr.log":None}
        if prefix=="reopen":names["native_verification.json"]=receipt["native_verification_sha256"]
        collect(directory,names)
    work_names={"native_recipe.json":hashes["native_recipe.json"],"runtime_code_provenance.json":hashes["runtime_code_provenance.json"],
        "runtime_request.json":hashes["runtime_request.json"],"byte_validation.json":hashes["source_byte_validation.json"],
        "native_production_receipt.json":hashes["source_receipt.json"]}
    collect(Path(preparation.workdir),work_names)
    authority=ancestry(expected)
    directories={directory:frozenset(path.name for path in expected if path.parent==directory)
                 for directory in (stage,fresh,Path(preparation.workdir))}
    def guard():
        budget.check()
        for path,stamp in authority.items():
            if identity(protected(path))!=stamp:
                raise ProjectStorageError("Completed native preparation ancestry/identity changed")
        for directory,names in directories.items():
            seen=set()
            for path in bounded_paths(directory,budget.cancel,maximum_entries=len(names)+2,allowed_directories=frozenset()):
                budget.check()
                if path==directory:continue
                if path.parent!=directory or path.name not in names or path.name in seen or not path.is_file():
                    raise ProjectStorageError("Completed native preparation namespace changed")
                seen.add(path.name)
            if seen!=set(names):raise ProjectStorageError("Completed native preparation is incomplete")
        for path,(digest,size) in expected.items():
            if hash_file(path,size,budget)!=(digest,size):
                raise ProjectStorageError("Completed native preparation bytes changed")
    guard()
    return guard
