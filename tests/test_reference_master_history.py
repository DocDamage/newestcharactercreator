"""Exact metadata/history boundaries; not geometry or master admission."""
from dataclasses import replace
import unittest

from ucc.core.commands import CharacterSession
from ucc.core.errors import CompatibilityError, ValidationError
from ucc.core.expressions import ExpressionState, DEFAULTS
from ucc.core.hand_parts import hand_asset_id
from ucc.core.models import CharacterProject, PartInstance


class ReferencedMasterHistoryTests(unittest.TestCase):
    def setUp(self):
        self.before = replace(CharacterProject.new('Reference master history fixture'), schema_version=3,
            master_blend='master/versions/'+('a'*64)+'.blend', geometry_state='generated_unverified',
            animations=('structural-source#clip-0000',),
            expression=ExpressionState('e'*64, tuple((name, .5) for name in DEFAULTS)),
            parts=(PartInstance('preserved-hand', hand_asset_id('b'*64, 'shorter'), 'hand.L'),))
        self.saved = replace(self.before, master_blend='master/versions/'+('c'*64)+'.blend',
            revision=self.before.revision+1,
            parts=(replace(self.before.parts[0], part_asset_id=hand_asset_id('d'*64, 'shorter')),))

    def test_adopt_one_rebuilt_master_and_hand_then_undo_redo_complete_state(self):
        session = CharacterSession(self.before)
        self.assertEqual(session.accept_saved_reference_master(self.saved), self.saved)
        undone = session.undo(); self.assertEqual(undone, replace(self.before, revision=undone.revision))
        redone = session.redo(); self.assertEqual(redone, replace(self.saved, revision=redone.revision))

    def test_source_strength_shape_and_revision_changes_cannot_be_adopted(self):
        changes = [dict(animations=()), dict(name='Unrelated rename'),
            dict(parameters=(('height', .6), ('muscle', .5), ('weight', .5))),
            dict(expression=ExpressionState('e'*64, tuple(DEFAULTS.items()))),
            dict(revision=self.saved.revision+1), dict(geometry_state='not_generated')]
        for fields in changes:
            session = CharacterSession(self.before)
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                session.accept_saved_reference_master(replace(self.saved, **fields))
            self.assertFalse(session.can_undo)

    def test_same_variant_and_instance_are_mandatory_for_rebuilt_hand(self):
        for part in (replace(self.saved.parts[0], part_id='replaced-instance'),
                     replace(self.saved.parts[0], part_asset_id=hand_asset_id('d'*64, 'longer')),
                     replace(self.saved.parts[0], part_asset_id=hand_asset_id('b'*64, 'shorter'))):
            with self.assertRaises(CompatibilityError):
                CharacterSession(self.before).accept_saved_reference_master(replace(self.saved, parts=(part,)))

    def test_no_hand_and_verified_noop_do_not_invent_part_or_history(self):
        before = replace(self.before, parts=()); session = CharacterSession(before)
        self.assertEqual(session.accept_saved_reference_master(before), before); self.assertFalse(session.can_undo)
        with self.assertRaises(ValidationError):
            session.accept_saved_reference_master(replace(before, revision=before.revision+1))
        saved = replace(self.saved, parts=()); self.assertEqual(session.accept_saved_reference_master(saved), saved)
        with self.assertRaises(CompatibilityError):
            CharacterSession(before).accept_saved_reference_master(self.saved)

    def test_plain_master_adoption_and_history_preserve_absent_expressions(self):
        for hand in (False, True):
            with self.subTest(hand=hand):
                before = replace(self.before, schema_version=2, expression=None,
                                 parts=self.before.parts if hand else ())
                saved = replace(self.saved, schema_version=2, expression=None,
                                parts=self.saved.parts if hand else ())
                session = CharacterSession(before)
                self.assertEqual(session.accept_saved_reference_master(saved), saved)
                undone = session.undo(); self.assertEqual(undone, replace(before, revision=undone.revision))
                redone = session.redo(); self.assertEqual(redone, replace(saved, revision=redone.revision))
                self.assertIsNone(redone.expression)

    def test_plain_adoption_cannot_introduce_expression_controls_or_change_source_ids(self):
        before = replace(self.before, schema_version=2, expression=None)
        plain = replace(self.saved, schema_version=2, expression=None)
        for saved in (self.saved, replace(plain, animations=('other-source#clip-0000',))):
            session = CharacterSession(before)
            with self.assertRaises(ValidationError): session.accept_saved_reference_master(saved)
            self.assertFalse(session.can_undo)


if __name__ == '__main__': unittest.main()
