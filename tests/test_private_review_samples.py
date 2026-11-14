import unittest
from blender_bridge.private_review_render import review_samples,PrivateRenderError


class PrivateReviewSamplesTests(unittest.TestCase):
    def test_existing_sample_sequences_are_preserved(self):
        self.assertEqual(review_samples(25),[1,7,13,19,25])
        self.assertEqual(review_samples(300),[1,75,150,225,300])

    def test_targeted_contact_frames_do_not_change_source_frame_count(self):
        frames=[1,6,8,11,31]
        self.assertEqual(review_samples(300,frames),frames)
        self.assertIsNot(review_samples(300,frames),frames)
        with self.assertRaises(PrivateRenderError):review_samples(25,frames)

    def test_bad_coverage_bool_indices_duplicate_order_and_workload_reject(self):
        for count,frames in ((True,None),(4,None),(2001,None),(300,[1,6,8,11]),
                             (300,[1,6,8,8,31]),(300,[1,8,6,11,31]),(300,[True,6,8,11,31]),
                             (300,[0,6,8,11,31]),(300,[1,6,8,11,301]),(300,'12345')):
            with self.subTest(count=count,frames=frames),self.assertRaises(PrivateRenderError):
                review_samples(count,frames)
