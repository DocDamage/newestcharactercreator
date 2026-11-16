"""UNIT_ONLY orchestration bytes. No Blender scene, model, image or target proof."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import json,shutil
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.sprite_render_logic import request
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.core.sprite_render import POLICY,STAGE
from ucc.jobs.static_export_sources import ExportReview,ExportSource
from ucc.jobs.export_destination import plan_destination


class SpriteTransactionFixture:
    def __init__(self,root):
        self.f=ReferenceMasterFixture(root);self.store=self.f.store;before=self.store.load()
        self.project=self.store.save(replace(before,animations=(),appearance=((APPEARANCE_KEY,'a'*64),),revision=before.revision+1),expected_revision=before.revision)
        master=self.store.root/self.project.master_blend;self.sources={'master':master};digest=lambda p:sha256(p.read_bytes()).hexdigest()
        for name in ('expression_library','body_material'):
            path=root/(name+'.UNIT');path.write_text('UNIT_NOT_REAL_PROVENANCE');self.sources[name]=path
        self.binding={'spec':SkinMaterialSpec((.3,.2,.1),.6).to_dict(),'recipe_sha256':'b'*64,'stage_sha256':'c'*64,'verification_sha256':'d'*64,
            'source_master_sha256':master.stem,'material_master_sha256':master.stem,'final_master_sha256':master.stem}
        proofs=self.store.root/'materials/proofs';proofs.mkdir(parents=True)
        for value in ('b','c','d'):(proofs/(value*64+'.json')).write_text('{"UNIT_NOT_REAL_PROOF":true}')
        self.review=ExportReview(self.project.project_id,self.project.revision,digest(self.store.file),tuple(ExportSource(k,digest(p),k) for k,p in self.sources.items()))
        template=request();self.request=replace(template,project_id=self.project.project_id,revision=self.project.revision,project_sha256=self.review.project_sha256,
            source_bindings=tuple((s.asset_id,s.sha256) for s in self.review.sources),permissions=tuple(replace(template.permissions[0],asset_id=s.asset_id,source_sha256=s.sha256) for s in self.review.sources))
        candidate=root/'UNIT_CANDIDATE';candidate.mkdir();(candidate/'material_stage.json').write_text('{"changed":false}')
        self.prepared=SimpleNamespace(directory=candidate,source_master_sha256=master.stem,material_master_sha256=master.stem,stage_job_id='UNIT_STAGE',reopen_job_id='UNIT_REOPEN')
        self.exe=root/'UNIT_NOT_EXECUTABLE';self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE');self.worker=root/'UNIT_NOT_WORKER.py';self.worker.write_text('UNIT_NOT_EXECUTED')
        self.dest=plan_destination(root/'output',self.store.root)
        self.options=dict(request=self.request,destination=self.dest,blender_exe=self.exe,worker_script=self.worker,mpfb_data_dir=root)


class UnitRunner:
    def __init__(self,exe,jobs,worker):self.jobs=jobs
    def run(self,job,*,staged_inputs,**kwargs):
        folder=self.jobs/job.job_id;folder.mkdir()
        for name,p in staged_inputs.items():shutil.copy2(p,folder/name)
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        if job.operation==STAGE:
            (folder/'sprite_scene.blend').write_bytes(b'UNIT_NOT_A_BLENDER_SCENE')
            (folder/'sprite_stage.json').write_text(json.dumps(unit_report()))
            for i in range(4):(folder/f'sprite-{i:02d}.png').write_bytes(b'UNIT_NOT_AN_IMAGE')
            details={'policy':POLICY,'scene_sha256':digest(folder/'sprite_scene.blend'),'stage_sha256':digest(folder/'sprite_stage.json')}
        else:
            details=unit_proof();(folder/'sprite_verification.json').write_text(json.dumps(details))
        return SimpleNamespace(job_id=job.job_id,details=details),folder


def unit_report():return {'configuration':{'objects':{'UNIT_NOT_CAMERA':{'camera':{'ortho_scale':2.5}}}},'pivot':[.5,.9]}
def unit_proof():return {'UNIT_NOT_REAL_VERIFICATION':True}
def unit_pack(plan,frames,output,**kwargs):
    output.mkdir();(output/'sprite_sheet_000.png').write_bytes(b'UNIT_NOT_A_SPRITE_SHEET');(output/'sprite_atlas.json').write_text('{"UNIT_NOT_REAL_ATLAS":true}')
