"""Nonshipping byte markers for transaction faults; never Unity/Blender evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.unity_contract_logic import request
from ucc.core.skin_material import APPEARANCE_KEY, SkinMaterialSpec
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.static_export_sources import ExportReview, ExportSource
from ucc.jobs.unity_engine import PreparedUnityEngine
from ucc.jobs.unity_export_payload import engine_payload, PRIVATE_INPUTS
from ucc.jobs.unity_runtime_verification import VerifiedUnityRuntime


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class UnityTransactionFixture:
    def __init__(self, root: Path):
        self.root = root
        self.f = ReferenceMasterFixture(root)
        before = self.f.store.load()
        self.project = self.f.store.save(replace(before, animations=(), appearance=((APPEARANCE_KEY, 'a'*64),),
            revision=before.revision+1), expected_revision=before.revision)
        self.store = self.f.store
        master = self.store.root/self.project.master_blend
        self.sources = {'master':master}
        for name in ('expression_library', 'body_material'):
            path = root/(name+'.UNIT'); path.write_text('UNIT_NOT_REAL_PROVENANCE')
            self.sources[name] = path
        self.binding = {'spec':SkinMaterialSpec((.3, .2, .1), .6).to_dict(),
            'recipe_sha256':'b'*64, 'stage_sha256':'c'*64, 'verification_sha256':'d'*64,
            'source_master_sha256':master.stem, 'material_master_sha256':master.stem, 'final_master_sha256':master.stem}
        self.proofs = self.store.root/'materials/proofs'; self.proofs.mkdir(parents=True)
        for value in ('b', 'c', 'd'):
            (self.proofs/(value*64+'.json')).write_text('{"UNIT_NOT_REAL_PROOF":true}')
        self.exe = root/'UNIT_NOT_EXECUTABLE'; self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE')
        self.worker = root/'UNIT_NOT_WORKER.py'; self.worker.write_text('UNIT_NOT_EXECUTED')
        self.review = ExportReview(self.project.project_id, self.project.revision, digest(self.store.file),
            tuple(ExportSource(k, digest(p), k) for k, p in self.sources.items()))
        template = request()
        self.request = replace(template, project_id=self.project.project_id, revision=self.project.revision,
            project_sha256=self.review.project_sha256, unity_executable_sha256=digest(self.exe),
            source_bindings=tuple((s.asset_id, s.sha256) for s in self.review.sources),
            permissions=tuple(replace(template.permissions[0], asset_id=s.asset_id, source_sha256=s.sha256)
                for s in self.review.sources))
        engine_root = root/'UNIT_NOT_REAL_ENGINE'; engine_root.mkdir()
        folder = engine_root/'reopen'; folder.mkdir()
        for name in engine_payload() | PRIVATE_INPUTS:
            path = folder/name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('UNIT_NOT_REAL_UNITY_DATA:'+name).encode())
        (folder/'request.json').write_bytes(canonical_bytes(self.request.to_dict()))
        (folder/'Assets/UCC/source_reference.json').write_bytes(canonical_bytes({'material_spec':self.binding['spec']}))
        saved = {name:digest(folder/name) for name in engine_payload() | PRIVATE_INPUTS}
        spec = SkinMaterialSpec.from_dict(self.binding['spec'])
        recipe = {'schema_version':1, 'policy':'UCC_UNITY_EDITOR_JOB_V1', 'request_sha256':self.request.sha256,
            'master_sha256':master.stem, 'weights_sha256':saved['Assets/UCC/source_weights.json'],
            'fbx_sha256':saved['Assets/UCC/character.fbx'], 'source_reference_sha256':saved['Assets/UCC/source_reference.json'],
            'native_mesh_sha256':'c'*64, 'topology_sha256':'d'*64,
            'color_srgb':dict(zip('rgba', (*spec.base_color_srgb, 1.))), 'roughness':spec.roughness}
        (folder/'engine_recipe.json').write_bytes(canonical_bytes(recipe))
        receipt = engine_root/'native-import-receipt.json'
        receipt.write_bytes(canonical_bytes({'saved_files':saved, 'UNIT_NOT_REAL_NATIVE_RECEIPT':True}))
        self.engine = PreparedUnityEngine(folder, self.request.sha256, 'c'*64, 'd'*64, {}, digest(receipt))
        self.prepared = SimpleNamespace(verification_sha256='a'*64)
        self.runtime_source = SimpleNamespace(verification_sha256='b'*64)
        self.destination = plan_destination(root/'output', self.store.root)
        self.options = dict(request=self.request, destination=self.destination, blender_exe=self.exe,
            worker_script=self.worker, mpfb_data_dir=root, unity_exe=self.exe)

    def patches(self):
        prefix = 'ucc.jobs.unity_export.'
        def verify(engine, source, **options):
            options['guard']()
            assert engine.directory == self.destination.path
            assert options['native_import_receipt'] == self.engine.directory.parent/'native-import-receipt.json'
            return VerifiedUnityRuntime(self.root, self.request.sha256, 'f'*64, .000001, .1)
        return [patch(prefix+'static_export_sources', return_value=(self.review, self.sources, self.binding)),
            patch(prefix+'worker_dependency_files', return_value={self.worker}),
            patch(prefix+'prepare_unity_source', return_value=self.prepared),
            patch(prefix+'prepare_unity_runtime_source', return_value=self.runtime_source),
            patch(prefix+'prepare_unity_engine', return_value=self.engine),
            patch(prefix+'verify_unity_runtime', side_effect=verify)]
