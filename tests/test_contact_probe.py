"""Candidate rejection/control flow only; no invented physical success claim."""
import unittest
from unittest.mock import Mock

from blender_bridge.native_contact_probe import CandidateProbe,CandidateBudgetExceeded
from blender_bridge.motion_quality import MotionQualityError


class ContactProbeTests(unittest.TestCase):
    def test_actual_quality_rejection_does_not_abort_later_candidates(self):
        probe=CandidateProbe.__new__(CandidateProbe)
        probe.frame=Mock(side_effect=MotionQualityError('unchanged compression limit'))
        rejected=probe.evaluate({},(6,8));self.assertGreater(rejected['pairs'],5_000_000)
        self.assertIn('compression',rejected['reason'])
        probe.frame=Mock(return_value=0)
        self.assertEqual(probe.evaluate({},(6,8)),{'pairs':0,'checked':2,'reason':''})

    def test_crossing_short_circuits_trial_and_budget_exhaustion_is_terminal(self):
        probe=CandidateProbe.__new__(CandidateProbe);probe.frame=Mock(side_effect=(0,12))
        result=probe.evaluate({},(5,8,27));self.assertEqual(result['failed_frame'],8)
        self.assertEqual(result['pairs'],12);self.assertEqual(probe.frame.call_count,2)
        probe.frame=Mock(side_effect=CandidateBudgetExceeded('bounded work exhausted'))
        with self.assertRaises(CandidateBudgetExceeded):probe.evaluate({},(1,2,3))


if __name__=='__main__':unittest.main()
