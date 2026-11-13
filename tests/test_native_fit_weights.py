"""Exact source weight guard catches changes below the old display precision."""
from types import SimpleNamespace as Obj
import struct
import unittest
from blender_bridge.native_fit_scene import exact_weights_digest


class NativeFitWeightTests(unittest.TestCase):
    def human(self,weight):
        return Obj(vertex_groups=[Obj(index=0,name='bone'),Obj(index=1,name='static-mask')],
                   data=Obj(vertices=[Obj(index=0,groups=[Obj(group=0,weight=weight),Obj(group=1,weight=.25)])]))

    def test_one_float32_ulp_weight_edit_rejects_even_when_six_decimal_evidence_is_equal(self):
        weight=.5;bits=struct.unpack('<I',struct.pack('<f',weight))[0]
        changed=struct.unpack('<f',struct.pack('<I',bits+1))[0]
        self.assertEqual(round(weight*1e6),round(changed*1e6))
        self.assertNotEqual(exact_weights_digest(self.human(weight)),exact_weights_digest(self.human(changed)))

    def test_all_groups_are_bound_without_dependence_on_membership_iteration_order(self):
        original=self.human(.5);other=self.human(.5);other.data.vertices[0].groups.reverse()
        self.assertEqual(exact_weights_digest(original),exact_weights_digest(other))
        other.data.vertices[0].groups[0].weight=.3
        self.assertNotEqual(exact_weights_digest(original),exact_weights_digest(other))
