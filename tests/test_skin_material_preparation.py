"""Real filesystem candidate transactions with explicitly synthetic worker doubles."""
from contextlib import ExitStack
from pathlib import Path
from threading import Event
import tempfile,time,unittest
from unittest.mock import patch
from fixtures.skin_material_logic import MaterialFixture
from ucc.jobs.skin_material_preparation import prepare_skin_material_revision
from ucc.core.errors import ProjectStorageError,ProjectConflict,ValidationError
from ucc.jobs.runner import WorkerFailure


class MaterialPreparationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.f=MaterialFixture(Path(temporary.name).resolve())
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch('ucc.jobs.skin_material_preparation.project_sources',return_value=self.f.sources))
        self.admission=stack.enter_context(patch('ucc.jobs.skin_material_preparation.verify_saved_expression_master'))
        stack.enter_context(patch('ucc.jobs.skin_material_preparation.BlenderJobRunner.run',side_effect=self.f.run))
        stack.enter_context(patch('ucc.jobs.skin_material_preparation.verify_material_glb',return_value={'UNIT_ONLY_NOT_PBR':True}))

    def run_material(self,**changes):return prepare_skin_material_revision(self.f.store,**{**self.f.kwargs(),**changes})

    def preserved(self):
        self.assertEqual(self.f.store.file.read_bytes(),self.f.original_metadata)
        self.assertEqual(self.f.master.read_bytes(),b'BLENDER_UNIT_NOT_A_REAL_MODEL_SOURCE')

    def test_atomic_retention_has_two_fresh_jobs_and_never_changes_project_pointer(self):
        result=self.run_material();self.preserved();self.assertFalse(result.project_pointer_changed)
        self.assertEqual(self.f.calls,['stage_mpfb_skin_material','verify_mpfb_skin_material'])
        self.assertTrue((result.directory/'material_human.blend').is_file());self.assertTrue((result.directory/'.gdignore').is_file())
        self.assertNotEqual(result.material_master_sha256,result.source_master_sha256)

    def test_stale_precancel_and_invalid_deadlines_stop_before_workers(self):
        with self.assertRaises(ProjectConflict):self.run_material(expected_revision=999)
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.run_material(cancel=cancel)
        for value in (True,float('nan'),-.1,3601):
            with self.assertRaises(ValidationError):self.run_material(timeout_s=value)
        self.assertEqual(self.f.calls,[]);self.preserved()

    def test_changed_registered_input_rejects_without_a_new_candidate(self):
        def changed(operation,folder):
            if operation=='stage_mpfb_skin_material':self.f.hand.write_bytes(b'UNIT_CHANGED_NOAI_SOURCE')
        self.f.callback=changed
        with self.assertRaises(ProjectStorageError):self.run_material()
        self.preserved();self.assertEqual(len(self.f.calls),1)
        self.assertFalse(list((self.f.store.root/'.ucc-candidates').glob('skin-material/*')))

    def test_cancel_after_realistic_stage_does_not_publish(self):
        cancel=Event();self.f.callback=lambda operation,folder:cancel.set()
        with self.assertRaises(ProjectStorageError):self.run_material(cancel=cancel)
        self.preserved();self.assertEqual(len(self.f.calls),1)

    def test_one_total_deadline_covers_existing_source_admission(self):
        self.admission.side_effect=lambda *args,**kwargs:time.sleep(1.1)
        with self.assertRaises(WorkerFailure):self.run_material(timeout_s=1.)
        self.admission.assert_called_once()
        self.preserved();self.assertEqual(self.f.calls,[])

    def test_final_journal_failure_rolls_retained_candidate_back_into_private_job(self):
        import os
        real=os.replace
        def replace(source,destination):
            if b'PRIVATE_MATERIAL_REVISION_PREPARED' in Path(source).read_bytes():raise OSError('UNIT_FINAL_JOURNAL_FAILURE')
            return real(source,destination)
        with patch('ucc.jobs.skin_material_preparation.os.replace',side_effect=replace):
            with self.assertRaisesRegex(OSError,'UNIT_FINAL_JOURNAL_FAILURE'):self.run_material()
        self.preserved();self.assertFalse(list((self.f.store.root/'.ucc-candidates/skin-material').glob('*')))
        self.assertTrue(list((self.f.store.root/'.ucc-jobs').glob('skin-material-*/retained/material_human.blend')))


if __name__=='__main__':unittest.main()
