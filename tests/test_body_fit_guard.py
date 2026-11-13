"""Conservative comparison gates on invented observations; no physical claim."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from ucc.core.errors import ValidationError
from ucc.jobs.body_fit_guard import require_body_fit_guard,POLICY
from ucc.preview.body_contacts import BodyContacts,POLICY as BODY_POLICY
from ucc.preview.contact_areas import BodyContactAreas
from ucc.preview.surface_review import SurfaceReview


class BodyFitGuardTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);path=Path(temp.name)/'unit-report.json'
        path.write_bytes(b'unit-only-not-a-physical-report')
        original=SurfaceReview('CHECKED','',((1,2),(),()),((2,0),(0,0),(0,0)),('a'*64,)*3,BODY_POLICY)
        fitted=replace(original,triangles=((2,),(),()),pairs=((1,0),(0,0),(0,0)))
        contacts=BodyContacts(original,fitted,())
        areas=BodyContactAreas(contacts,'CHECKED','','a'*64,(frozenset({1,2}),frozenset(),frozenset()),
            (frozenset({2}),frozenset(),frozenset()),(),())
        self.review=SimpleNamespace(contacts=contacts,areas=areas,private_report=str(path),report_sha256=sha256(path.read_bytes()).hexdigest(),
            original_playback=SimpleNamespace(cache=SimpleNamespace(frame_count=3,source_first_frame=7)),fitted_playback=object())

    def test_fewer_pairs_and_only_existing_stable_faces_produce_bound_unapproved_receipt(self):
        receipt=require_body_fit_guard(self.review);self.assertEqual(receipt.policy,POLICY)
        self.assertEqual(receipt.body_report_sha256,self.review.report_sha256);self.assertEqual(receipt.frames_checked,3)
        self.assertFalse(hasattr(receipt,'contact_quality_verified'))

    def test_new_face_rejects_even_if_total_pair_count_and_flagged_frames_drop(self):
        self.review.areas=replace(self.review.areas,fitted=(frozenset({2,3}),frozenset(),frozenset()),new_area_frames=(0,))
        with self.assertRaisesRegex(ValidationError,'BODY_FIT_INTRODUCES_CONTACT_AREAS; source frames 7'):
            require_body_fit_guard(self.review)

    def test_one_hands_pair_increase_cannot_hide_behind_the_other_hands_decrease(self):
        contacts=self.review.contacts;fitted=replace(contacts.fitted,pairs=((0,1),(0,0),(0,0)))
        self.review.contacts=replace(contacts,fitted=fitted)
        self.review.areas=replace(self.review.areas,contacts=self.review.contacts,more_hand_pair_frames=(0,))
        with self.assertRaisesRegex(ValidationError,'BODY_FIT_INCREASES_HAND_PAIRS'):require_body_fit_guard(self.review)

    def test_missing_unavailable_stale_partial_and_forged_comparison_fields_reject(self):
        for fault in ('missing','unavailable','original_only','partial','summary','counts','hash','file','sha'):
            case=BodyFitGuardTests();case.setUp()
            try:
                r=case.review
                if fault=='missing':r.areas=None
                if fault=='unavailable':r.areas=replace(r.areas,status='UNAVAILABLE')
                if fault=='original_only':r.fitted_playback=None
                if fault=='partial':r.areas=replace(r.areas,fitted=r.areas.fitted[:-1])
                if fault=='summary':r.areas=replace(r.areas,new_area_frames=(0,))
                if fault=='counts':r.areas=replace(r.areas,more_hand_pair_frames=(0,))
                if fault=='hash':r.report_sha256='b'*64
                if fault=='file':Path(r.private_report).unlink()
                if fault=='sha':r.areas=replace(r.areas,polygon_sha256=None)
                with self.subTest(fault=fault),self.assertRaises(ValidationError):require_body_fit_guard(r)
            finally:case.doCleanups()


if __name__=='__main__':unittest.main()
