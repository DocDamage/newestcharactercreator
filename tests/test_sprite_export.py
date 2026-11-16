"""Fault injection across real filesystem publication; renderer is explicitly mocked."""
from dataclasses import replace
from pathlib import Path
import os,tempfile,unittest
from unittest.mock import patch
from fixtures.sprite_transaction import SpriteTransactionFixture,UnitRunner,unit_report,unit_proof,unit_pack
from ucc.jobs.sprite_export import export_sprite_sample
from ucc.core.errors import ProjectConflict,ProjectStorageError


class SpriteExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.f=SpriteTransactionFixture(Path(temp.name).resolve())
        prefix='ucc.jobs.sprite_export.'
        patches=[patch(prefix+'static_export_sources',return_value=(self.f.review,self.f.sources,self.f.binding)),
            patch(prefix+'worker_dependency_files',return_value={self.f.worker}),patch(prefix+'prepare_skin_material_revision',return_value=self.f.prepared),
            patch(prefix+'BlenderJobRunner',UnitRunner),patch(prefix+'checked_sprite_evidence',return_value=(unit_report(),unit_proof())),
            patch(prefix+'pack_frames',side_effect=unit_pack),patch(prefix+'checked_atlas')]
        mocks=[p.start() for p in patches];self.prepare=mocks[2]
        for p in patches:self.addCleanup(p.stop)

    def invoke(self,**change):return export_sprite_sample(self.f.store,**(self.f.options|change))

    def test_stale_review_never_starts_source_worker(self):
        with self.assertRaises(ProjectConflict):self.invoke(request=replace(self.f.request,project_sha256='f'*64))
        self.prepare.assert_not_called();self.assertFalse(self.f.dest.path.exists())

    def test_concurrent_save_is_preserved_before_render_or_commit(self):
        def save(*a,**kw):
            self.changed=self.f.store.save(replace(self.f.project,name='UNIT_EXTERNAL_SAVE',revision=self.f.project.revision+1),expected_revision=self.f.project.revision)
            return self.f.prepared
        self.prepare.side_effect=save
        with self.assertRaises(ProjectConflict):self.invoke()
        self.assertEqual(self.f.store.load(),self.changed);self.assertFalse(self.f.dest.path.exists())

    def test_material_repair_cannot_be_published_as_the_saved_character(self):
        from types import SimpleNamespace
        self.prepare.return_value=SimpleNamespace(source_master_sha256='a'*64,material_master_sha256='b'*64)
        with self.assertRaisesRegex(ProjectStorageError,'repair'):self.invoke()
        self.assertFalse(self.f.dest.path.exists())

    def test_failure_after_atomic_rename_rolls_back_only_new_owned_folder(self):
        original=self.f.store.file.read_bytes();actual=os.replace
        def replace_journal(source,destination):
            if str(source).endswith('job_status.tmp') and 'PRIVATE_SPRITES_PUBLISHED' in Path(source).read_text():raise OSError('UNIT_FINAL_JOURNAL_FAILURE')
            return actual(source,destination)
        with patch('ucc.jobs.sprite_export.os.replace',side_effect=replace_journal):
            with self.assertRaisesRegex(OSError,'UNIT_FINAL_JOURNAL_FAILURE'):self.invoke()
        self.assertFalse(self.f.dest.path.exists());self.assertEqual(self.f.store.file.read_bytes(),original)
        self.assertEqual(len(list(self.f.dest.path.parent.glob('.ucc-export-*'))),1)
