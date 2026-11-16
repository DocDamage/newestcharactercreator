"""Reference metadata history preserves master intent and never grants exports."""
from dataclasses import replace
import tempfile
from pathlib import Path
import unittest

from fixtures.project_reference_contract import ReferenceFixture
from ucc.core.commands import CharacterSession
from ucc.core.errors import ValidationError
from ucc.core.models import CharacterProject


class ReferenceHistoryTests(unittest.TestCase):
    def test_intent_attach_detach_undo_redo_preserves_old_identifiers_and_all_fields(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        original = ReferenceFixture(Path(temporary.name))
        session = CharacterSession(original.project)
        attached = session.attach_animation_reference(original.clip_id)
        self.assertEqual(attached, replace(original.project, animations=(original.clip_id,), revision=2))
        self.assertEqual(session.attach_animation_reference(original.clip_id), attached)
        self.assertEqual(session.undo().animations, ()); self.assertEqual(session.redo().animations, (original.clip_id,))
        self.assertEqual(session.detach_animation_reference(original.clip_id).animations, ())
        self.assertEqual(original.master.read_bytes(), original.master_bytes)

    def test_accept_saved_reference_rejects_unrelated_changes_and_reordered_members(self):
        project = replace(CharacterProject.new('Metadata'),
                          animations=('first#clip-0000', 'second#clip-0000'))
        for changed in (replace(project, name='Changed', animations=(), revision=1),
                        replace(project, animations=('second#clip-0000',), revision=0),
                        replace(project, animations=('second#clip-0000', 'first#clip-0000', 'third#clip-0000'), revision=1)):
            with self.subTest(changed=changed), self.assertRaises(ValidationError):
                CharacterSession(project).accept_saved_animation_references(changed)

    def test_source_reference_never_makes_metadata_engine_ready(self):
        project = replace(CharacterProject.new('Metadata only'), master_blend='master/fixture.blend',
                          geometry_state='validated', rig_profile='synthetic.metadata.only', animations=('source#clip-0000',))
        self.assertIn('separate target and engine acceptance', ' '.join(project.export_readiness()))

    def test_bad_identifiers_cannot_be_adopted_from_a_saved_reference_result(self):
        project = CharacterProject.new('Metadata')
        saved = replace(project, animations=('source\n#clip-0000',), revision=1)
        with self.assertRaises(ValidationError): CharacterSession(project).accept_saved_animation_references(saved)


if __name__ == '__main__': unittest.main()
