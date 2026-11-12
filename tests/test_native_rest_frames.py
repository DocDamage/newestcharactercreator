"""Endpoint-preserving roll changes must not pass saved rest-frame checks."""
from copy import deepcopy
import math
import unittest
from blender_bridge.native_rest_frames import same_rest_frames


class NativeRestFrameTests(unittest.TestCase):
    def frames(self):
        return {"helper":{"parent":"wrist","matrix":[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]}}

    def test_complete_rest_matrix_detects_roll_with_unchanged_endpoints_and_parent(self):
        before=self.frames();after=deepcopy(before)
        self.assertTrue(same_rest_frames(before,after))
        # A Y-axis roll preserves the bone's origin and longitudinal axis.
        c,s=math.cos(.05),math.sin(.05)
        after["helper"]["matrix"][0]=after["helper"]["matrix"][10]=c
        after["helper"]["matrix"][2]=s;after["helper"]["matrix"][8]=-s
        self.assertFalse(same_rest_frames(before,after))

    def test_missing_extra_reparented_or_nonfinite_rest_evidence_rejects(self):
        for kind in ("missing","extra","parent","nan","bool","large","short"):
            a=self.frames();b=deepcopy(a)
            if kind=="missing":b.clear()
            if kind=="extra":b["other"]=deepcopy(b["helper"])
            if kind=="parent":b["helper"]["parent"]="other"
            if kind=="nan":b["helper"]["matrix"][0]=float('nan')
            if kind=="bool":b["helper"]["matrix"][0]=True
            if kind=="large":b["helper"]["matrix"][0]=10**1000
            if kind=="short":b["helper"]["matrix"].pop()
            with self.subTest(kind=kind):self.assertFalse(same_rest_frames(a,b))
