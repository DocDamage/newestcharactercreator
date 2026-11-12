"""Closed-form coordinate/reference invariants, not production animation proof."""
import math
import unittest
from blender_bridge.native_reference import anatomy_frame,body_frame,target_reference,transport_global,check_mapping_hierarchy,RootRotation
from blender_bridge.rest_calibration import axis_rotation,multiply,transpose,transform,Z_UP_IDENTITY as I


def difference(a,b):return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


class NativeReferenceTests(unittest.TestCase):
    def test_common_reference_corrects_a_to_t_pose_and_preserves_bind_roll(self):
        source=(1.,0.,0.);target=(2**-.5,0.,-2**-.5);secondary=(0.,-1.,0.)
        for roll in (0,37,90):
            bind=axis_rotation("Yrotation",roll)
            ref,residual=target_reference(source,target,secondary,secondary,I,bind)
            actual=transform(multiply(ref,transpose(bind)),target)
            self.assertLess(max(abs(a-b) for a,b in zip(actual,source)),1e-12)
            self.assertLess(residual,1e-12)

    def test_source_bind_not_first_frame_is_the_rotation_reference(self):
        bind=axis_rotation("Xrotation",23)
        first=multiply(axis_rotation("Zrotation",31),bind)
        reference=axis_rotation("Yrotation",-42)
        actual=transport_global(bind,first,I,reference)
        expected=multiply(axis_rotation("Zrotation",31),reference)
        self.assertLess(difference(actual,expected),1e-12)
        self.assertGreater(difference(actual,reference),.1)

    def test_world_axes_noncommuting_rotation_is_covariant(self):
        c=axis_rotation("Yrotation",71);bind=axis_rotation("Zrotation",17)
        delta=axis_rotation("Xrotation",29);pose=multiply(delta,bind)
        reference=axis_rotation("Xrotation",-35)
        actual=transport_global(bind,pose,c,reference)
        expected=multiply(multiply(multiply(c,delta),transpose(c)),reference)
        self.assertLess(difference(actual,expected),1e-12)

    def test_body_frame_translation_invariance_and_degenerate_axes_reject(self):
        a,height=body_frame((.1,0,0),(-.1,0,0),(0,0,1))
        b,h=body_frame((3.1,4,5),(2.9,4,5),(3,4,6))
        self.assertLess(difference(a,b),1e-12);self.assertEqual(height,h)
        with self.assertRaises(ValueError):anatomy_frame((0,1,0),(0,1,0))
        with self.assertRaises(ValueError):body_frame((0,0,0),(0,0,0),(0,0,1))

    def test_nearest_mapped_ancestor_accepts_helpers_and_rejects_crossed_branches(self):
        pairs=[{"source":"@ARMATURE","target":"root","source_tip":None,"target_tip":None},
               {"source":"arm","target":"upper","source_tip":"hand","target_tip":"wrist"},
               {"source":"hand","target":"wrist","source_tip":None,"target_tip":None}]
        source={"@ARMATURE":None,"arm":"@ARMATURE","hand":"arm"}
        target={"root":None,"upper":"root","helper":"upper","wrist":"helper","other":"root"}
        ordered=check_mapping_hierarchy(pairs,source,target)
        self.assertLess(ordered.index("helper"),ordered.index("wrist"))
        target["wrist"]="other"
        with self.assertRaisesRegex(ValueError,"tip crosses"):check_mapping_hierarchy(pairs,source,target)
        pairs[1]["target_tip"]=None
        with self.assertRaisesRegex(ValueError,"ancestors"):check_mapping_hierarchy(pairs,source,target)

    def test_root_can_turn_full_circle_but_not_jump_or_skip_frames(self):
        root=RootRotation()
        for frame,degrees in enumerate(range(0,361,10),1):
            q=(math.cos(math.radians(degrees)/2),0.,0.,math.sin(math.radians(degrees)/2))
            root.add(tuple(-v for v in q) if frame%2 else q,frame)
        self.assertAlmostEqual(root.maximum_step,10.)
        with self.assertRaises(ValueError):root.add((1.,0.,0.,0.),99)
        fresh=RootRotation();fresh.add((1.,0.,0.,0.),1)
        with self.assertRaises(ValueError):fresh.add((0.,0.,0.,1.),2)
