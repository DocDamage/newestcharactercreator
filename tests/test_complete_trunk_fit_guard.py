"""Nonshipping publication metadata; no actual collision or quality evidence."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from ucc.core.errors import ValidationError
from ucc.preview.central_surface import CompleteTrunkSurfaces,CompleteSurfaceVariant,POLICY
from ucc.preview.surface_review import SurfaceReview
from ucc.jobs.complete_trunk_fit_guard import require_complete_trunk_fit_guard


class CompleteTrunkFitGuardTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=Path(tmp.name)
        report=folder/'full_trunk_contacts.json';report.write_bytes(b'unit report')
        receipt=folder/'result.json';receipt.write_bytes(b'unit receipt')
        surface=SurfaceReview('CHECKED','',((1,2),)*3,((2,1),)*3,('a'*64,)*3,POLICY)
        variant=CompleteSurfaceVariant(surface,((frozenset({1}),frozenset({2})),)*3,
            ((frozenset({3}),frozenset({4})),)*3)
        self.review=SimpleNamespace(full_trunk=CompleteTrunkSurfaces(variant,variant,(),()),
            original_playback=SimpleNamespace(cache=SimpleNamespace(frame_count=3,source_first_frame=10)),fitted_playback=object(),
            private_full_trunk_report=str(report),full_trunk_report_sha256=sha256(report.read_bytes()).hexdigest(),
            private_anatomical_verification=str(receipt),anatomical_verification_sha256=sha256(receipt.read_bytes()).hexdigest())

    def test_unchanged_verified_per_hand_identities_and_counts_pass(self):
        guard=require_complete_trunk_fit_guard(self.review)
        self.assertEqual(guard.frames_checked,3)
        self.assertEqual(guard.full_trunk_report_sha256,self.review.full_trunk_report_sha256)

    def test_swapping_hands_or_new_body_polygons_cannot_hide_behind_aggregate_totals(self):
        full=self.review.full_trunk
        for field,values in [('hand_polygons',((frozenset({2}),frozenset({1})),)*3),
                             ('body_polygons',((frozenset({5}),frozenset({4})),)*3)]:
            self.review.full_trunk=replace(full,fitted=replace(full.fitted,**{field:values}),new_area_frames=(0,1,2))
            with self.subTest(field=field),self.assertRaisesRegex(ValidationError,'CONTACT_AREAS; source frames 10, 11, 12'):
                require_complete_trunk_fit_guard(self.review)

    def test_per_hand_pair_increase_rejects_even_when_total_pairs_drop(self):
        full=self.review.full_trunk;surface=replace(full.fitted.surface,pairs=((0,2),)*3)
        self.review.full_trunk=replace(full,fitted=replace(full.fitted,surface=surface),more_hand_pair_frames=(0,1,2))
        with self.assertRaisesRegex(ValidationError,'INCREASES_HAND_PAIRS'):require_complete_trunk_fit_guard(self.review)

    def test_hidden_comparison_coverage_or_missing_complete_evidence_rejects(self):
        original=self.review.full_trunk
        cases=[None,replace(original,new_area_frames=(1,)),replace(original,fitted=None),
               replace(original,fitted=replace(original.fitted,body_polygons=original.fitted.body_polygons[:2]))]
        for full in cases:
            self.review.full_trunk=full
            with self.subTest(full=full),self.assertRaises(ValidationError):require_complete_trunk_fit_guard(self.review)

    def test_changed_report_or_fresh_receipt_invalidates_the_guard(self):
        for name in ('private_full_trunk_report','private_anatomical_verification'):
            path=Path(getattr(self.review,name));original=path.read_bytes();path.write_bytes(original+b' changed')
            with self.subTest(path=name),self.assertRaisesRegex(ValidationError,'EVIDENCE_CHANGED'):
                require_complete_trunk_fit_guard(self.review)
            path.write_bytes(original)


if __name__=='__main__':unittest.main()
