"""Synthetic target transaction inputs; NEVER model, Blender or engine evidence."""
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import json,shutil
from fixtures.godot_runtime_logic import RuntimeTransactionFixture
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import FILES
from ucc.jobs.godot_runtime_bundle import PrivateNativeRuntimeInputs
from ucc.jobs.godot_native_producer import ProducedNativeRuntimeInputs
from ucc.jobs.godot_native_sampling import NativeInteractionReferences
from ucc.jobs.godot_native_target import SCRIPTS


class NativeTargetFixture(RuntimeTransactionFixture):
    def __init__(self,root: Path):
        super().__init__(root);digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.bundle=self.store.root/'.ucc-candidates/godot-runtime-inputs'/self.request.job_id;self.bundle.mkdir(parents=True)
        for name in FILES:shutil.copy2(self.folder/name,self.bundle/name)
        (self.bundle/'request.json').write_bytes(canonical_bytes(self.request.to_dict()))
        self.production=self.store.root/'.ucc-jobs/unit-production/production.json';self.production.parent.mkdir(parents=True)
        stage,reopened=str(uuid4()),str(uuid4())
        self.production.write_bytes(canonical_bytes({'status':'SOURCE_AND_FRESH_REOPEN_VERIFIED','request_sha256':self.request.sha256,
            'stage_job_id':stage,'reopen_job_id':reopened,'frames_verified':300,'recipe_sha256':'a'*64,'native_verification_sha256':'b'*64}))
        self.produced=ProducedNativeRuntimeInputs(PrivateNativeRuntimeInputs(self.bundle,self.request.sha256,'c'*64),self.production,stage,reopened)
        identity=str(uuid4());self.samples=self.store.root/'.ucc-jobs'/identity;self.samples.mkdir()
        raw={'policy':'UNIT_ONLY','cases':[{'UNIT_NOT_SOURCE':True}]*2697,'views':[],'race_mix':{},'roles':[],
            'files':{name:{'sha256':sha256(b'UNIT_NOT_GEOMETRY').hexdigest(),'bytes':17} for name in ('expected_vec4.f32','expected_normals_vec4.f32')}}
        for name in raw['files']:(self.samples/name).write_bytes(b'UNIT_NOT_GEOMETRY')
        (self.samples/'native_samples.json').write_bytes(canonical_bytes(raw))
        self.references=NativeInteractionReferences(self.samples,identity,self.request.sha256,digest(self.samples/'native_samples.json'),digest(self.production))
        (self.samples/'sample_acceptance.json').write_bytes(canonical_bytes({'schema_version':1,'policy':'UNIT_ONLY',
            'request_sha256':self.request.sha256,'report_sha256':self.references.report_sha256,
            'production_receipt_sha256':self.references.production_receipt_sha256,'samples':2697,'reference_streams_validated':True,
            'engine_import_verified':False,'visual_quality_approved':False}))
        self.adapter=root/'unit-adapter';self.adapter.mkdir()
        for name in SCRIPTS:(self.adapter/name).write_text('UNIT_ADAPTER_NOT_EXECUTED')

    def target_kwargs(self) -> dict:
        return {'produced':self.produced,'references':self.references,'source_fbx':self.motion,
            'authorized_source_root':self.folder,'godot_exe':self.exe,'adapter_directory':self.adapter}
