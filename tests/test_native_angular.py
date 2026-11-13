"""Nonshipping float32 quaternion precision cases; not animation evidence."""
import math
import struct
import unittest
from blender_bridge.native_angular import angular_velocity


class NativeAngularTests(unittest.TestCase):
    def test_vector_part_retains_motion_when_scalar_rounds_to_one(self):
        single=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
        for degrees in (.001,.005,.01,.02,.03,.04,.05,.1):
            angle=math.radians(degrees)/2
            q=(single(math.cos(angle)),single(math.sin(angle)),0.,0.)
            with self.subTest(degrees=degrees):
                actual=angular_velocity(q,30.)
                self.assertAlmostEqual(actual[0],degrees*30.,delta=1e-6)
                self.assertEqual(actual[1:],(0.,0.))
        self.assertEqual(single(math.cos(math.radians(.01)/2)),1.)

    def test_equivalent_hemispheres_and_scaling_have_same_velocity(self):
        q=(math.cos(.01),.3*math.sin(.01),-.4*math.sin(.01),math.sqrt(.75)*math.sin(.01))
        expected=angular_velocity(q,60.)
        for multiple in (-1.,.9999999,1.0000001):
            for a,b in zip(expected,angular_velocity(tuple(v*multiple for v in q),60.)):
                self.assertAlmostEqual(a,b,places=10)
        self.assertEqual(angular_velocity((1.,0.,0.,0.),30.),(0.,0.,0.))

    def test_malformed_nonfinite_and_zero_rotation_data_rejects(self):
        for q,fps in (((0.,0.,0.,0.),30.),((True,0.,0.,0.),30.),((1.,float('nan'),0.,0.),30.),
                      ((1.,0.,0.),30.),((1.,0.,0.,0.),True),((1.,0.,0.,0.),0.)):
            with self.subTest(q=q,fps=fps),self.assertRaises(ValueError):angular_velocity(q,fps)
