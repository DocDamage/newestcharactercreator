"""Transaction orchestration doubles; never real character integration proof."""
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import tempfile,unittest
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.static_face_contract import unit_triangle
from ucc.core.errors import ProjectConflict,ProjectStorageError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.jobs.material_master_preview import preview_material_master
from ucc.jobs.master_preview import MasterPreview


class MaterialPreviewJobTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.f=ReferenceMasterFixture(Path(tmp.name).resolve())
        p=self.f.store.load();self.project=self.f.store.save(replace(p,animations=(),appearance=((APPEARANCE_KEY,'a'*64),),revision=p.revision+1),expected_revision=p.revision)
        self.spec=SkinMaterialSpec((.3,.2,.1),.6);sha=Path(self.project.master_blend).stem
        self.binding={'spec':self.spec.to_dict(),'recipe_sha256':'b'*64,'stage_sha256':'c'*64,'verification_sha256':'d'*64,
            'source_master_sha256':sha,'material_master_sha256':sha,'final_master_sha256':sha}
        for folder,ids in [('manifests',['a'*64]),('proofs',['b'*64,'c'*64,'d'*64])]:
            directory=self.f.store.root/'materials'/folder;directory.mkdir(parents=True)
            for identity in ids:(directory/(identity+'.json')).write_text('{"UNIT_NOT_PROOF":true}')
        self.prepared=SimpleNamespace(source_master_sha256=sha,material_master_sha256=sha)
        self.result=MasterPreview(unit_triangle(),self.project.project_id,self.project.revision,self.project.master_blend,sha,'e'*64,3,'UNIT_NOT_BLENDER',True)
        self.options=dict(blender_exe=Path('UNIT_NOT_EXE'),worker_script=Path('UNIT_NOT_WORKER'),mpfb_data_dir=Path('UNIT_NOT_DATA'),
            expected_project_id=self.project.project_id,expected_revision=self.project.revision,expected_master_blend=self.project.master_blend)
        self.prefix='ucc.jobs.material_master_preview.'
        self.patchers=[patch(self.prefix+'registered_material_binding',return_value=self.binding),
            patch(self.prefix+'project_sources',return_value={'master':self.f.store.root/self.project.master_blend}),
            patch(self.prefix+'prepare_skin_material_revision',return_value=self.prepared),patch(self.prefix+'preview_saved_master',return_value=self.result)]
        self.binding_read,self.sources,self.prepare,self.preview=[p.start() for p in self.patchers]
        for p in self.patchers:self.addCleanup(p.stop)

    def invoke(self,**kw):return preview_material_master(self.f.store,**(self.options|kw))

    def test_complete_surface_admitted_before_export_and_all_proofs_watched(self):
        before=self.f.store.file.read_bytes();result=self.invoke()
        self.prepare.assert_called_once();self.preview.assert_called_once()
        self.assertIs(self.preview.call_args.kwargs['full_surface'],True)
        self.assertEqual(self.preview.call_args.kwargs['material_spec'],self.spec)
        self.assertEqual(self.f.store.file.read_bytes(),before)
        watched={Path(n) for n,h in result.watched_inputs}
        self.assertIn(self.f.store.root/'materials'/'manifests'/('a'*64+'.json'),watched)
        self.assertIn(self.f.store.root/'materials'/'proofs'/('c'*64+'.json'),watched)
        self.assertIn(self.f.store.file,watched)

    def test_stale_and_precancel_stop_before_source_workers(self):
        with self.assertRaises(ProjectConflict):self.invoke(expected_revision=999)
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.invoke(cancel=cancel)
        self.prepare.assert_not_called();self.preview.assert_not_called()

    def test_material_repair_cannot_be_shown_as_saved_preview(self):
        self.prepare.return_value=SimpleNamespace(source_master_sha256=self.prepared.source_master_sha256,material_master_sha256='f'*64)
        with self.assertRaisesRegex(ProjectStorageError,'repair'):self.invoke()
        self.preview.assert_not_called()

    def test_proof_or_user_save_during_export_discards_result(self):
        def alter(**kwargs):
            (self.f.store.root/'materials'/'proofs'/('c'*64+'.json')).write_text('{"UNIT_CHANGED":true}')
            return self.result
        self.preview.side_effect=lambda *a,**kw:alter(**kw)
        with self.assertRaisesRegex(ProjectStorageError,'authority changed'):self.invoke()

    def test_total_budget_is_shared_and_expiry_never_starts_export(self):
        clock=[10.]
        def expired(*a,**kw):clock[0]=11.;return self.prepared
        self.prepare.side_effect=expired
        with patch(self.prefix+'time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ProjectStorageError,'deadline'):self.invoke(timeout_s=.1)
        self.prepare.assert_called_once();self.preview.assert_not_called()
