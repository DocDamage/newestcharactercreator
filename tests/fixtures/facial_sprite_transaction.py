"""UNIT filesystem transaction markers, NEVER target-application evidence."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
import json,shutil
from fixtures.sprite_transaction import SpriteTransactionFixture,unit_report,unit_proof
from ucc.core.expression_clip import build_expression_clip
from ucc.core.facial_sprites import FacialSpriteRequest,POLICY,STAGE
from ucc.core.sprite_render import canonical
from ucc.jobs.static_export_sources import ExportReview,ExportSource


class FacialTransactionFixture(SpriteTransactionFixture):
    def __init__(self,root):
        super().__init__(root)
        self.sources['expression_library']=self.store.root/'expressions/manifests'/(self.project.expression.library_sha256+'.json')
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.review=ExportReview(self.project.project_id,self.project.revision,digest(self.store.file),tuple(ExportSource(k,digest(p),k) for k,p in self.sources.items()))
        review=replace(self.request,source_bindings=tuple((s.asset_id,s.sha256) for s in self.review.sources),
            permissions=tuple(replace(self.request.permissions[0],asset_id=s.asset_id,source_sha256=s.sha256) for s in self.review.sources))
        self.request=FacialSpriteRequest(review,canonical(build_expression_clip(self.project,self.sources['master'].stem)))
        self.options['request']=self.request


class FacialUnitRunner:
    def __init__(self,exe,jobs,worker):self.jobs=jobs
    def run(self,job,*,staged_inputs,**kwargs):
        folder=self.jobs/job.job_id;folder.mkdir()
        for name,p in staged_inputs.items():shutil.copy2(p,folder/name)
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        if job.operation==STAGE:
            (folder/'facial_sprite_scene.blend').write_bytes(b'UNIT_NOT_A_BLENDER_SCENE')
            (folder/'facial_sprite_stage.json').write_text(json.dumps(unit_report()))
            for d in range(4):
                for f in range(1,26):(folder/f'facial-{d:02d}-{f:02d}.png').write_bytes(b'UNIT_NOT_AN_IMAGE')
            details={'policy':POLICY,'scene_sha256':digest(folder/'facial_sprite_scene.blend'),'stage_sha256':digest(folder/'facial_sprite_stage.json')}
        else:
            details=unit_proof();(folder/'facial_sprite_verification.json').write_text(json.dumps(details))
        return SimpleNamespace(job_id=job.job_id,details=details),folder


def unit_pack(plan,frames,output,**kwargs):
    output.mkdir()
    for i in range(4):(output/f'sprite_sheet_{i:03d}.png').write_bytes(b'UNIT_NOT_A_SPRITE_SHEET')
    (output/'sprite_atlas.json').write_text('{"UNIT_NOT_REAL_ATLAS":true}')
