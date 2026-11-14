"""Metadata/transaction guards only; these do not prove Blender deformation."""
from dataclasses import replace
import copy
import json
from pathlib import Path
from threading import Event
import tempfile
import unittest

from ucc.core.commands import CharacterSession
from ucc.core.errors import CompatibilityError, ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expressions import (DEFAULTS, TARGETS, ExpressionState,
                                  validate_expression_parameters, validate_expression_part_rebind)
from ucc.core.hand_parts import hand_asset_id
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.storage import ProjectStore


def source_project(*, hand=False, face=False):
    return replace(CharacterProject.new('Expression contract only'),
                   master_blend='master/versions/'+('a'*64)+'.blend', geometry_state='generated_unverified',
                   schema_version=2 if face else 1, facial_parameters=(('nose_width', .25),) if face else (),
                   parts=(PartInstance('hand-instance', hand_asset_id('b'*64, 'shorter'), 'hand.L'),) if hand else ())


def prepared(project, *, hand=False):
    parts=(replace(project.parts[0], part_asset_id=hand_asset_id('c'*64, 'shorter')),) if hand else ()
    return replace(project, schema_version=3, expression=ExpressionState('d'*64), parts=parts,
                   master_blend='master/versions/'+('e'*64)+'.blend', revision=project.revision+1)


class ExpressionIntentTests(unittest.TestCase):
    def test_legacy_serialization_stays_legacy_until_actual_preparation(self):
        for face in (False, True):
            old=source_project(face=face);raw=old.to_dict()
            self.assertNotIn('expression',raw)
            self.assertEqual(CharacterProject.from_dict(raw),old)
            self.assertEqual(CharacterSession(old).set_face_parameter('nose_width',.75).schema_version,2)
            with self.assertRaises(CompatibilityError):CharacterSession(old).set_expression_parameter('mouth_open',.25)
            self.assertNotIn('expression',old.to_dict())

    def test_prepared_v3_roundtrips_and_static_face_edit_preserves_it(self):
        project=prepared(source_project(face=True));raw=project.to_dict()
        self.assertEqual(raw['schema_version'],3)
        self.assertEqual(raw['expression']['parameters'],DEFAULTS)
        self.assertEqual(CharacterProject.from_dict(raw),project)
        changed=CharacterSession(project).set_face_parameter('nose_width',.75)
        self.assertEqual(changed.schema_version,3);self.assertEqual(changed.expression,project.expression)
        self.assertEqual(changed.master_blend,project.master_blend)

    def test_closed_v3_requires_real_preparation_reference_and_saved_master(self):
        legacy=source_project().to_dict()
        for raw in (dict(legacy,expression=ExpressionState('d'*64).to_dict()),
                    dict(legacy,schema_version=3),dict(legacy,schema_version=True)):
            with self.subTest(raw=raw),self.assertRaises(ValidationError):CharacterProject.from_dict(raw)
        ready=prepared(source_project()).to_dict()
        for name in ('expression','facial_parameters'):
            broken=dict(ready);del broken[name]
            with self.assertRaises(ValidationError):CharacterProject.from_dict(broken)
        for raw in (dict(ready,expression=None),dict(ready,expression={}),dict(ready,extra=True)):
            with self.assertRaises(ValidationError):CharacterProject.from_dict(raw)
        with self.assertRaises(ValidationError):replace(CharacterProject.new('No master'),schema_version=3,expression=ExpressionState('d'*64))

    def test_strengths_are_closed_finite_bounded_and_not_booleans(self):
        for value in (-.001,.500001,float('nan'),float('inf'),10**1000,True,'0.25'):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                validate_expression_parameters({'mouth_open':value},partial=True)
        for raw in ({}, {'mouth_open':.25},dict(DEFAULTS,unknown=.2)):
            with self.assertRaises(ValidationError):validate_expression_parameters(raw)
        for identity in ('D'*64,'../library','a'*63,True,None):
            with self.assertRaises(ValidationError):ExpressionState(identity)
        for raw in ({'library_sha256':'d'*64,'parameters':DEFAULTS,'extra':True},
                    {'library_sha256':'d'*64}):
            with self.assertRaises(ValidationError):ExpressionState.from_dict(raw)
        with self.assertRaises(ValidationError):ExpressionState('d'*64,(('mouth_open',0.),('mouth_open',.1)))

    def test_saved_strength_history_and_reset_never_change_neutral_master_or_parts(self):
        project=prepared(source_project(hand=True),hand=True);session=CharacterSession(project)
        changed=session.set_expression_parameter('mouth_open',.375)
        self.assertEqual(changed.master_blend,project.master_blend);self.assertEqual(changed.parts,project.parts)
        self.assertEqual(changed.expression.library_sha256,project.expression.library_sha256)
        self.assertFalse(changed.expression.neutral)
        self.assertEqual(session.undo().expression,project.expression)
        self.assertEqual(session.redo().expression,changed.expression)
        reset=session.reset_expression();self.assertTrue(reset.expression.neutral)
        self.assertEqual(session.reset_expression(),reset)
        self.assertEqual(reset.master_blend,project.master_blend)

    def test_preparation_adopts_rebound_hand_and_master_in_one_history_step(self):
        for hand in (False,True):
            old=source_project(hand=hand,face=True);new=prepared(old,hand=hand);session=CharacterSession(old)
            with self.assertRaises(ValidationError):session.accept_saved_master(new)
            self.assertFalse(session.can_undo)
            self.assertEqual(session.accept_saved_expression_master(new,library_sha256='d'*64),new)
            restored=session.undo()
            self.assertEqual(restored.master_blend,old.master_blend);self.assertEqual(restored.parts,old.parts)
            self.assertEqual(restored.schema_version,old.schema_version);self.assertIsNone(restored.expression)
            self.assertFalse(session.can_undo)
            self.assertEqual(session.redo().expression,new.expression)

    def test_preparation_rejects_unrelated_intent_changes_and_fake_readiness(self):
        old=source_project();new=prepared(old)
        for broken in (replace(new,name='Other'),replace(new,parameters=(('height',.8),)),
                       replace(new,revision=old.revision+2),replace(new,master_blend=old.master_blend),
                       replace(new,expression=ExpressionState('d'*64,tuple(dict(DEFAULTS,mouth_open=.25).items())))):
            session=CharacterSession(old)
            with self.assertRaises(ValidationError):session.accept_saved_expression_master(broken,library_sha256='d'*64)
            self.assertEqual(session.project,old);self.assertFalse(session.can_undo)
        with self.assertRaises(ValidationError):CharacterSession(old).accept_saved_expression_master(new,library_sha256='f'*64)

    def test_selected_hands_require_new_library_same_variant_and_instance(self):
        old=source_project(hand=True);new=prepared(old,hand=True)
        variants=[old.parts,(),(replace(new.parts[0],part_id='different'),),
                  (replace(new.parts[0],part_asset_id=hand_asset_id('c'*64,'longer')),),
                  (replace(new.parts[0],visible=False),),(replace(new.parts[0],slot='hand.R'),)]
        for parts in variants:
            with self.subTest(parts=parts),self.assertRaises(CompatibilityError):
                validate_expression_part_rebind(old.parts,parts)
        with self.assertRaises(CompatibilityError):validate_expression_part_rebind((),new.parts)
        validate_expression_part_rebind(old.parts,new.parts)

    def test_twelve_pinned_targets_have_unique_staging_and_owned_names(self):
        self.assertEqual(len(TARGETS),12)
        self.assertEqual(len({t.staged_name for t in TARGETS}),12)
        self.assertEqual(len({t.key_name for t in TARGETS}),12)
        self.assertTrue(all(len(t.key_name)<=61 and t.source_relative.startswith('targets/expression/units/') for t in TARGETS))

    def test_schema_v3_is_closed_and_does_not_accept_a_partial_state(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional jsonschema unavailable')
        path=Path(__file__).resolve().parents[1]/'docs/schemas/character-project.v3.schema.json'
        schema=json.loads(path.read_text());Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
        raw=prepared(source_project()).to_dict();validator.validate(raw)
        for edit in (lambda r:r['expression'].update(extra=True),lambda r:r['expression']['parameters'].pop('mouth_open'),
                     lambda r:r['expression']['parameters'].update(mouth_open=True),
                     lambda r:r['expression']['parameters'].update(mouth_open=.501),
                     lambda r:r.update(master_blend=None)):
            broken=copy.deepcopy(raw);edit(broken);self.assertTrue(list(validator.iter_errors(broken)))


class ExpressionPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.store=ProjectStore(self.root/'project');self.store.save(CharacterProject.new('Structural transaction only'))
        self.worker=self.root/'worker';self.worker.mkdir();self.source=self.worker/'source.blend'
        self.source.write_bytes(b'BLENDER'+b'synthetic-structural-fixture-not-a-real-scene'*4)
        self.initial=stage_unverified_master(self.store,self.source,authorized_source_root=self.worker).project
        self.result=self.worker/'prepared.blend';self.result.write_bytes(b'BLENDER'+b'different-structural-fixture-not-expression-proof'*4)

    def publish(self,**kwargs):
        return stage_unverified_master(self.store,self.result,authorized_source_root=self.worker,
                                       expected_project=self.initial,proposed_expression=ExpressionState('d'*64),**kwargs)

    def test_preparation_fields_and_pointer_commit_once(self):
        result=self.publish();saved=self.store.load()
        self.assertEqual(saved,result.project);self.assertEqual(saved.revision,self.initial.revision+1)
        self.assertEqual(saved.schema_version,3);self.assertTrue(saved.expression.neutral)
        self.assertNotEqual(saved.master_blend,self.initial.master_blend)
        self.assertEqual((self.store.root/self.initial.master_blend).read_bytes(),self.source.read_bytes())

    def test_failure_cancel_and_same_bytes_preserve_old_version(self):
        before=self.store.file.read_bytes()
        def failed():raise RuntimeError('before single atomic metadata commit')
        with self.assertRaises(RuntimeError):self.publish(before_project_save=failed)
        self.assertEqual(self.store.file.read_bytes(),before)
        cancel=Event();cancel.set()
        with self.assertRaises(ProjectStorageError):self.publish(cancel=cancel)
        self.result.write_bytes(self.source.read_bytes())
        with self.assertRaises(ProjectStorageError):self.publish()
        self.assertEqual(self.store.file.read_bytes(),before)

    def test_full_snapshot_conflict_even_without_external_revision_increment(self):
        raw=json.loads(self.store.file.read_text());raw['name']='external retained';self.store.file.write_text(json.dumps(raw))
        with self.assertRaises(ProjectConflict):self.publish()
        self.assertEqual(self.store.load().name,'external retained')

    def test_hand_registration_cannot_be_kept_unchanged_when_master_gets_keys(self):
        p=replace(self.initial,parts=source_project(hand=True).parts,revision=self.initial.revision+1)
        self.initial=self.store.save(p,expected_revision=self.initial.revision)
        before=self.store.file.read_bytes()
        with self.assertRaises(CompatibilityError):self.publish()
        self.assertEqual(self.store.file.read_bytes(),before)
        rebind=(replace(p.parts[0],part_asset_id=hand_asset_id('c'*64,'shorter')),)
        result=self.publish(proposed_parts=rebind)
        self.assertEqual(result.project.parts,rebind);self.assertEqual(result.project.schema_version,3)

    def test_body_only_entrypoints_cannot_silently_discard_prepared_keys(self):
        from ucc.jobs.humanoid_generation import generate_humanoid
        from ucc.jobs.body_revision import apply_saved_body_revision
        from ucc.jobs.customized_humanoid import generate_customized_humanoid
        project=self.publish().project;before=self.store.file.read_bytes()
        common={'blender_exe':Path('not-used.exe'),'worker_script':Path('not-used.py'),
                'expected_project_id':project.project_id,'expected_revision':project.revision}
        for method,extras in ((generate_humanoid,{}),
                (apply_saved_body_revision,{'expected_master_blend':project.master_blend}),
                (generate_customized_humanoid,{'mpfb_data_dir':Path('not-used-data')})):
            with self.subTest(method=method.__name__),self.assertRaisesRegex(ValidationError,'expression-aware'):
                method(self.store,**common,**extras)
            self.assertEqual(self.store.file.read_bytes(),before)
        self.assertFalse((self.store.root/'.ucc-jobs').exists())
