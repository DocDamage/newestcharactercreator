"""Synthetic transaction boundaries only; actual Blender/Godot acceptance separate."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest,json,os
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.godot_export_logic import request,write_unit_engine_outputs,write_unit_morph_reference
from ucc.core.errors import ProjectConflict,ProjectStorageError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.jobs.static_export_sources import ExportReview,ExportSource
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.static_godot_export import export_static_godot


class StaticExportJobTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve();self.f=ReferenceMasterFixture(root)
        before=self.f.store.load();self.project=self.f.store.save(replace(before,animations=(),appearance=((APPEARANCE_KEY,'a'*64),),revision=before.revision+1),expected_revision=before.revision)
        spec=SkinMaterialSpec((.3,.2,.1),.6);master=self.f.store.root/self.project.master_blend;master_sha=master.stem
        self.sources={'master':master}
        for name in ('expression_library','body_material'):
            path=root/(name+'.UNIT');path.write_text('UNIT_NOT_REAL_PROVENANCE');self.sources[name]=path
        self.binding={'spec':spec.to_dict(),'recipe_sha256':'b'*64,'stage_sha256':'c'*64,'verification_sha256':'d'*64,
            'source_master_sha256':master_sha,'material_master_sha256':master_sha,'final_master_sha256':master_sha}
        proofs=self.f.store.root/'materials/proofs';proofs.mkdir(parents=True)
        for value in ('b','c','d'):(proofs/(value*64+'.json')).write_text('{"UNIT_NOT_REAL_PROOF":true}')
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.review=ExportReview(self.project.project_id,self.project.revision,digest(self.f.store.file),tuple(ExportSource(k,digest(p),k) for k,p in self.sources.items()))
        template=request();self.request=replace(template,project_id=self.project.project_id,revision=self.project.revision,project_sha256=self.review.project_sha256,
            source_bindings=tuple((s.asset_id,s.sha256) for s in self.review.sources),permissions=tuple(replace(template.permissions[0],asset_id=s.asset_id,source_sha256=s.sha256) for s in self.review.sources))
        candidate=root/'UNIT_NOT_REAL_CANDIDATE';candidate.mkdir();(candidate/'character.glb').write_bytes(b'UNIT_NOT_REAL_GLB');(candidate/'material_stage.json').write_text('{"changed":false}')
        self.prepared=SimpleNamespace(directory=candidate,source_master_sha256=master_sha,material_master_sha256=master_sha,stage_job_id='UNIT_STAGE',reopen_job_id='UNIT_REOPEN')
        self.exe=root/'UNIT_NOT_EXECUTABLE';self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE');self.worker=root/'UNIT_NOT_WORKER.py';self.worker.write_text('UNIT_NOT_EXECUTED')
        self.dest=plan_destination(root/'output',self.f.store.root);self.options=dict(request=self.request,destination=self.dest,blender_exe=self.exe,worker_script=self.worker,mpfb_data_dir=root,godot_exe=self.exe)
        prefix='ucc.jobs.static_godot_export.'
        patches=[patch(prefix+'static_export_sources',return_value=(self.review,self.sources,self.binding)),patch(prefix+'scripts',return_value={}),
            patch(prefix+'worker_dependency_files',return_value={self.worker}),patch(prefix+'prepare_skin_material_revision',return_value=self.prepared),
            patch(prefix+'verify_material_glb'),patch(prefix+'build_skin_plan',return_value=SimpleNamespace(to_dict=lambda:{'UNIT_NOT_REAL_PLAN':True})),
            patch(prefix+'write_morph_reference',side_effect=write_unit_morph_reference),patch(prefix+'run_engine',side_effect=lambda folder,*a,**kw:write_unit_engine_outputs(folder))]
        mocks=[p.start() for p in patches];self.prepare=mocks[3];self.engine=mocks[-1]
        for p in patches:self.addCleanup(p.stop)
        # Actual file copy/publish is exercised; only engine-produced bytes are test markers.
        self.payload_patch=patch('ucc.jobs.static_godot_engine.PAYLOAD',('character.glb','character.tscn','character_preview.tscn','project.godot','skin_plan.json','morph_reference.json','morph_reference.bin','request.json'))
        self.payload_patch.start();self.addCleanup(self.payload_patch.stop)
        package_patch=patch(prefix+'PAYLOAD',('character.glb','character.tscn','character_preview.tscn','project.godot','skin_plan.json','morph_reference.json','morph_reference.bin','request.json'))
        package_patch.start();self.addCleanup(package_patch.stop)

    def invoke(self,**change):return export_static_godot(self.f.store,**(self.options|change))

    def test_stale_review_never_starts_workers_or_creates_destination(self):
        with self.assertRaises(ProjectConflict):self.invoke(request=replace(self.request,project_sha256='f'*64))
        self.prepare.assert_not_called();self.assertFalse(self.dest.path.exists())

    def test_concurrent_source_save_is_preserved_before_engine_or_commit(self):
        def save(*a,**kw):
            self.changed=self.f.store.save(replace(self.project,name='UNIT_EXTERNAL_SAVE',revision=self.project.revision+1),expected_revision=self.project.revision)
            return self.prepared
        self.prepare.side_effect=save
        with self.assertRaises(ProjectConflict):self.invoke()
        self.assertEqual(self.f.store.load(),self.changed);self.engine.assert_not_called();self.assertFalse(self.dest.path.exists())

    def test_private_material_repair_cannot_be_exported_as_saved_character(self):
        self.prepare.return_value=SimpleNamespace(source_master_sha256='a'*64,material_master_sha256='b'*64)
        with self.assertRaisesRegex(ProjectStorageError,'repair'):self.invoke()
        self.engine.assert_not_called();self.assertFalse(self.dest.path.exists())

    def test_final_journal_failure_rolls_new_folder_back_to_retained_stage(self):
        actual=os.replace
        def replace_journal(source,destination):
            if str(source).endswith('job_status.tmp') and 'PRIVATE_GODOT_EXPORT_PUBLISHED' in Path(source).read_text():raise OSError('UNIT_FINAL_JOURNAL_FAILURE')
            return actual(source,destination)
        with patch('ucc.jobs.static_godot_export.os.replace',side_effect=replace_journal):
            with self.assertRaisesRegex(OSError,'UNIT_FINAL_JOURNAL_FAILURE'):self.invoke()
        self.assertFalse(self.dest.path.exists());self.assertEqual(self.f.store.load(),self.project)
        self.assertEqual(len(list(self.dest.path.parent.glob('.ucc-export-*'))),1)
