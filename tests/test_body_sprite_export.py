"""API filesystem/pixel transactions; explicit doubles replace every native job."""
from dataclasses import replace
from pathlib import Path
import json
import os
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fixtures.body_sprite_sources import BodySourceFixture
from fixtures.body_sprite_images import image_evidence
from ucc.animations.target_action_diagnostic_contract import TargetActionDiagnosticSelection
from ucc.core.body_sprites import POLICY,STAGE
from ucc.core.target_action_format import canonical_bytes
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.jobs.authored_idle_loop_preview import AuthoredIdleReviewIdentity
from ucc.jobs.body_sprite_export import export_body_sprite_sample
from ucc.jobs.body_sprite_provenance import AuthoredIdleSpriteOrigin
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

    def authored_fixture(self):
        binding = replace(self.f.binding, root_motion_policy='ARMATURE_ORIGIN_DISPLACEMENT_V1')
        if self.f.directory.name != binding.sha256:
            (self.f.directory/'binding.json').write_bytes(canonical_bytes(binding.to_dict()))
            renamed = self.f.directory.with_name(binding.sha256)
            self.f.directory.rename(renamed)
            self.f.directory = renamed
        self.f.request = replace(self.f.request, target_binding=binding)
        source, target = binding.source, binding.target
        selection = TargetActionDiagnosticSelection(target.project_id,target.revision,target.project_sha256,
            target.master_sha256,source.clip_id,binding.sha256,source.source_binding_sha256,source.catalog_record_sha256)
        protected = self.root/'UNIT_OWNED_ORIGIN_SCOPE'
        protected.mkdir()
        proof = protected/'UNIT_PROOF_POINTER.json'
        proof.write_bytes(b'UNIT_NOT_AN_ADMITTED_REAL_PROOF')
        digest = _digest(proof)
        identity = AuthoredIdleReviewIdentity(selection,digest,'f'*64,binding.mapping_sha256,
                                               binding.file_map['playback/motion_skin.bin'].sha256)
        authority = SimpleNamespace(review_identity=identity, _protected_output_scopes=(protected,),
                                    assert_current=Mock())
        origin = AuthoredIdleSpriteOrigin(proof,authority)
        return origin,authority

    def invoke_authored(self, origin, **changes):
        return self.invoke(original_author_record=None,original_author_record_sha256=None,
            original_motion_role=None,original_motion_uri_aliases=(),authored_idle_proof=origin.record_path,
            **({'authored_idle_proof_sha256':origin.expected_sha256}|changes))

    def test_authored_idle_origin_is_readmitted_and_keeps_the_four_worker_and_pixel_route(self):
        origin, authority = self.authored_fixture()
        with patch(self.prefix+'review_authored_idle_sprite_origin',return_value=origin) as review:
            result = self.invoke_authored(origin)
        review.assert_called_once()
        self.assertEqual(review.call_args.kwargs['proof_file'],origin.record_path)
        self.assertEqual(review.call_args.kwargs['expected_proof_sha256'],origin.expected_sha256)
        self.assertEqual(review.call_args.kwargs['binding'],self.f.request.target_binding)
        self.assertEqual(len(self.f.calls),2)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(result.image_count,8)
        receipt = json.loads((self.destination.path/'body_sprite_receipt.json').read_bytes())
        metadata = receipt['source_admission']['original_motion_provenance']
        self.assertEqual(metadata['record_sha256'],origin.expected_sha256)
        self.assertEqual(metadata['record_format'],'AUTHORED_IDLE_PROOF_V1')
        self.assertFalse(metadata['sprite_rights_inferred'])
        self.assertNotIn(str(origin.record_path),str(metadata))
        self.assertGreater(authority.assert_current.call_count,4)

    def test_authored_idle_origin_revoked_between_stages_stops_before_publication(self):
        origin, authority = self.authored_fixture()
        self.after_stage = lambda: setattr(authority.assert_current,'side_effect',ProjectStorageError('Unit stale origin'))
        with patch(self.prefix+'review_authored_idle_sprite_origin',return_value=origin):
            with self.assertRaisesRegex(ProjectStorageError,'Unit stale origin'):
                self.invoke_authored(origin)
        self.assertEqual(len(self.f.calls),2)
        self.assertEqual(len(self.calls),1)
        self.assertFalse(self.destination.path.exists())

    def test_authored_idle_output_must_be_disjoint_and_proof_options_are_exclusive(self):
        origin, _ = self.authored_fixture()
        inside = plan_destination(origin.record_path.parent/'UNIT_OUTPUT',self.f.store.root)
        with patch(self.prefix+'review_authored_idle_sprite_origin',return_value=origin) as review:
            with self.assertRaises(ValidationError):
                self.invoke(authored_idle_proof=origin.record_path,authored_idle_proof_sha256=origin.expected_sha256)
            with self.assertRaises(ValidationError):
                self.invoke_authored(origin,authored_idle_proof_sha256=None)
            review.assert_not_called()
            with self.assertRaisesRegex(ValidationError,'outside the authored idle proof closure'):
                self.invoke_authored(origin,destination=inside)
        self.assertEqual(self.f.calls,[])
        self.assertEqual(self.calls,[])
        self.assertFalse(inside.path.exists())

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
