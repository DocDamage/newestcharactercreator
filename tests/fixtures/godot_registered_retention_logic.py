"""NONSHIPPING synthetic source graph; native geometry/context admission is stubbed."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from test_godot_registered_native_recipe import recipe_args
from fixtures.godot_native_logic import stage_report
from ucc.core.storage import ProjectStore
from ucc.core.errors import ProjectConflict
from ucc.export.godot_candidate_contract import canonical_bytes, EngineInputPermission
from ucc.export.godot_registered_native_recipe import build_registered_native_recipe, POLICY
from ucc.export.godot_runtime_contract import FILES, CODE_FILES, NativeRuntimeRequest
from ucc.export.godot_registered_runtime_contract import RegisteredInputSelection
from ucc.jobs.godot_registered_native_producer import OUTPUTS, RECEIPT_POLICY, PreparedRegisteredNativeSource
from ucc.jobs.protocol import JobRequest, JobResult

OBSERVED={"status":"NONSHIPPING_BYTES_VALIDATOR_DOUBLE","engine_import_verified":False}


def digest(path):return sha256(Path(path).read_bytes()).hexdigest()


class RetentionFixture:
    def __init__(self,root):
        self.root=Path(root).resolve();self.store=ProjectStore(self.root/"project")
        self.store.root.mkdir()
        args=recipe_args();old=args["target_action_binding"]
        inputs={"candidate.blend":b"NONSHIPPING_NOT_A_MASTER_BLEND",
            "source.fbx":b"NONSHIPPING_NOT_A_SOURCE_FBX",
            "review_motion.blend":b"NONSHIPPING_NOT_A_REVIEW_BLEND",
            "target_timeline.json":b'{"nonshipping":"not_a_timeline"}',
            "source_snapshot.json":b'{"nonshipping":"not_a_snapshot"}',
            "native_mapping.json":b'{"nonshipping":"not_a_mapping"}'}
        h=lambda name:sha256(inputs[name]).hexdigest()
        self.project=replace(args["project"],master_blend="master/versions/"+h("candidate.blend")+".blend")
        self.store.file.write_bytes(canonical_bytes(self.project.to_dict()))
        source=replace(old.source,source_sha256=h("source.fbx"),snapshot_sha256=h("source_snapshot.json"))
        files=tuple(replace(row,sha256=h({"body_first/review_motion.blend":"review_motion.blend",
            "body_first/target_timeline.json":"target_timeline.json"}.get(row.name,row.name)),
            bytes=len(inputs[{"body_first/review_motion.blend":"review_motion.blend",
            "body_first/target_timeline.json":"target_timeline.json"}.get(row.name,row.name)]))
            if row.name in {"body_first/review_motion.blend","body_first/target_timeline.json","source_snapshot.json","native_mapping.json"}
            else row for row in old.files)
        self.binding=replace(old,source=source,mapping_sha256=h("native_mapping.json"),files=files,
            target=replace(old.target,project_id=self.project.project_id,revision=self.project.revision,
                project_sha256=digest(self.store.file),master_sha256=h("candidate.blend")))
        sources=dict(args["source_bindings"]);sources["master"]=h("candidate.blend");sources[args["motion_asset_id"]]=h("source.fbx")
        self.permissions=tuple(replace(p,source_sha256=sources[p.asset_id]) for p in args["permissions"])
        self.selection=RegisteredInputSelection(self.project.project_id,self.project.revision,digest(self.store.file),
            h("candidate.blend"),source.clip_id,self.binding.sha256,source.source_binding_sha256,source.catalog_record_sha256)
        self.revoked=False
        def guard():
            if self.revoked or self.store.load()!=self.project:raise ProjectConflict("NONSHIPPING source policy/project changed")
        self.context=SimpleNamespace(selection=self.selection,project=self.project,binding=self.binding,
            prepared_target=SimpleNamespace(directory=self.store.root/"animations/actions"/self.binding.sha256),
            source_hashes=sources,sources={},guard=guard)
        jobs=self.store.root/".ucc-jobs";jobs.mkdir()
        self.work=jobs/("registered-native-source-"+str(UUID(int=1000)));
        self.stage=jobs/str(UUID(int=2000));self.fresh=jobs/str(UUID(int=3000))
        for directory in (self.work,self.stage,self.fresh):directory.mkdir()
        code={name:("# NONSHIPPING_NOT_EXECUTED:"+name).encode() for name in CODE_FILES}
        provenance=canonical_bytes({"nonshipping":"identity_only_not_admitted"})
        args.update(project=self.project,project_file_sha256=self.selection.project_sha256,
            target_action_binding=self.binding,target_action_binding_sha256=self.binding.sha256,
            source_bindings=sources,permissions=self.permissions,
            evidence_bindings={"native_review":h("review_motion.blend"),"native_timeline":h("target_timeline.json"),
                "source_snapshot":h("source_snapshot.json"),"native_mapping":h("native_mapping.json")},
            implementation={name:sha256(value).hexdigest() for name,value in code.items()},
            runtime_code_lengths={name:len(value) for name,value in code.items()},
            runtime_code_provenance_sha256=sha256(provenance).hexdigest())
        self.recipe=build_registered_native_recipe(**args)
        recipe_raw=canonical_bytes(self.recipe);recipe_sha=sha256(recipe_raw).hexdigest()
        for directory in (self.stage,self.fresh):
            for name,data in inputs.items():(directory/name).write_bytes(data)
            (directory/"native_recipe.json").write_bytes(recipe_raw)
            for name in OUTPUTS:(directory/name).write_bytes(code.get(name,("NONSHIPPING_NOT_NATIVE:"+name).encode()))
        stage=stage_report(recipe_sha);stage["policy"]=POLICY
        stage["files"]={name:{"sha256":digest(self.stage/name),"bytes":(self.stage/name).stat().st_size} for name in OUTPUTS}
        stage_raw=canonical_bytes(stage);stage_sha=sha256(stage_raw).hexdigest()
        for directory in (self.stage,self.fresh):(directory/"native_stage.json").write_bytes(stage_raw)
        fresh={key:value for key,value in stage.items() if key not in {"source_names","fps","numpy_version","files","export_optimize_animation_size"}}
        fresh.update(status="FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED",native_stage_sha256=stage_sha,
            saved_output_rebuilt_or_repaired=False,frames=[dict(frame=i,source_error_m=0.,normal_vector_error=0.,raw_error_m=0.,
                reconstruction_error_m=0.,bone_world_error=0.) for i in range(1,301)])
        fresh_raw=canonical_bytes(fresh);fresh_sha=sha256(fresh_raw).hexdigest()
        (self.fresh/"native_verification.json").write_bytes(fresh_raw)
        e=args["evidence_bindings"]
        options=dict(master_sha256=sources["master"],source_sha256=sources[args["motion_asset_id"]],
            snapshot_sha256=e["source_snapshot"],mapping_sha256=e["native_mapping"],review_sha256=e["native_review"],
            timeline_sha256=e["native_timeline"],native_recipe_sha256=recipe_sha,target_action_binding_sha256=self.binding.sha256)
        for directory,is_stage in ((self.stage,True),(self.fresh,False)):
            operation="stage_registered_native_godot_runtime" if is_stage else "verify_registered_native_godot_runtime"
            job=JobRequest(directory.name,operation,"candidate.blend",options if is_stage else options|{"native_stage_sha256":stage_sha})
            report=stage if is_stage else fresh
            details=dict(policy=POLICY,status=report["status"],frame_count=300,engine_import_verified=False)
            details["native_stage_sha256" if is_stage else "native_verification_sha256"]=stage_sha if is_stage else fresh_sha
            (directory/"request.json").write_bytes(canonical_bytes(job.as_dict()))
            (directory/"result.json").write_bytes(canonical_bytes(JobResult(job.job_id,operation,"ok",details).as_dict()))
            for name in ("stdout.log","stderr.log"):(directory/name).write_bytes(b"NONSHIPPING_NOT_PROCESS_LOG")
        request=NativeRuntimeRequest(str(UUID(int=4000)),self.project.project_id,self.project.revision,
            self.selection.project_sha256,sources["master"],tuple((name,digest(self.fresh/name)) for name in sorted(FILES)),
            tuple(sources.items()),tuple((name,e[name]) for name in ("native_review","native_timeline")),self.permissions,args["capability"])
        receipt=dict(schema_version=1,policy=RECEIPT_POLICY,status="REGISTERED_SOURCE_AND_FRESH_REOPEN_VERIFIED_NOT_EXECUTED",
            recipe_sha256=recipe_sha,request_sha256=request.sha256,target_action_binding_sha256=self.binding.sha256,
            stage_job_id=self.stage.name,reopen_job_id=self.fresh.name,native_stage_sha256=stage_sha,
            native_verification_sha256=fresh_sha,byte_validation_sha256=sha256(canonical_bytes(OBSERVED)).hexdigest(),frames_verified=300,
            **{name:False for name in ("runtime_code_provenance_verified","runtime_execution_verified","engine_import_verified",
                "visual_quality_approved","distribution_license_review_complete","public_export_published",
                "source_redistribution_authorized","cloud_transmission_authorized")})
        for name,data in {"native_recipe.json":recipe_raw,"runtime_code_provenance.json":provenance,
            "runtime_request.json":canonical_bytes(request.to_dict()),"byte_validation.json":canonical_bytes(OBSERVED),
            "native_production_receipt.json":canonical_bytes(receipt)}.items():(self.work/name).write_bytes(data)
        self.preparation=PreparedRegisteredNativeSource(self.work,self.fresh,self.work/"native_production_receipt.json",
            recipe_sha,request.sha256,self.binding.sha256,self.stage.name,self.fresh.name)
        self.receipt_sha=digest(self.preparation.production_receipt)

    def retain_args(self):
        return dict(selection=self.selection,preparation=self.preparation,expected_production_receipt_sha256=self.receipt_sha,
            database_path=self.root/"unused-fixture-catalog.sqlite",permissions=self.permissions)
