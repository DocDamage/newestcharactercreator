"""API filesystem/pixel transactions; explicit doubles replace every native job."""
from dataclasses import replace
from pathlib import Path
import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from fixtures.body_sprite_sources import BodySourceFixture
from fixtures.body_sprite_images import image_evidence
from ucc.core.body_sprites import POLICY,STAGE
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.jobs.body_sprite_export import export_body_sprite_sample
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.master_preview import _digest
from ucc.jobs.protocol import JobResult


class BodySpriteExportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.f=BodySourceFixture(self.root)
        pixels=self.root/'UNIT_IMAGE_REFERENCES';pixels.mkdir()
        _,self.cache,*_=image_evidence(pixels,self.f.request)
        self.calls=[];self.after_stage=None;self.prefix='ucc.jobs.body_sprite_sources.'
        self.addCleanup(patch.stopall)
        patch('ucc.jobs.target_action_evidence.validate_retained_target_action',return_value=self.cache).start()
        patch(self.prefix+'_character_sources',return_value=self.f.paths).start()
        patch(self.prefix+'worker_dependency_files',return_value={self.f.f.script}).start()
        patch(self.prefix+'host_code_snapshot',return_value={}).start()
        patch(self.prefix+'worker_namespace_snapshot',return_value={}).start()
        patch(self.prefix+'blender_helper_inventory',return_value={}).start()
        patch(self.prefix+'inspect_selected_fbx',side_effect=self.f.intake).start()
        owner=self
        class Runner:
            def __init__(self,exe,jobs,worker):self.jobs=jobs
            def run(self,job,*,staged_inputs,**kwargs):
                folder=self.jobs/job.job_id;folder.mkdir()
                for name,path in staged_inputs.items():shutil.copyfile(path,folder/name)
                owner.calls.append(job)
                if job.operation==STAGE:
                    (folder/'body_sprite_scene.blend').write_bytes(b'UNIT_NOT_A_RENDERED_BLENDER_SCENE')
                    _,_,options,report,_,write=image_evidence(folder,owner.f.request)
                    options.clear();options.update(job.options,scene_sha256=_digest(folder/'body_sprite_scene.blend'))
                    report['bindings']=dict(job.options);report['scene_sha256']=options['scene_sha256']
                    owner.proof=write()
                    details={'policy':POLICY,'scene_sha256':options['scene_sha256'],'stage_sha256':options['stage_sha256']}
                    if owner.after_stage:owner.after_stage()
                else:
                    details=owner.proof
                    (folder/'body_sprite_verification.json').write_text(json.dumps(details))
                return JobResult(job.job_id,job.operation,'ok',details),folder
        patch('ucc.jobs.body_sprite_export.BlenderJobRunner',Runner).start()
        self.destination=plan_destination(self.root/'private-output',self.f.store.root)

    def invoke(self,**changes):
        options=dict(request=self.f.request,database_path=self.f.f.database,destination=self.destination,
            blender_exe=self.f.f.executable,worker_script=self.f.f.script,
            original_author_record=self.f.provenance.record_path,
            original_author_record_sha256=self.f.provenance.expected_sha256,
            original_motion_role=self.f.provenance.motion_role,
            original_motion_uri_aliases=self.f.provenance.uri_aliases)
        return export_body_sprite_sample(self.f.store,**(options|changes))

    def test_two_fresh_intakes_then_render_reopen_exact_pixels_and_exclusive_publication(self):
        original=self.f.store.file.read_bytes();result=self.invoke()
        self.assertEqual(len(self.f.calls),2);self.assertEqual(len(self.calls),2)
        self.assertEqual(result.selected_target_frames,(1,2));self.assertEqual(result.selected_source_frames,(2,3))
        self.assertEqual(result.image_count,8);self.assertTrue(self.destination.path.is_dir())
        self.assertEqual(self.f.store.file.read_bytes(),original)
        receipt=json.loads((self.destination.path/'body_sprite_receipt.json').read_text())
        self.assertFalse(receipt['material_adopted']);self.assertFalse(receipt['sprite_redistribution_authorized'])
        self.assertEqual(receipt['source_intake_job_ids'],[job.job_id for job in self.f.calls])
        self.assertFalse(any(path.suffix in ('.blend','.fbx') for path in self.destination.path.iterdir()))

    def test_source_permission_or_record_failure_precedes_every_native_boundary(self):
        with self.assertRaises(ProjectConflict):self.invoke(original_author_record_sha256='f'*64)
        self.assertEqual(self.f.calls,[]);self.assertEqual(self.calls,[]);self.assertFalse(self.destination.path.exists())

    def test_external_project_save_after_stage_preserves_external_revision_and_no_destination(self):
        def save():
            project=self.f.store.load()
            self.changed=self.f.store.save(replace(project,name='UNIT_EXTERNAL_SAVE',revision=project.revision+1),expected_revision=project.revision)
        self.after_stage=save
        with self.assertRaises(ProjectConflict):self.invoke()
        self.assertEqual(self.f.store.load(),self.changed);self.assertEqual(len(self.calls),1)
        self.assertFalse(self.destination.path.exists())

    def test_postpublish_journal_failure_withdraws_only_unchanged_new_output(self):
        actual=os.replace
        def fail(source,destination):
            if Path(source).name=='job_status.tmp' and 'PRIVATE_BODY_SPRITE_SAMPLE_PUBLISHED' in Path(source).read_text():
                raise OSError('UNIT_POSTPUBLISH_JOURNAL')
            return actual(source,destination)
        with patch('ucc.jobs.body_sprite_transactions.os.replace',side_effect=fail):
            with self.assertRaisesRegex(OSError,'UNIT_POSTPUBLISH_JOURNAL'):self.invoke()
        self.assertFalse(self.destination.path.exists())
        journal=next((self.f.store.root/'.ucc-jobs').glob('body-sprites-*/job_status.json'))
        self.assertEqual(json.loads(journal.read_text())['state'],'FAILED')

    def test_cancel_after_stage_prevents_verify_and_publication(self):
        cancel=threading.Event();self.after_stage=cancel.set
        original=self.f.store.file.read_bytes()
        with self.assertRaisesRegex(ProjectStorageError,'cancel'):
            self.invoke(cancel=cancel)
        self.assertEqual(len(self.f.calls),2);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.f.store.file.read_bytes(),original)
        self.assertFalse(self.destination.path.exists())
        journal=next((self.f.store.root/'.ucc-jobs').glob('body-sprites-*/job_status.json'))
        self.assertEqual(json.loads(journal.read_text())['state'],'FAILED')

    def test_publication_inside_registered_source_namespace_rejects_without_workers(self):
        invalid=plan_destination(self.f.store.root/'animations'/'not-an-export',self.f.store.root)
        with self.assertRaises(ValidationError):self.invoke(destination=invalid)
        self.assertEqual(self.f.calls,[]);self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
