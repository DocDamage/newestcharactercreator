"""Facial intent/schema/migration tests only; no simulated Blender success."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from ucc.core.commands import CharacterSession
from ucc.core.errors import CompatibilityError, ProjectStorageError, ValidationError
from ucc.core.facial import build_face_recipe, nose_weights, validate_face_parameters, validate_face_recipe
from ucc.core.models import CharacterProject, PartInstance
from ucc.core.storage import ProjectStore


class FaceRecipeTests(unittest.TestCase):
    def test_bounded_narrow_neutral_and_wide(self):
        for value, expected in [(0., (.5, 0.)), (.5, (0., 0.)), (1., (0., .5))]:
            with self.subTest(value=value):
                self.assertEqual(nose_weights(value), expected)
                recipe = build_face_recipe('a'*64, {'nose_width': value})
                self.assertEqual(tuple(t['weight'] for t in recipe['targets']), expected)
                self.assertEqual(validate_face_recipe(json.loads(json.dumps(recipe))), recipe)
        self.assertAlmostEqual(nose_weights(.8)[1], .3)

    def test_invalid_or_inferred_intent_rejected(self):
        for value in (True, False, None, '0.5', float('nan'), float('inf'), -.01, 1.01, 10**1000):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValidationError):
                nose_weights(value)
        for raw in ({}, {'nose_width': .5, 'jaw': .1}, {'nose': .2}, [], None):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                build_face_recipe('a'*64, raw)
        self.assertEqual(validate_face_parameters({}), {})

    def test_recipe_cannot_substitute_data_paths_hashes_or_controls(self):
        source = build_face_recipe('a'*64, {'nose_width': .8})
        mutations = [
            lambda r: r.update(schema_version=True),
            lambda r: r.update(schema_version=2),
            lambda r: r.update(extra='unknown'),
            lambda r: r.update(family='dragon.v1'),
            lambda r: r.update(mpfb_version='unverified'),
            lambda r: r['bindings'].pop('wide_target_sha256'),
            lambda r: r['bindings'].update(wide_target_sha256='b'*64),
            lambda r: r['bindings'].update(master_sha256='../master.blend'),
            lambda r: r['targets'][0].update(file='../custom.target.gz'),
            lambda r: r['targets'][0].update(name='custom'),
            lambda r: r['targets'][0].update(weight=True),
            lambda r: r['targets'][0].update(weight=10**1000),
            lambda r: r['targets'][0].update(weight=.1),
            lambda r: r['targets'][1].update(weight=.2),
            lambda r: r['targets'].reverse(),
        ]
        for number, change in enumerate(mutations):
            candidate = deepcopy(source); change(candidate)
            with self.subTest(case=number), self.assertRaises(ValidationError):
                validate_face_recipe(candidate)


class FaceProjectTests(unittest.TestCase):
    def test_face_api_without_master_fails_before_asset_read_or_worker(self):
        from ucc.jobs.face_revision import apply_saved_face_revision
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(directory)
            project = store.save(replace(CharacterProject.new('No master'), schema_version=2,
                                         facial_parameters=(('nose_width', .8),)))
            before = store.file.read_bytes()
            with self.assertRaisesRegex(ValidationError, 'existing MPFB master'):
                apply_saved_face_revision(store, blender_exe=Path('not-launched'),
                    worker_script=Path('not-launched.py'), mpfb_data_dir=Path('not-read'),
                    expected_project_id=project.project_id, expected_revision=project.revision,
                    expected_master_blend=project.master_blend)
            self.assertEqual(store.file.read_bytes(), before)
            self.assertFalse((store.root/'.ucc-jobs').exists())

    def test_external_saved_master_history_rejects_metadata_substitution(self):
        original = CharacterProject.new('Existing')
        session = CharacterSession(original)
        intent = session.set_face_parameter('nose_width', .8)
        saved = replace(intent, master_blend='master/versions/'+'a'*64+'.blend',
                        geometry_state='generated_unverified', revision=intent.revision+1)
        for invalid in (replace(saved, name='Other'), replace(saved, facial_parameters=(('nose_width', .2),)),
                        replace(saved, revision=intent.revision+2)):
            with self.assertRaises(ValidationError):
                session.accept_saved_master(invalid)
        self.assertEqual(session.project, intent)
        session.accept_saved_master(saved)
        undone = session.undo()
        self.assertIsNone(undone.master_blend)
        redone = session.redo()
        self.assertEqual(redone.master_blend, saved.master_blend)
        self.assertGreater(redone.revision, saved.revision)

    def test_v1_roundtrip_and_neutral_edit_do_not_migrate(self):
        project = CharacterProject.new('Existing')
        original = project.to_dict()
        session = CharacterSession(CharacterProject.from_dict(deepcopy(original)))
        self.assertEqual(session.set_face_parameter('nose_width', .5), project)
        self.assertEqual(session.project.to_dict(), original)
        self.assertNotIn('facial_parameters', original)
        self.assertFalse(session.can_undo)

    def test_explicit_v2_intent_preserves_old_macros_and_undo_redo(self):
        original = CharacterProject.new('Existing')
        session = CharacterSession(original)
        changed = session.set_face_parameter('nose_width', .8)
        self.assertEqual(changed.schema_version, 2)
        self.assertEqual(changed.parameters, original.parameters)
        self.assertEqual(changed.facial_parameters, (('nose_width', .8),))
        self.assertEqual(CharacterProject.from_dict(changed.to_dict()), changed)
        restored = session.undo()
        self.assertEqual(restored.schema_version, 1)
        self.assertNotIn('facial_parameters', restored.to_dict())
        self.assertGreater(restored.revision, changed.revision)
        redone = session.redo()
        self.assertEqual(redone.schema_version, 2)
        self.assertEqual(redone.facial_parameters, changed.facial_parameters)
        self.assertGreater(redone.revision, restored.revision)

    def test_v2_rejects_missing_extra_and_invalid_facial_data(self):
        raw = CharacterSession(CharacterProject.new('Test')).set_face_parameter('nose_width', .8).to_dict()
        cases = []
        missing = deepcopy(raw); del missing['facial_parameters']; cases.append(missing)
        legacy = deepcopy(raw); legacy['schema_version'] = 1; cases.append(legacy)
        extra = deepcopy(raw); extra['unexpected'] = True; cases.append(extra)
        for face in (None, [], {'unknown': .5}, {'nose_width': True}, {'nose_width': float('nan')}, {'nose_width': 2.}):
            bad = deepcopy(raw); bad['facial_parameters'] = face; cases.append(bad)
        for number, candidate in enumerate(cases):
            with self.subTest(case=number), self.assertRaises(ValidationError):
                CharacterProject.from_dict(candidate)
        with self.assertRaises(ValidationError):
            replace(CharacterProject.new('Test'), facial_parameters=(('nose_width', .8),))
        with self.assertRaises(ValidationError):
            replace(CharacterProject.new('Test'), schema_version=2,
                    facial_parameters=(('nose_width', .8), ('nose_width', .7)))

    def test_intent_invalidates_geometry_approval_and_rejects_unvalidated_attachments(self):
        # Metadata-only contract fixture; this test produces no Blender file.
        original = replace(CharacterProject.new('Test'), master_blend='master/existing.blend',
                           geometry_state='validated')
        edited = CharacterSession(original).set_face_parameter('nose_width', .8)
        self.assertEqual(edited.master_blend, original.master_blend)
        self.assertEqual(edited.geometry_state, 'generated_unverified')
        self.assertTrue(edited.export_readiness())
        for project in (replace(original, animations=('unverified-clip',)),
                        replace(original, parts=(PartInstance('p', 'a', 'eye.L'),))):
            with self.subTest(project=project), self.assertRaises(CompatibilityError):
                CharacterSession(project).set_face_parameter('nose_width', .8)

    def test_saved_migration_retains_byte_exact_legacy_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(directory)
            original = store.save(CharacterProject.new('Legacy'))
            before = store.file.read_bytes()
            session = CharacterSession(store.load())
            self.assertEqual(store.file.read_bytes(), before)
            changed = session.set_face_parameter('nose_width', .8)
            store.save(changed, expected_revision=original.revision)
            self.assertEqual(store.list_backups()[0].read_bytes(), before)
            self.assertEqual(store.load(), changed)
            undone = session.undo()
            store.save(undone, expected_revision=changed.revision)
            self.assertEqual(store.load().schema_version, 1)
            self.assertNotIn('facial_parameters', json.loads(store.file.read_text(encoding='utf-8')))

    def test_failed_migration_write_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(directory); original = store.save(CharacterProject.new('Legacy'))
            before = store.file.read_bytes()
            changed = CharacterSession(original).set_face_parameter('nose_width', .8)
            with patch.object(store, '_atomic_bytes', side_effect=OSError('injected write failure')):
                with self.assertRaises(ProjectStorageError):
                    store.save(changed, expected_revision=original.revision)
            self.assertEqual(store.file.read_bytes(), before)
            self.assertEqual(store.load(), original)

    def test_legacy_body_operations_cannot_silently_discard_facial_intent(self):
        from ucc.jobs.humanoid_generation import generate_humanoid
        from ucc.jobs.body_revision import apply_saved_body_revision
        with tempfile.TemporaryDirectory() as directory:
            store = ProjectStore(directory)
            intent = replace(CharacterProject.new('Face intent'), schema_version=2,
                             facial_parameters=(('nose_width', .8),))
            saved = store.save(intent); before = store.file.read_bytes()
            common = dict(blender_exe=Path('not-launched'), worker_script=Path('not-launched.py'),
                          expected_project_id=saved.project_id, expected_revision=saved.revision)
            with patch('ucc.jobs.humanoid_generation.BlenderJobRunner') as worker:
                with self.assertRaisesRegex(ValidationError, 'facial intent'):
                    generate_humanoid(store, **common)
                worker.assert_not_called()
            with patch('ucc.jobs.body_revision.BlenderJobRunner') as worker:
                with self.assertRaisesRegex(ValidationError, 'facial intent'):
                    apply_saved_body_revision(store, expected_master_blend=saved.master_blend, **common)
                worker.assert_not_called()
            self.assertEqual(store.file.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
