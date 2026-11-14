"""Actual Qt publication/actions with synthetic data; not physical/GPU evidence."""
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import test_fitted_comparison_qt as comparison_fixture
import test_desktop_qt as desktop_fixture
try:
    from PySide6.QtTest import QTest
    from ucc.desktop.body_contact_review import publish_body_contact_review,start_body_contact_review
except ImportError:
    QTest=None

from ucc.core.errors import ValidationError
from ucc.jobs.body_contact_review import BodyContactReview
from ucc.preview.body_contacts import BodyContacts,POLICY
from ucc.preview.surface_review import SurfaceReview


@unittest.skipIf(desktop_fixture.QApplication is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 not installed')
class BodyReviewQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):comparison_fixture.FittedComparisonQtTests.setUpClass()

    def setUp(self):
        self.f=comparison_fixture.FittedComparisonQtTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.w=self.f.w;root=Path(self.f.fixture.tmp.name);digest=lambda p:sha256(p.read_bytes()).hexdigest()
        self.executable=root/'unit-blender';self.executable.write_bytes(b'unit-only-not-program')
        self.report=root/'body_contacts.json';self.report.write_text('{"unit_only":true}')
        snapshot=root/'source_snapshot.json';snapshot.write_text('{"unit_only":true}')
        arm=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,('a'*64,)*3)
        self.f.original.cache=replace(self.f.original.cache,surface_review=arm);self.f.fitted.cache=replace(self.f.fitted.cache,surface_review=arm)
        source=SurfaceReview('CHECKED','',((1,),(),()),((2,0),(0,0),(0,0)),('a'*64,)*3,POLICY)
        fitted=replace(source,pairs=((1,0),(0,0),(0,0)))
        preview=self.f.preview;fp=self.f.fitted.fitted_preview
        bindings={'source_sha256':self.f.original.source_sha256,'master_sha256':self.f.original.master_sha256,
            'snapshot_sha256':digest(snapshot),'mapping_sha256':digest(Path(preview.mapping_profile_used)),
            'timeline_sha256':digest(Path(preview.private_timeline)),'review_sha256':digest(Path(preview.private_visual_review_blend)),
            'fit_sha256':self.f.fitted.fit_policy_sha256,'fitted_sha256':self.f.fitted.fitted_scene_sha256,
            'fit_report_sha256':digest(Path(fp.private_timeline))}
        self.f.original.job_id='unit-original';self.f.fitted.job_id='unit-fitted'
        self.result=BodyContactReview(self.f.original.project_id,self.f.original.revision,self.f.original.master_sha256,
            self.f.original.source_sha256,BodyContacts(source,fitted,()),self.f.original,self.f.fitted,('unit-first','unit-second'),
            str(self.report),digest(self.report),tuple(sorted(bindings.items())),digest(self.w.controller.store.root/'project.ucc.json'))
        pane=self.w.animations;pane.provider.setText('Original unit fixture');pane.license.setText('CC0');pane.uri.setText('original-unit://body-review')
        pane.local_preview_review.setChecked(True)
        self.w._native_review=self.f.preview
        self.error_patch=patch.object(self.w,'_error',side_effect=lambda message:(_ for _ in ()).throw(AssertionError(message)))
        self.error_patch.start();self.addCleanup(self.error_patch.stop)
        from ucc.desktop.native_playback import publish_comparison
        publish_comparison(self.w,self.f.original,self.f.fitted)

    def test_publish_preserves_transport_and_body_report_change_clears_both_scopes(self):
        viewer=self.w.motion_viewer;viewer.seek(1);clock=viewer.clock;viewer.canvas.yaw=.8;viewer.canvas.zoom=2.
        self.w._work_kind='body_contacts';self.w._job_success(self.result)
        self.assertIs(self.w._body_contact_review,self.result);self.assertIs(viewer.clock,clock)
        self.assertEqual(viewer.clock.frame,1);self.assertEqual((viewer.canvas.yaw,viewer.canvas.zoom),(.8,2.))
        self.assertEqual(viewer.inspection.currentIndex(),1);self.assertIn('Hand/body',viewer.surface_status.text())
        self.assertIn(str(self.report),self.w._motion_watcher.files())
        self.report.write_text('changed');QTest.qWait(150)
        self.assertIsNone(viewer.cache);self.assertIsNone(viewer._body_caches)
        self.assertIsNone(self.w._fitted_playback);self.assertIsNone(self.w._body_contact_review)

    def test_changed_metadata_or_visible_buffers_cannot_publish_annotations(self):
        metadata=self.w.controller.store.root/'project.ucc.json';original=metadata.read_bytes();metadata.write_bytes(original+b' ')
        with self.assertRaises(ValidationError):publish_body_contact_review(self.w,self.result)
        self.assertIsNone(self.w.motion_viewer._body_caches);metadata.write_bytes(original)
        other=SimpleNamespace(**vars(self.f.fitted));other.cache=replace(other.cache,packed=b'changed unit buffer')
        with self.assertRaises(ValidationError):publish_body_contact_review(self.w,replace(self.result,fitted_playback=other))

    def test_body_action_dispatches_current_pair_and_cancel_event_without_policy_editing(self):
        self.w._blender_executable=self.executable
        with (patch.object(self.w,'_submit') as submit,patch('ucc.desktop.body_contact_review.bundled_worker_path',return_value=self.executable),
              patch('ucc.desktop.body_contact_review.review_body_contact_areas',return_value='unit-only') as review):
            self.w.motion_viewer.review_body.click();args,kwargs=submit.call_args
            self.assertEqual(args[0],'body_contacts');self.assertEqual(args[1](),'unit-only')
            values=review.call_args.kwargs;self.assertIs(values['fitted'],self.f.fitted)
            self.assertIs(values['cancel'],kwargs['cancel']);self.assertTrue(values['permission'].allow('local_preview')[0])

    def test_unavailable_body_comparison_never_displays_zero_as_a_verdict(self):
        unavailable=SurfaceReview('UNAVAILABLE','SURFACE_WORKLOAD_EXCEEDED',((),)*3,((0,0),)*3,('a'*64,)*3,POLICY)
        result=replace(self.result,contacts=BodyContacts(unavailable,unavailable,None))
        publish_body_contact_review(self.w,result)
        self.assertIn('unavailable',self.w.motion_viewer.surface_status.text())
        self.assertNotIn('0 flagged frames',self.w.motion_viewer.surface_status.text())
        self.assertFalse(self.w.motion_viewer.highlight.isEnabled());self.assertFalse(self.w.motion_viewer.next_flagged.isEnabled())

    def guarded_comparison(self):
        from ucc.preview.contact_areas import BodyContactAreas
        from ucc.jobs.body_fit_guard import require_body_fit_guard
        from ucc.jobs.fitted_playback import FittedComparison
        areas=BodyContactAreas(self.result.contacts,'CHECKED','','a'*64,
            (frozenset({1,2}),frozenset(),frozenset()),(frozenset({1}),frozenset(),frozenset()),(),())
        body=replace(self.result,areas=areas)
        return FittedComparison(self.f.original,self.f.fitted,'unit-candidate','unit-policy',body,require_body_fit_guard(body))

    def test_automatic_fit_requires_guard_before_publication_then_shows_stable_body_review(self):
        from ucc.desktop.contact_fit import publish_fitted_result
        result=self.guarded_comparison()
        with patch('ucc.desktop.native_playback.publish_comparison') as publish:
            with self.assertRaises(ValidationError):publish_fitted_result(self.w,replace(result,body_review=None))
            with self.assertRaises(ValidationError):publish_fitted_result(self.w,replace(result,body_fit_guard=None))
            publish.assert_not_called()
        publish_fitted_result(self.w,result)
        self.assertIs(self.w._body_contact_review,result.body_review)
        self.assertIn('Newly involved contact areas: 0',self.w.log.toPlainText())

    def test_guarded_body_publication_failure_clears_partially_published_comparison(self):
        from ucc.desktop.contact_fit import publish_fitted_result
        result=self.guarded_comparison();metadata=self.w.controller.store.root/'project.ucc.json'
        metadata.write_bytes(metadata.read_bytes()+b' ')
        with self.assertRaises(ValidationError):publish_fitted_result(self.w,result)
        self.assertIsNone(self.w._native_review);self.assertIsNone(self.w.motion_viewer.cache)

    def test_new_stable_contact_area_is_a_plain_rejection_even_when_pairs_decrease(self):
        from ucc.desktop.contact_fit import publish_fitted_result,fit_error_message
        result=self.guarded_comparison();body=result.body_review
        body=replace(body,areas=replace(body.areas,fitted=(frozenset({3}),frozenset(),frozenset()),new_area_frames=(0,)))
        with patch('ucc.desktop.native_playback.publish_comparison') as publish:
            with self.assertRaisesRegex(ValidationError,'BODY_FIT_INTRODUCES_CONTACT_AREAS'):
                publish_fitted_result(self.w,replace(result,body_review=body))
            publish.assert_not_called()
        self.assertIn('new surface areas',fit_error_message('BODY_FIT_INTRODUCES_CONTACT_AREAS; source frames 7'))


if __name__=='__main__':unittest.main()
