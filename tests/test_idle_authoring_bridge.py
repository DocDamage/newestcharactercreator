"""Pure synthetic tests only; no Blender, installed assets, native or quality proof."""
from copy import deepcopy
from hashlib import sha256
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from blender_bridge.idle_authoring_math import (
    body_axes,cross,dot,hand_anatomy,periodic_amplitudes,periodic_derivatives,
    relaxed_directions,sign_continuous,
)
from blender_bridge.idle_authoring_policy import (
    AuthoredIdleError,canonical_digest,checked_job,document,finite_matrix,finite_vector,
    payload,private_bytes,write_document,
)
from blender_bridge.idle_authoring_verify import _max_difference,wrapped_velocity_residual
from blender_bridge.idle_authoring_scene import digit_flex_degrees
from tests.fixtures.idle_authoring_bridge import BODY,HANDS,METACARPALS,PHALANGES,identity,rotated,staged_inspection
from ucc.core.authored_idle import baseline_spec,periodic_spec
from ucc.core.target_action_format import canonical_bytes
from ucc.core.errors import ValidationError


class OriginalIdleMathTests(unittest.TestCase):
    def axes(self):return body_axes(BODY['pelvis'],BODY['neck'],BODY['left'],BODY['right'])

    def test_all_eight_metacarpals_have_no_authored_rotation(self):
        for name in METACARPALS:
            with self.subTest(name=name):
                self.assertIsNone(digit_flex_degrees(name,baseline_spec()))

    def test_exact_specified_phalanges_and_thumb_keep_declared_flex(self):
        for name,expected in PHALANGES:
            with self.subTest(name=name):
                self.assertEqual(digit_flex_degrees(name,baseline_spec()),expected)

    def test_other_helpers_and_nonexact_digit_names_are_unaddressed(self):
        for name in ('metacarpal1.L','wrist.R','finger1-0.L','finger2--1.R',
                     'finger2-4.L','finger6-1.L','finger2-1.L.001','finger2-1.X',
                     'finger2-1.L\n','finger2-01.L','finger20-1.R'):
            with self.subTest(name=name):
                self.assertIsNone(digit_flex_degrees(name,baseline_spec()))

    def test_public_mpfb_anterior_and_proper_handed_frame(self):
        axes=self.axes()
        self.assertGreater(dot(axes['forward'],(0.,-1.,0.)),.999999)
        self.assertGreater(dot(cross(axes['right'],axes['forward']),axes['up']),.999999)

    def test_relaxed_both_arms_drop_not_t_pose_and_flex_anterior(self):
        axes=self.axes()
        for side in ('L','R'):
            row=relaxed_directions(axes,side,baseline_spec())
            self.assertLess(dot(row['upper'],axes['up']),-.8)
            self.assertGreater(dot(row['lower'],axes['forward']),dot(row['upper'],axes['forward']))
            self.assertAlmostEqual(dot(row['hand'],row['palm']),0.)

    def test_chiral_palmar_normals_and_positive_flex_are_volar_both_sides(self):
        for side,points in HANDS.items():
            hand=hand_anatomy(side,**points)
            self.assertGreater(dot(hand['normal'],(0.,0.,-1.)),.999999)
            self.assertGreater(dot(cross(hand['flex_axis'],hand['direction']),hand['normal']),.999999)
            self.assertLess(dot(cross(hand['flex_axis'],hand['direction']),(0.,0.,1.)),-.999999)

    def test_hand_axis_measurement_is_equivariant_under_proper_rotation(self):
        for side,points in HANDS.items():
            hand=hand_anatomy(side,**points)
            actual=hand_anatomy(side,**{k:rotated(v) for k,v in points.items()})
            for key,value in hand.items():
                self.assertGreater(dot(actual[key],rotated(value)),.999999)

    def test_degenerate_and_nonplanar_hands_are_rejected(self):
        for points in [dict(HANDS['L'],index=HANDS['L']['little']),
                       dict(HANDS['L'],index=(2.,0.,0.),little=(1.,0.,0.)),
                       dict(HANDS['L'],index=(1.,-.5,10.),little=(1.,.5,10.))]:
            with self.assertRaises(ValueError):hand_anatomy('L',**points)

    def test_stored_300_are_unique_phase_samples_virtual_only_closes(self):
        periodic=periodic_spec()
        a=periodic_amplitudes(1,periodic);last=periodic_amplitudes(300,periodic)
        self.assertNotEqual(a,last)
        self.assertAlmostEqual(periodic_amplitudes(301,periodic)['torso'],a['torso'],places=12)
        self.assertNotEqual(periodic_derivatives(1,periodic)['torso'],0.)
        self.assertAlmostEqual(periodic_derivatives(1,periodic)['torso'],periodic_derivatives(301,periodic)['torso'])
        for value in (0,302,True,1.5):
            with self.assertRaises(ValueError):periodic_amplitudes(value,periodic)

    def test_quaternion_sign_continuity_and_nonfinite_rejection(self):
        self.assertEqual(sign_continuous((-1.,0.,0.,0.),(1.,0.,0.,0.)),(1.,-0.,-0.,-0.))
        for value in ((1.,0.,float('nan'),0.),(0.,0.,0.,0.),(1.,float('inf'),0.,0.)):
            with self.assertRaises(ValueError):sign_continuous(value)

    def test_nan_after_finite_first_matrix_value_never_passes_max_guard(self):
        actual={'bone':identity()};wanted=deepcopy(actual)
        for index in (1,7,15):
            bad=deepcopy(actual);bad['bone'][index]=float('nan')
            with self.assertRaises(ValueError):_max_difference(bad,wanted)
            with self.assertRaises(ValueError):wrapped_velocity_residual(bad,wanted,wanted,wanted)
        with self.assertRaises(ValueError):finite_vector((0.,float('nan'),0.))
        with self.assertRaises(ValueError):finite_matrix(identity()[:-1])

    def test_wrapped_velocity_compares_same_interval_not_zero(self):
        last={'bone':identity()};first=deepcopy(last);first['bone'][3]=.01
        self.assertEqual(wrapped_velocity_residual(first,last,first,last)['position_m_s'],0.)
        self.assertGreater(wrapped_velocity_residual(first,last,last,last)['position_m_s'],0.)


class OriginalIdleBoundaryTests(unittest.TestCase):
    def test_private_frame_canonical_sha_is_actual_file_sha_even_unicode(self):
        value={'NONSHIPPING':'synthetic-é','items':[1.,2.,3.]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();record=write_document(root,'frame.json',value)
            self.assertEqual(record['sha256'],canonical_digest(value))
            self.assertEqual(record['sha256'],sha256((root/'frame.json').read_bytes()).hexdigest())
            self.assertEqual(document(root,'frame.json',record['sha256']),value)

    def test_private_evidence_cap_is_distinct_from_intent_cap(self):
        value={'NONSHIPPING':'x'*(300*1024)}
        with self.assertRaises(ValidationError):canonical_bytes(value)
        self.assertGreater(len(private_bytes(value)),256*1024)
        with self.assertRaises(ValueError):private_bytes(value,1024)

    def test_growth_between_hash_and_payload_read_is_bounded_and_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();path=root/'frame.json';data=b'{}';path.write_bytes(data)
            expected=sha256(data).hexdigest()
            def grow(*args,**kwargs):path.write_bytes(b'x'*100);return expected
            with patch('blender_bridge.idle_authoring_policy.digest',side_effect=grow):
                with self.assertRaises(ValueError):payload(root,'frame.json',expected,16)

    def test_boundary_checks_neutral_intent_without_fabricated_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();request,job=staged_inspection(root)
            actual,inputs=checked_job(job,root)
            self.assertEqual(actual,request);self.assertEqual(len(inputs),2)
            self.assertNotIn('target',actual.to_dict())
            job['options']['anatomical_frame_sha256']='1'*64
            with self.assertRaises(ValueError):checked_job(job,root)

    def test_changed_master_or_existing_evidence_never_succeeds(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();_,job=staged_inspection(root)
            (root/'candidate.blend').write_bytes(b'NONSHIPPING changed bytes')
            with self.assertRaises(ValueError):checked_job(job,root)
            write_document(root,'evidence.json',{'fixture':True})
            with self.assertRaises(FileExistsError):write_document(root,'evidence.json',{'fixture':False})

    def test_private_json_rejects_nonfinite_duplicate_keys_and_noncanonical_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            for raw in (b'{"x":NaN}',b'{"x":1,"x":2}',b'{"x":1e999}',b'{ "x":1}'):
                (root/'evidence.json').write_bytes(raw)
                with self.assertRaises(ValueError):document(root,'evidence.json',sha256(raw).hexdigest())


if __name__=='__main__':unittest.main()
