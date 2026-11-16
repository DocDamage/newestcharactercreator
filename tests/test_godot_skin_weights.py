"""Pure representation tests; no synthetic mesh is engine/MPFB evidence."""
import math
import unittest

from blender_bridge.godot_skin_weights import normalize_weights, serialization_weights


class GodotSkinWeightsTests(unittest.TestCase):
    def test_all_eight_positive_contributions_survive_without_top_four_pruning(self):
        rows = tuple((f'bone{i}', (i+1)/40) for i in range(8))
        converted, total = normalize_weights(rows)
        self.assertEqual([name for name, _ in converted], [name for name, _ in rows])
        self.assertAlmostEqual(math.fsum(weight for _, weight in converted), 1.)
        for (_, original), (_, weight) in zip(rows, converted):
            self.assertAlmostEqual(weight*total, original)

    def test_uniform_scaling_preserves_relative_deformation_contributions(self):
        rows = (('upper', .19996), ('lower', .79984))
        actual, _ = normalize_weights(rows)
        for (_, weight), expected in zip(actual, (.2, .8)):
            self.assertAlmostEqual(weight, expected)

    def test_zero_weights_do_not_consume_the_eight_positive_slots(self):
        rows = (('unused', 0.), *tuple((f'b{i}', .125) for i in range(8)))
        actual, _ = normalize_weights(rows)
        self.assertEqual(len(actual), 8)
        self.assertNotIn('unused', dict(actual))

    def test_ninth_influence_is_rejected_instead_of_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, 'truncation is forbidden'):
            normalize_weights(tuple((f'b{i}', .1) for i in range(9)))

    def test_missing_duplicate_nonfinite_and_invalid_weights_are_rejected(self):
        bad = [(), (('b', 0.),), (('b', .5), ('b', .5)), (('b', True),),
               (('b', float('nan')),), (('b', float('inf')),), (('b', -.1),),
               (('b', 1.1),), ((False, .5),), (('b',),), [('b', 1.)]]
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                normalize_weights(rows)

    def test_uniform_serialization_scale_keeps_small_positive_influence(self):
        original = (('large', .7583), ('middle', .2416), ('small', .000099999997))
        serialized = serialization_weights(original)
        self.assertEqual(dict(serialized)['large'], 1.)
        self.assertGreater(dict(serialized)['small'], .0001)
        normalized, _ = normalize_weights(serialized)
        expected, _ = normalize_weights(original)
        for (name, value), (expected_name, expected_value) in zip(normalized, expected):
            self.assertEqual(name, expected_name)
            self.assertAlmostEqual(value, expected_value, places=7)

    def test_unrepresentable_ratio_fails_without_nudging_or_dropping_it(self):
        with self.assertRaisesRegex(ValueError, 'no pruning allowed'):
            serialization_weights((('large', .99999999), ('small', .00000001)))


if __name__ == '__main__':
    unittest.main()
