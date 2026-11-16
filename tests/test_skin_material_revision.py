"""Synthetic transaction guards only; real Blender/engine evidence stays private."""
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
import json,tempfile,unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from fixtures.reference_master_contract import ReferenceMasterFixture
from fixtures.skin_material_logic import MaterialFixture
from ucc.core.errors import ProjectStorageError,ProjectConflict,ValidationError
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.expression_library import canonical_digest
from ucc.core.skin_material import SkinMaterialSpec,material_recipe,canonical_bytes,APPEARANCE_KEY
from ucc.jobs.godot_candidate_inputs import project_sources
from ucc.jobs.expression_inspection import CheckedExpressionMaster
from ucc.jobs.hand_storage import load_hand_library
from ucc.jobs.hand_revision import HandRevisionResult
from ucc.jobs.protocol import JobRequest
from ucc.jobs.skin_material_preparation import PreparedSkinMaterialRevision
from ucc.jobs.skin_material_revision import apply_skin_material_revision,revise_material_bound_master,MaterialMasterNoOp
from ucc.jobs.expression_revisions import publish_expression_receipt
from ucc.jobs.expression_storage import load_expression_library
from ucc.core.master_versions import stage_unverified_master
from ucc.jobs.skin_material_storage import registered_material_binding
from ucc.jobs.runner import WorkerFailure

MODULE='ucc.jobs.skin_material_revision.'
digest=lambda p:sha256(p.read_bytes()).hexdigest()


class SkinMaterialRevisionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.f=ReferenceMasterFixture(self.root);current=self.f.store.load()
        self.initial=self.f.store.save(replace(current,animations=(),appearance=(('existing','retained'),),revision=current.revision+1),expected_revision=current.revision)
        self.before=self.f.store.file.read_bytes();self.history=self.f.store.list_backups()
        fixture_root=self.root/'material-double';fixture_root.mkdir();self.m=MaterialFixture(fixture_root)
        (self.m.store.root/'.ucc-jobs').mkdir();self.spec=self.m.spec
        stack=ExitStack();self.addCleanup(stack.close)
        self.prepare=stack.enter_context(patch(MODULE+'prepare_skin_material_revision',side_effect=self.fake_material))
        stack.enter_context(patch(MODULE+'verify_saved_expression_master'))
        stack.enter_context(patch(MODULE+'inspect_saved_neutral_master'))
        stack.enter_context(patch(MODULE+'_inspect_expression_copy',side_effect=self.fake_inspect))
        stack.enter_context(patch(MODULE+'build_hand_library',side_effect=lambda private,**kw:SimpleNamespace(library=self.f.library(private),observed={'UNIT_NOT_GEOMETRY':True})))
        stack.enter_context(patch(MODULE+'apply_hand_revision',side_effect=self.fake_hand))
        for name in ('installed_expression_inputs','installed_inputs'):stack.enter_context(patch(MODULE+name,return_value={}))

    def fake_material(self,private,**kw):
        current=private.load();sources=project_sources(private,current,None)
        recipe=material_recipe(current,digest(private.file),{k:digest(p) for k,p in sources.items()},self.spec)
        recipe_path=private.root/'UNIT-material-recipe.json';recipe_path.write_bytes(canonical_bytes(recipe))
        options={'master_sha256':digest(sources['master']),'recipe_sha256':digest(recipe_path)}
        stage_job=JobRequest.new('stage_mpfb_skin_material',input_project='candidate.blend',options=options)
        _,stage=self.m.run(stage_job,staged_inputs={'candidate.blend':sources['master'],'material_recipe.json':recipe_path})
        path=stage/'material_human.blend';path.write_bytes((path.read_bytes()+options['master_sha256'].encode())*100)
        report=json.loads((stage/'material_stage.json').read_text());report['material_master_sha256']=digest(path)
        (stage/'material_stage.json').write_bytes(canonical_bytes(report))
        options.update(material_master_sha256=digest(stage/'material_human.blend'),glb_sha256=digest(stage/'character.glb'),stage_report_sha256=digest(stage/'material_stage.json'))
        verify_job=JobRequest.new('verify_mpfb_skin_material',input_project='candidate.blend',options=options)
        _,fresh=self.m.run(verify_job,staged_inputs={name:stage/name for name in ('candidate.blend','material_recipe.json','material_human.blend','character.glb','material_stage.json')})
        return PreparedSkinMaterialRevision(fresh,options['master_sha256'],options['material_master_sha256'],self.spec.sha256,digest(fresh/'material_verification.json'),stage_job.job_id,verify_job.job_id)

    def fake_inspect(self,private,*,master_blend,**kw):
        master=private.root/master_blend;sha=digest(master)
        observed={'schema_version':1,'policy':build_expression_recipe(sha)['policy'],'master_sha256':sha,
            'recipe_sha256':canonical_digest(build_expression_recipe(sha)),'sample_count':20,'observation':{'UNIT_NOT_BLENDER':True},
            'expression_keys_sha256':'e'*64,'exact_neutral_restoration':True,'visual_quality_approved':False,'engine_import_verified':False}
        report=private.root/'UNIT-inspection.json';report.write_text(json.dumps(observed))
        return CheckedExpressionMaster(master,sha,observed,report,digest(report),'UNIT-stage','UNIT-reopen')

    def fake_hand(self,private,*,manifest_sha256,selection,**kw):
        library=load_hand_library(private,manifest_sha256);revision=self.f.select(private,library,selection)
        return HandRevisionResult(revision.project,revision,manifest_sha256,{'UNIT_NOT_BLENDER':True},'UNIT-stage','UNIT-reopen')

    def run_revision(self,**changes):
        p=self.initial
        return apply_skin_material_revision(self.f.store,spec=self.spec,blender_exe=self.m.exe,worker_script=self.m.worker,mpfb_data_dir=self.m.data,
            **{**dict(expected_project_id=p.project_id,expected_revision=p.revision,expected_master_blend=p.master_blend),**changes})

    def preserved(self):
        self.assertEqual(self.f.store.file.read_bytes(),self.before);self.assertEqual(self.f.store.list_backups(),self.history)

    def test_atomic_publication_preserves_expression_hand_instance_and_other_appearance(self):
        result=self.run_revision();saved=self.f.store.load()
        self.assertEqual(saved.revision,self.initial.revision+1);self.assertEqual(saved.expression,self.initial.expression)
        self.assertEqual(saved.parts[0].part_id,self.initial.parts[0].part_id)
        self.assertTrue(saved.parts[0].part_asset_id.endswith('-shorter'));self.assertNotEqual(saved.parts[0].part_asset_id,self.initial.parts[0].part_asset_id)
        record=registered_material_binding(self.f.store,saved)
        self.assertEqual(record['spec'],self.spec.to_dict());self.assertEqual(record['hand_manifest_sha256'],result.hand_manifest_sha256)
        self.assertEqual(dict(saved.appearance)[APPEARANCE_KEY],result.binding_sha256)
        self.assertEqual(dict(saved.appearance)['existing'],'retained')
        self.assertEqual(len(self.f.store.list_backups()),len(self.history)+1)

    def test_commit_failure_leaves_old_metadata_and_history_authoritative(self):
        original=self.f.store.save
        def fail(project,**kw):
            if APPEARANCE_KEY in dict(project.appearance):raise OSError('UNIT final metadata failure')
            return original(project,**kw)
        with patch.object(self.f.store,'save',side_effect=fail),self.assertRaisesRegex(OSError,'final metadata'):
            self.run_revision()
        self.preserved()

    def test_rebuilt_hand_failure_does_not_publish_material_master(self):
        with patch(MODULE+'build_hand_library',side_effect=ProjectStorageError('UNIT hand failed')),self.assertRaisesRegex(ProjectStorageError,'hand failed'):
            self.run_revision()
        self.preserved()

    def test_stale_cancel_invalid_timeout_and_source_references_stop_early(self):
        with self.assertRaises(ProjectConflict):self.run_revision(expected_revision=999)
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.run_revision(cancel=cancel)
        with self.assertRaises(ValidationError):self.run_revision(timeout_s=True)
        current=self.f.store.load();self.f.store.save(replace(current,animations=(self.f.clip_id,),revision=current.revision+1),expected_revision=current.revision)
        self.initial=self.f.store.load()
        with self.assertRaisesRegex(ValidationError,'source-animation'):self.run_revision()
        self.prepare.assert_not_called()

    def test_tampered_appearance_binding_cannot_admit_another_master_or_spec(self):
        self.run_revision();saved=self.f.store.load()
        with self.assertRaises(ProjectStorageError):registered_material_binding(self.f.store,replace(saved,master_blend=self.initial.master_blend))
        wrong=replace(saved.parts[0],part_asset_id=saved.parts[0].part_asset_id.rsplit('-',1)[0]+'-longer')
        with self.assertRaises(ProjectStorageError):registered_material_binding(self.f.store,replace(saved,parts=(wrong,)))
        identity=dict(saved.appearance)[APPEARANCE_KEY];path=self.f.store.root/'materials/manifests'/(identity+'.json')
        raw=json.loads(path.read_text());raw['spec']['roughness']=.15;path.write_bytes(canonical_bytes(raw))
        with self.assertRaises(ProjectStorageError):registered_material_binding(self.f.store,saved)

    def test_body_and_face_edits_explicitly_reject_until_material_preservation_is_verified(self):
        from ucc.jobs.humanoid_generation import generate_humanoid
        from ucc.jobs.body_revision import apply_saved_body_revision
        from ucc.jobs.face_revision import apply_saved_face_revision
        self.run_revision();saved=self.f.store.load();before=self.f.store.file.read_bytes()
        common=dict(blender_exe=self.m.exe,worker_script=self.m.worker,expected_project_id=saved.project_id,expected_revision=saved.revision)
        for function,kwargs in [(generate_humanoid,{}),(apply_saved_body_revision,{'expected_master_blend':saved.master_blend}),
                (apply_saved_face_revision,{'expected_master_blend':saved.master_blend,'mpfb_data_dir':self.m.data})]:
            with self.subTest(function=function.__name__),self.assertRaisesRegex(ValidationError,'material preservation'):
                function(self.f.store,**common,**kwargs)
        self.assertEqual(self.f.store.file.read_bytes(),before)

    def test_source_mutation_after_material_workers_blocks_publication(self):
        prepare=self.fake_material
        original=self.f.store.root/self.initial.master_blend
        def mutate(private,**kwargs):
            result=prepare(private,**kwargs);original.write_bytes(original.read_bytes()+b'UNIT concurrent source mutation')
            return result
        self.prepare.side_effect=mutate
        with self.assertRaises(ProjectStorageError):self.run_revision()
        self.preserved()

    def fake_body_edit(self,private,*,operation,**kwargs):
        current=private.load();source_sha=Path(current.master_blend).stem
        output=private.root/'UNIT-BODY-NOT-GEOMETRY.blend'
        output.write_bytes(b'BLENDER'+(operation+source_sha+str(current.parameters)+str(current.facial_parameters)).encode()*30)
        sha=digest(output);relative='master/versions/'+sha+'.blend'
        from ucc.jobs.expression_storage import install_master_copy
        install_master_copy(private,output,sha,private.root)
        checked=self.fake_inspect(private,master_blend=relative)
        library=load_expression_library(private,current.expression.library_sha256)
        publish_expression_receipt(private,library,source_sha,checked,operation)
        revision=stage_unverified_master(private,output,authorized_source_root=private.root,expected_project=current,expected_revision=current.revision)
        return SimpleNamespace(revision=revision,observed={'UNIT_ONLY_NOT_GEOMETRY':operation})

    def run_body_edit(self,operation='body_refit',**changes):
        p=self.initial
        return revise_material_bound_master(self.f.store,operation=operation,blender_exe=self.m.exe,worker_script=self.m.worker,mpfb_data_dir=self.m.data,
            **{**dict(expected_project_id=p.project_id,expected_revision=p.revision,expected_master_blend=p.master_blend),**changes})

    def published_material(self):
        self.run_revision();self.initial=self.f.store.load()
        return registered_material_binding(self.f.store,self.initial)

    def test_material_body_edit_replays_old_physical_intent_and_applies_pending_dimensions(self):
        old=self.published_material();current=self.initial
        self.initial=self.f.store.save(replace(current,parameters=(('height',.66),('muscle',.5),('weight',.5)),revision=current.revision+1),expected_revision=current.revision)
        self.before=self.f.store.file.read_bytes();self.history=self.f.store.list_backups()
        with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=self.fake_body_edit) as edit:
            result=self.run_body_edit()
        saved=self.f.store.load();binding=registered_material_binding(self.f.store,saved)
        self.assertEqual(saved.parameters,self.initial.parameters);self.assertEqual(binding['spec'],old['spec'])
        self.assertEqual(saved.expression,self.initial.expression);self.assertEqual(saved.parts[0].part_id,self.initial.parts[0].part_id)
        self.assertNotEqual(saved.parts[0].part_asset_id,self.initial.parts[0].part_asset_id)
        self.assertEqual(saved.revision,self.initial.revision+1);self.assertTrue(result.observed['material_parameters_preserved'])
        self.assertEqual(edit.call_args.kwargs['operation'],'body_refit')

    def test_generation_and_face_revision_keep_chosen_material_and_publish_two_ancestry_steps(self):
        old=self.published_material()
        for operation in ('body_generation','face_revision'):
            current=self.f.store.load();self.initial=current
            with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=self.fake_body_edit):result=self.run_body_edit(operation)
            saved=self.f.store.load();binding=registered_material_binding(self.f.store,saved)
            self.assertEqual(binding['spec'],old['spec']);self.assertEqual(saved.revision,current.revision+1)
            self.assertEqual(result.observed['operation'],operation)
            self.assertTrue((self.f.store.root/'expressions/revisions'/(result.observed['body_master_sha256']+'.json')).is_file())

    def test_verified_material_face_noop_leaves_pointer_and_history_unchanged(self):
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups()
        with patch('ucc.jobs.expression_mutation.preserve_expressions',return_value=SimpleNamespace(revision=None)):
            result=self.run_body_edit('face_revision')
        self.assertIsInstance(result,MaterialMasterNoOp);self.assertTrue(result.observed['verified_noop'])
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)

    def test_material_body_edit_failure_and_final_commit_failure_keep_original_graph(self):
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups()
        with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=ProjectStorageError('UNIT body failed')),self.assertRaisesRegex(ProjectStorageError,'body failed'):
            self.run_body_edit()
        self.assertEqual(self.f.store.file.read_bytes(),before)
        actual_save=self.f.store.save
        def fail(project,**kw):
            if project.master_blend!=self.initial.master_blend:raise OSError('UNIT final body material commit failed')
            return actual_save(project,**kw)
        with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=self.fake_body_edit),patch.object(self.f.store,'save',side_effect=fail),self.assertRaisesRegex(OSError,'final body material'):
            self.run_body_edit()
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)

    def test_cancel_after_private_body_edit_prevents_material_phase_and_outer_commit(self):
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups();cancel=Event()
        def stop(private,**kwargs):
            result=self.fake_body_edit(private,**kwargs);cancel.set();return result
        with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=stop),self.assertRaisesRegex(ProjectStorageError,'cancel'):
            self.run_body_edit(cancel=cancel)
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)

    def test_total_deadline_expiring_after_body_edit_blocks_the_next_phase(self):
        import time
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups()
        actual=time.monotonic;advance=[0.]
        def expire(private,**kwargs):
            result=self.fake_body_edit(private,**kwargs);advance[0]=4000.;return result
        with patch('ucc.jobs.skin_material_revision.time.monotonic',side_effect=lambda:actual()+advance[0]),\
                patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=expire),\
                self.assertRaisesRegex((WorkerFailure,ProjectStorageError),'deadline|cancel'):
            self.run_body_edit(timeout_s=3600)
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)

    def test_concurrent_outer_metadata_save_is_preserved_and_prevents_body_publication(self):
        self.published_material();saved_by_user=[]
        def concurrent(private,**kwargs):
            result=self.fake_body_edit(private,**kwargs);current=self.f.store.load()
            saved_by_user.append(self.f.store.save(replace(current,name='UNIT concurrent user edit',revision=current.revision+1),expected_revision=current.revision))
            return result
        with patch('ucc.jobs.expression_mutation.preserve_expressions',side_effect=concurrent),self.assertRaises(ProjectConflict):
            self.run_body_edit()
        self.assertEqual(self.f.store.load(),saved_by_user[0]);self.assertEqual(saved_by_user[0].master_blend,self.initial.master_blend)

    def test_same_spec_rechecks_saved_source_without_rebuilding_or_publishing(self):
        import shutil
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups();self.prepare.reset_mock()
        folder=self.f.root/'UNIT-noop-not-integration';folder.mkdir()
        (folder/'material_stage.json').write_bytes(canonical_bytes({'changed':False,'UNIT_NOT_BPY':True}))
        (folder/'material_verification.json').write_bytes(canonical_bytes({'UNIT_NOT_BPY':True}))
        source=self.f.store.root/self.initial.master_blend;shutil.copy2(source,folder/'material_human.blend')
        prepared=PreparedSkinMaterialRevision(folder,digest(source),digest(source),self.spec.sha256,digest(folder/'material_verification.json'),'UNIT-stage','UNIT-reopen')
        self.prepare.side_effect=None;self.prepare.return_value=prepared
        result=self.run_revision()
        self.assertIsInstance(result,MaterialMasterNoOp);self.prepare.assert_called_once()
        self.assertTrue(result.observed['fresh_owned_shader_verified'])
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)
        self.prepare.side_effect=WorkerFailure('UNIT actual saved source mismatch')
        with self.assertRaises(WorkerFailure):
            self.run_revision()
        self.assertEqual(self.f.store.file.read_bytes(),before)

    def test_same_spec_does_not_publish_a_private_material_repair(self):
        self.published_material();before=self.f.store.file.read_bytes();history=self.f.store.list_backups()
        # The ordinary synthetic material producer deliberately makes a different
        # candidate. That is a repair/revision, never an unchanged source proof.
        with self.assertRaisesRegex(ProjectStorageError,'cannot repair'):self.run_revision()
        self.assertEqual(self.f.store.file.read_bytes(),before);self.assertEqual(self.f.store.list_backups(),history)


if __name__=='__main__':unittest.main()
