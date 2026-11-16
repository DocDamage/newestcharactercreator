"""Boundary orchestration doubles only; no Blender result acceptance here."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import tempfile,unittest
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from ucc.core.errors import ProjectConflict,ProjectStorageError
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.jobs.material_expression_preview import preview_material_expressions


class MaterialExpressionJobTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.f=ReferenceMasterFixture(Path(tmp.name).resolve())
        p=self.f.store.load();self.project=self.f.store.save(replace(p,animations=(),appearance=((APPEARANCE_KEY,'a'*64),),revision=p.revision+1),expected_revision=p.revision)
        self.spec=SkinMaterialSpec((.3,.2,.1),.6);sha=Path(self.project.master_blend).stem
        self.binding={'spec':self.spec.to_dict(),'recipe_sha256':'b'*64,'stage_sha256':'c'*64,'verification_sha256':'d'*64,
            'source_master_sha256':sha,'material_master_sha256':sha,'final_master_sha256':sha}
        for folder,ids in [('manifests',['a'*64]),('proofs',['b'*64,'c'*64,'d'*64])]:
            directory=self.f.store.root/'materials'/folder;directory.mkdir(parents=True)
            for identity in ids:(directory/(identity+'.json')).write_text('{"UNIT_NOT_PROOF":true}')
        # Isolated boundary-byte fixtures; no executable is run.
        self.exe=Path(tmp.name)/'UNIT_NOT_EXECUTABLE';self.exe.write_bytes(b'UNIT_NOT_EXECUTABLE')
        self.worker=Path(tmp.name)/'UNIT_NOT_WORKER';self.worker.write_bytes(b'UNIT_NOT_WORKER')
        self.options=dict(blender_exe=self.exe,worker_script=self.worker,mpfb_data_dir=Path('UNIT_NOT_DATA'),
            expected_project_id=self.project.project_id,expected_revision=self.project.revision,expected_master_blend=self.project.master_blend)
        self.prefix='ucc.jobs.material_expression_preview.'
        patchers=[patch(self.prefix+'registered_material_binding',return_value=self.binding),
            patch(self.prefix+'project_sources',return_value={'master':self.f.store.root/self.project.master_blend}),
            patch(self.prefix+'worker_dependency_files',return_value={self.worker}),patch(self.prefix+'preview_saved_expressions')]
        self.binding_read,self.sources,self.dependencies,self.geometry=[p.start() for p in patchers]
        for p in patchers:self.addCleanup(p.stop)

    def invoke(self,**kw):return preview_material_expressions(self.f.store,**(self.options|kw))

    def test_stale_or_precancel_cannot_start_geometry_or_normal_workers(self):
        with self.assertRaises(ProjectConflict):self.invoke(expected_revision=999)
        cancel=Event();cancel.set()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled'):self.invoke(cancel=cancel)
        self.geometry.assert_not_called()

    def test_proof_change_during_geometry_discard_before_normal_stage(self):
        def changed(*a,**kw):(self.f.store.root/'materials/proofs'/('c'*64+'.json')).write_text('{"UNIT_MUTATION":true}')
        self.geometry.side_effect=changed
        with self.assertRaisesRegex(ProjectStorageError,'source, proof or adapter changed'):self.invoke()
        self.assertEqual(self.f.store.load(),self.project)

    def test_worker_failure_leaves_original_project_authoritative(self):
        self.geometry.side_effect=ProjectStorageError('UNIT real adapter failure boundary')
        with self.assertRaisesRegex(ProjectStorageError,'failure boundary'):self.invoke()
        self.assertEqual(self.f.store.load(),self.project)

    def test_one_total_deadline_covers_existing_geometry_and_normal_phase(self):
        clock=[10.]
        def expired(*a,**kw):clock[0]=12.
        self.geometry.side_effect=expired
        with patch(self.prefix+'time.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ProjectStorageError,'deadline'):self.invoke(timeout_s=1.)
        self.geometry.assert_called_once();self.assertEqual(self.f.store.load(),self.project)
