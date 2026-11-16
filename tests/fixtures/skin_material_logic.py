"""Synthetic transaction metadata only; NEVER Blender, model or material evidence."""
from dataclasses import replace
from hashlib import sha256
import json,shutil
from pathlib import Path
from ucc.core.models import CharacterProject,PartInstance
from ucc.core.expressions import ExpressionState
from ucc.core.skin_material import SkinMaterialSpec,RECIPE_POLICY,canonical_bytes
from ucc.core.storage import ProjectStore
from ucc.jobs.protocol import JobResult


class MaterialFixture:
    def __init__(self,root: Path):
        self.store=ProjectStore(root/'project');self.store.root.mkdir()
        self.master_sha=sha256(b'BLENDER_UNIT_NOT_A_REAL_MODEL_SOURCE').hexdigest()
        self.master=self.store.root/'master/versions'/(self.master_sha+'.blend');self.master.parent.mkdir(parents=True)
        self.master.write_bytes(b'BLENDER_UNIT_NOT_A_REAL_MODEL_SOURCE')
        self.expression=self.store.root/'unit-expression.json';self.expression.write_bytes(b'{"rights":{"no_ai":true},"UNIT_NOT_MODEL":true}')
        self.hand=self.store.root/'unit-hand.json';self.hand.write_bytes(b'{"rights":{"no_ai":true},"UNIT_NOT_HAND":true}')
        self.library_sha=sha256(self.expression.read_bytes()).hexdigest();self.hand_sha=sha256(self.hand.read_bytes()).hexdigest()
        self.part=PartInstance('unit-part-instance','ucc-hand-v1-'+self.hand_sha+'-longer','hand.L')
        self.project=self.store.save(replace(CharacterProject.new('UNIT_NOT_RENDERABLE'),schema_version=3,
            master_blend='master/versions/'+self.master_sha+'.blend',geometry_state='generated_unverified',
            expression=ExpressionState(self.library_sha),parts=(self.part,)))
        self.exe=root/'unit-never-executed.exe';self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE')
        self.worker=root/'unit-never-executed.py';self.worker.write_text('# UNIT_PROCESS_DOUBLE_ONLY\n')
        self.data=root/'unit-data';self.data.mkdir();self.spec=SkinMaterialSpec((.58,.31,.19),.62)
        self.sources={'master':self.master,'expression_library':self.expression,'part:'+self.part.part_asset_id:self.hand}
        self.original_metadata=self.store.file.read_bytes();self.calls=[];self.callback=None

    def kwargs(self):
        return dict(spec=self.spec,blender_exe=self.exe,worker_script=self.worker,mpfb_data_dir=self.data,
            expected_project_id=self.project.project_id,expected_revision=self.project.revision,expected_master_blend=self.project.master_blend)

    def run(self,job,*,staged_inputs,**kwargs):
        self.calls.append(job.operation);folder=self.store.root/'.ucc-jobs'/job.job_id;folder.mkdir()
        for name,path in staged_inputs.items():shutil.copy2(path,folder/name)
        digest=lambda p:sha256(p.read_bytes()).hexdigest();options=job.options
        if job.operation=='stage_mpfb_skin_material':
            (folder/'material_human.blend').write_bytes(b'BLENDER_UNIT_NOT_A_REAL_MATERIAL_REVISION')
            (folder/'character.glb').write_bytes(b'UNIT_NOT_A_GLTF_ASSET')
            exported={'pbr':{'UNIT_ONLY_NOT_PBR':True},'uv':{'policy':'UCC_NATIVE_SOURCE_CORNER_UV_V1','source_corners':53512,
                'source_polygons':13378,'imported_vertices':14517,'maximum_uv_component_error':0.,'material_appearance_verified':False,'engine_import_verified':False},
                'maximum_relative_weight_error':0.,'maximum_morph_delta_error_m':0.}
            report={'schema_version':1,'policy':RECIPE_POLICY,'recipe_sha256':options['recipe_sha256'],'source_master_sha256':options['master_sha256'],
                'material_master_sha256':digest(folder/'material_human.blend'),'glb_sha256':digest(folder/'character.glb'),'spec_sha256':self.spec.sha256,
                'nonmaterial_state_sha256':'a'*64,'shader_sha256':'b'*64,'shape_key_count':22,'full_vertices':19158,'visible_vertices':13380,'bones':163,
                'changed':True,'blender_version':'5.3.UNIT_NOT_OBSERVED','export':exported,'project_pointer_changed':False,'engine_import_verified':False,
                'visual_quality_approved':False,'distribution_license_review_complete':False}
            (folder/'material_stage.json').write_bytes(canonical_bytes(report))
            details={'policy':RECIPE_POLICY,'stage_report_sha256':digest(folder/'material_stage.json'),'material_master_sha256':report['material_master_sha256'],
                'glb_sha256':report['glb_sha256'],'engine_import_verified':False}
        else:
            stage=json.loads((folder/'material_stage.json').read_text())
            keep={'schema_version','policy','recipe_sha256','source_master_sha256','material_master_sha256','glb_sha256','spec_sha256',
                'nonmaterial_state_sha256','shader_sha256','export','project_pointer_changed','engine_import_verified','visual_quality_approved','distribution_license_review_complete'}
            report={name:stage[name] for name in keep};report.update(stage_report_sha256=options['stage_report_sha256'],verified_reopen=True,saved_output_rebuilt_or_repaired=False)
            (folder/'material_verification.json').write_bytes(canonical_bytes(report))
            details={'policy':RECIPE_POLICY,'verification_sha256':digest(folder/'material_verification.json'),'material_master_sha256':report['material_master_sha256'],
                'glb_sha256':report['glb_sha256'],'engine_import_verified':False}
        if self.callback:self.callback(job.operation,folder)
        return JobResult(job.job_id,job.operation,'ok',details),folder
