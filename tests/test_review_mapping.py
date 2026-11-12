"""Pure contract tests; none claim that synthetic motion proves external rig compatibility."""
from __future__ import annotations

import unittest

from ucc.animations.review_mapping import (
    parse_review_mapping, review_mapping_sha256, validate_review_mapping,
)
from ucc.core.errors import ValidationError


class ReviewMappingTests(unittest.TestCase):
    def test_three_named_roles_are_explicit_and_ordered(self):
        raw = "CustomNeck02 -> neck02\nCustomNeck03 -> neck03\nCustomHead -> head"
        pairs = parse_review_mapping(raw)
        self.assertEqual([p["target"] for p in pairs], ["neck02", "neck03", "head"])
        self.assertEqual(len(review_mapping_sha256(pairs)), 64)
        self.assertNotEqual(review_mapping_sha256(pairs), review_mapping_sha256(list(reversed(pairs))))

    def test_invalid_or_ambiguous_pairs_rejected(self):
        good = [{"source": "a", "target": "x"}, {"source": "b", "target": "y"},
                {"source": "c", "target": "z"}]
        for bad in ([], good[:2], good * 3, good + [good[0]],
                    [*good[:2], {"source": "c", "target": "X"}],
                    [{**good[0], "extra": True}, *good[1:]],
                    [{**good[0], "source": "../bad"}, *good[1:]],
                    [{**good[0], "source": "bad\\bone"}, *good[1:]]):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_review_mapping(bad)
        for text in ("a => x\nb -> y\nc -> z", "a -> x\nb -> y\nx -> y",
                     "a -> x\nb -> y", "a -> x\nb -> y\nc -> z -> extra"):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                parse_review_mapping(text)

    def test_namespace_prefix_is_permitted_but_paths_are_not(self):
        pairs = parse_review_mapping(
            "mixamorig:Hips -> neck02\nmixamorig:Spine -> neck03\nmixamorig:Head -> head"
        )
        self.assertEqual(pairs[0]["source"], "mixamorig:Hips")

    def test_same_source_or_target_casefold_is_not_distinct(self):
        with self.assertRaises(ValidationError):
            parse_review_mapping("Neck -> neck02\nneck -> neck03\nHead -> head")
        with self.assertRaises(ValidationError):
            parse_review_mapping("n1 -> Head\nn2 -> head\nn3 -> neck03")


if __name__ == "__main__":
    unittest.main()
