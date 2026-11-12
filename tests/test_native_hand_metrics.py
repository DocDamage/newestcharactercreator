"""Synthetic negative: wrist motion alone must not count as finger animation."""
from copy import deepcopy
import math
import unittest
from ci.native_hand_metrics import hand_local_motion
from ucc.animations.native_hands import HAND_TARGETS


class NativeHandMetricsTests(unittest.TestCase):
    def test_inherited_motion_is_zero_and_intrinsic_motion_is_measured(self):
        names=sorted(HAND_TARGETS)+["wrist.L","wrist.R"]
        def pose(angle):
            c,s=math.cos(angle),math.sin(angle)
            return [c,-s,0.,0.,s,c,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
        data={"mapped_pairs":[{"target":name} for name in names],
              "full_timeline_frames":[{"target_global_poses":[pose(a) for _ in names]} for a in (0.,.2,.4)]}
        self.assertLess(max(hand_local_motion(data).values()),1e-4)
        changed=deepcopy(data)
        changed["full_timeline_frames"][-1]["target_global_poses"][names.index("finger2-3.L")]=pose(.5)
        motion=hand_local_motion(changed)
        self.assertAlmostEqual(motion["finger2-3.L"],math.degrees(.1),places=5)
        self.assertLess(motion["finger2-2.L"],1e-4)
