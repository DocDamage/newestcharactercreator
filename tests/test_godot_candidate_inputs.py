"""Closed modifier metadata guards; actual MPFB negatives run separately."""
from copy import deepcopy
import unittest

from fixtures.godot_transaction_contract import unit_bind_profile
from ucc.core.errors import ValidationError
from ucc.jobs.godot_candidate_inputs import validate_bind_profile


class GodotCandidateInputTests(unittest.TestCase):
    def test_supported_linear_static_stack_is_read_only(self):
        profile = unit_bind_profile(); before = deepcopy(profile)
        validate_bind_profile(profile)
        self.assertEqual(profile, before)

    def test_dual_quaternion_envelopes_multi_modifier_and_numeric_booleans_reject(self):
        for key, value in [('use_deform_preserve_volume', True), ('use_bone_envelopes', True),
                           ('use_multi_modifier', True), ('use_vertex_groups', False),
                           ('use_deform_preserve_volume', 0), ('show_render', False)]:
            profile = unit_bind_profile(); profile['source_modifiers'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                validate_bind_profile(profile)

    def test_corrective_smoothing_and_nonstatic_or_wrong_source_masks_reject(self):
        for key, value in [('type', 'CORRECTIVE_SMOOTH'), ('use_smooth', True), ('mode', 'ARMATURE'),
                           ('threshold', float('nan')), ('threshold', -1.), ('source_mesh_vertices', True),
                           ('source_mesh_vertices', 13380), ('vertex_group_sha256', '../outside')]:
            profile = unit_bind_profile(); profile['source_modifiers'][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                validate_bind_profile(profile)

    def test_missing_bakes_or_unknown_modifiers_cannot_be_silently_discarded(self):
        for fault in ['body', 'mask', 'extra_modifier', 'unknown_field']:
            profile = unit_bind_profile()
            if fault == 'body': profile['body_and_hand_targets_baked'] = False
            if fault == 'mask': profile['static_masks_baked'] = False
            if fault == 'extra_modifier': profile['source_modifiers'].append({'type': 'SUBSURF'})
            if fault == 'unknown_field': profile['source_modifiers'][0]['unreviewed_behavior'] = True
            with self.subTest(fault=fault), self.assertRaises(ValidationError):
                validate_bind_profile(profile)


if __name__ == '__main__':
    unittest.main()
