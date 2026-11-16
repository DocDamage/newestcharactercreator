"""NONSHIPPING source byte markers; mocked workers never prove Blender or Unreal."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import shutil
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.unreal_contract_logic import request
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.unreal_contract import PROFILE, READINESS_FLAGS
from ucc.export.unreal_blender_recipe import POLICY, STAGE, FILES, NORMAL_BYTES, VERIFICATION_FILE
from ucc.jobs.static_export_sources import ExportReview, ExportSource


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class UnrealSourceFixture:
    def __init__(self, root: Path):
        self.root = root
        f = ReferenceMasterFixture(root, hand=False); self.store = f.store
        self.project = self.store.load()
        self.sources = {'master':self.store.root/self.project.master_blend}
        for name in ('expression_library', 'body_material'):
            path = root/(name+'.UNIT'); path.write_bytes(b'UNIT_NOT_REAL_PROVENANCE')
            self.sources[name] = path
        self.binding = {'spec':SkinMaterialSpec((.3,.2,.1),.6).to_dict()}
        self.review = ExportReview(self.project.project_id, self.project.revision, digest(self.store.file),
            tuple(ExportSource(k, digest(v), k) for k,v in self.sources.items()))
        template = request()
        self.request = replace(template, project_id=self.project.project_id, revision=self.project.revision,
            project_sha256=self.review.project_sha256,
            source_bindings=tuple((s.asset_id,s.sha256) for s in self.review.sources),
            permissions=tuple(replace(template.permissions[0], asset_id=s.asset_id, source_sha256=s.sha256)
                for s in self.review.sources))
        self.exe = root/'UNIT_NOT_EXECUTABLE'; self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE')
        bridge = root/'bridge'; bridge.mkdir(); self.worker = bridge/'UNIT_NOT_WORKER.py'
        self.worker.write_bytes(b'UNIT_NOT_EXECUTED')
        self.data = root/'mpfb/data'; self.data.mkdir(parents=True)
        (self.data/'UNIT_NOT_REAL_DATA').write_bytes(b'UNIT_DATA')
        self.calls = []; self.after_stage = lambda:None; self.after_verify = lambda inputs,folder:None
        self.alter_proof = lambda proof:None

    @property
    def options(self):
        return dict(request=self.request, blender_exe=self.exe, worker_script=self.worker,
                    mpfb_data_dir=self.data)

    def run(self, job, *, staged_inputs, cancel, timeout_s):
        folder = self.store.root/'.ucc-jobs'/('unreal-source-'+self.request.job_id)/'workers'/job.job_id
        folder.mkdir(parents=True)
        for name,path in staged_inputs.items():
            shutil.copy2(path, folder/name)
        self.calls.append((job.operation, timeout_s, cancel))
        if job.operation == STAGE:
            for name in FILES:
                path = folder/name
                path.write_bytes(bytes(NORMAL_BYTES) if name == 'source_corner_normals.bin' else
                    b'UNIT_NOT_REAL_SOURCE:'+name.encode())
            (folder/'unreal_source_stage.json').write_bytes(canonical_bytes({
                'fbx_metadata':{'expected_unreal_material_slot_name':'UNIT_SLOT_NOT_REAL'}}))
            files = {name:digest(folder/name) for name in FILES}
            details = {'policy':POLICY, 'request_sha256':self.request.sha256,
                       'files':files, 'engine_import_verified':False}
            self.after_stage()
        else:
            files = {name:job.options[name.replace('.', '_')+'_sha256'] for name in FILES}
            proof = {'schema_version':1, 'policy':POLICY, 'profile':PROFILE,
                'request_sha256':self.request.sha256, 'recipe_sha256':job.options['recipe_sha256'],
                'master_sha256':job.options['master_sha256'], 'files':files,
                'original_state_preserved':True, 'source_reference_recomputed':True,
                'fresh_original_master_reopened':True, 'exported_fbx_rebuilt':False,
                'project_pointer_changed':False, 'runtime_deformation_verified':False,
                **{name:False for name in READINESS_FLAGS}}
            self.alter_proof(proof)
            (folder/VERIFICATION_FILE).write_bytes(canonical_bytes(proof))
            details = {'policy':POLICY, 'request_sha256':self.request.sha256,
                'verification_sha256':digest(folder/VERIFICATION_FILE), 'files':files,
                'engine_import_verified':False}
            self.after_verify(staged_inputs, folder)
        return SimpleNamespace(details=details), folder

    def patches(self):
        prefix = 'ucc.jobs.unreal_preparation.'
        return [patch(prefix+'static_export_sources', return_value=(self.review,self.sources,self.binding)),
            patch(prefix+'worker_dependency_files', return_value={self.worker}),
            patch(prefix+'verify_saved_expression_master'),
            patch(prefix+'BlenderJobRunner.run', side_effect=self.run)]
