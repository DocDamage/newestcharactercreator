"""Real filesystem rollback/concurrency; explicitly mocked renderer markers."""
from dataclasses import replace
from pathlib import Path
from threading import Event
import os,tempfile,unittest
from unittest.mock import patch
from fixtures.facial_sprite_transaction import FacialTransactionFixture,FacialUnitRunner,unit_pack,unit_report,unit_proof
from ucc.jobs.facial_sprite_export import export_facial_sprites
from ucc.core.errors import ProjectConflict,ProjectStorageError


class FacialSpriteExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.f=FacialTransactionFixture(Path(temp.name).resolve())
        prefix='ucc.jobs.facial_sprite_export.'
        patches=[patch(prefix+'static_export_sources',return_value=(self.f.review,self.f.sources,self.f.binding)),
            patch(prefix+'worker_dependency_files',return_value={self.f.worker}),patch(prefix+'prepare_skin_material_revision',return_value=self.f.prepared),
            patch(prefix+'installed_expression_inputs',return_value={}),patch(prefix+'BlenderJobRunner',FacialUnitRunner),
            patch(prefix+'checked_facial_evidence',return_value=(unit_report(),unit_proof())),patch(prefix+'pack_frames',side_effect=unit_pack),patch(prefix+'checked_facial_atlas')]
        mocks=[p.start() for p in patches];self.prepare=mocks[2]
        for p in patches:self.addCleanup(p.stop)

    def invoke(self,**change):return export_facial_sprites(self.f.store,**(self.f.options|change))

    def test_stale_review_and_strengths_fail_before_workers(self):
        r=self.f.request
        with self.assertRaises(ProjectConflict):self.invoke(request=replace(r,review=replace(r.review,project_sha256='f'*64)))
        self.prepare.assert_not_called();self.assertFalse(self.f.dest.path.exists())

    def test_cancelled_before_work_has_no_destination_or_source_worker(self):
        event=Event();event.set()
        with self.assertRaisesRegex(ProjectStorageError,'cancelled'):self.invoke(cancel=event)
        self.prepare.assert_not_called();self.assertFalse(self.f.dest.path.exists())

    def test_concurrent_saved_strength_revision_remains_authoritative(self):
        def save(*a,**kw):
            expression=replace(self.f.project.expression,parameters=tuple((k,.25) for k,_ in self.f.project.expression.parameters))
            self.changed=self.f.store.save(replace(self.f.project,expression=expression,revision=self.f.project.revision+1),expected_revision=self.f.project.revision)
            return self.f.prepared
        self.prepare.side_effect=save
        with self.assertRaises(ProjectConflict):self.invoke()
        self.assertEqual(self.f.store.load(),self.changed);self.assertFalse(self.f.dest.path.exists())

    def test_material_repair_cannot_replace_the_reviewed_master(self):
        from types import SimpleNamespace
        self.prepare.return_value=SimpleNamespace(source_master_sha256='a'*64,material_master_sha256='b'*64)
        with self.assertRaisesRegex(ProjectStorageError,'repair'):self.invoke()
        self.assertFalse(self.f.dest.path.exists())

    def test_failure_after_atomic_rename_rolls_back_new_folder(self):
        original=self.f.store.file.read_bytes();actual=os.replace
        def replace_journal(source,destination):
            if str(source).endswith('job_status.tmp') and 'PRIVATE_ANIMATED_SPRITES_PUBLISHED' in Path(source).read_text():raise OSError('UNIT_FINAL_JOURNAL_FAILURE')
            return actual(source,destination)
        with patch('ucc.jobs.facial_sprite_export.os.replace',side_effect=replace_journal):
            with self.assertRaisesRegex(OSError,'UNIT_FINAL_JOURNAL_FAILURE'):self.invoke()
        self.assertFalse(self.f.dest.path.exists());self.assertEqual(self.f.store.file.read_bytes(),original)
        self.assertEqual(len(list(self.f.dest.path.parent.glob('.ucc-export-*'))),1)
