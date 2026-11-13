"""Qt publication/invalidation with synthetic geometry; no GPU/Blender claim."""
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import test_desktop_qt as desktop_fixture
from fixtures.motion_skin_contract import write_cache
from ucc.core.errors import ValidationError
from ucc.preview.motion_cache import read_motion_cache

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget
    from PySide6.QtTest import QTest
    from ucc.desktop.native_playback import publish_comparison
except ImportError:
    QWidget=None


@unittest.skipIf(QWidget is None and os.environ.get('UCC_REQUIRE_QT')!='1','Optional PySide6 not installed')
class FittedComparisonQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):desktop_fixture.DesktopQtSmoke.setUpClass()

    def setUp(self):
        self.fixture=desktop_fixture.DesktopQtSmoke();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;f.test_existing_master_refit_button_disabled_until_generated()
        self.w=f.window;root=Path(f.tmp.name);self.source=root/'unit.fbx';self.source.write_bytes(b'not an actual animation')
        files={}
        for name in ('review.blend','source.json','fitted.blend','fit.json','fitted.json'):
            files[name]=root/name;files[name].write_bytes(b'original unit evidence '+name.encode())
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        _,report,bindings,timeline=write_cache(root);cache=read_motion_cache(root,report,bindings,timeline)
        self.preview=SimpleNamespace(source_sha256=digest(self.source),private_visual_review_blend=str(files['review.blend']),
            private_timeline=str(files['source.json']),mapping_profile_used=str(files['fit.json']))
        project=f.controller.require_project();identity={'project_id':project.project_id,'revision':project.revision,
            'master_sha256':digest(f.controller.master_path()),'source_sha256':digest(self.source)}
        fit_preview=SimpleNamespace(verification={'bindings':{'review_sha256':digest(files['review.blend']),
            'timeline_sha256':digest(files['source.json']),'fit_report_sha256':digest(files['fitted.json'])}},
            fit_policy_used=str(files['fit.json']),private_fitted_scene=str(files['fitted.blend']),private_timeline=str(files['fitted.json']))
        self.original=SimpleNamespace(**identity,cache=cache)
        self.fitted=SimpleNamespace(**identity,cache=replace(cache),fit_policy_sha256=digest(files['fit.json']),
            fitted_scene_sha256=digest(files['fitted.blend']),original_preview=self.preview,fitted_preview=fit_preview)
        self.policy=files['fit.json'];pane=self.w.animations
        pane.selected.setText(str(self.source));pane.local_preview_review.setChecked(True);self.w._native_review=self.preview
        self.addCleanup(self.w._clear_native_review)
        class Canvas(QWidget):
            failed=Signal(str)
            def __init__(self,cache,parent):super().__init__(parent);self.cache=cache;self.frame=0
            def release(self):pass
        self.mock=patch('ucc.desktop.motion_viewer.MotionCanvas',Canvas);self.mock.start();self.addCleanup(self.mock.stop)

    def test_publish_pair_and_actual_watched_policy_change_clears_both(self):
        from ucc.jobs.fitted_playback import FittedComparison
        self.w._work_kind='fitted_comparison'
        self.w._job_success(FittedComparison(self.original,self.fitted))
        self.assertIsNotNone(self.w.motion_viewer.comparison)
        self.assertIn(str(self.policy),self.w._motion_watcher.files())
        self.w.motion_viewer.variant.setCurrentIndex(1);self.policy.write_bytes(b'changed policy')
        QTest.qWait(150)
        self.assertIsNone(self.w._native_review);self.assertIsNone(self.w.motion_viewer.cache)
        self.assertIsNone(self.w.motion_viewer.comparison);self.assertIsNone(self.w._native_playback)

    def test_changed_policy_or_permission_never_publishes(self):
        self.policy.write_bytes(b'changed')
        with self.assertRaises(ValidationError):publish_comparison(self.w,self.original,self.fitted)
        self.assertIsNone(self.w.motion_viewer)
        self.w.animations.local_preview_review.setChecked(False)
        with self.assertRaises(ValidationError):publish_comparison(self.w,self.original,self.fitted)

    def test_new_private_job_does_not_invalidate_but_atomic_input_replacement_does(self):
        from ucc.desktop.motion_inputs import directory_changed
        publish_comparison(self.w,self.original,self.fitted)
        root=self.w.controller.store.root
        jobs=root/'.ucc-jobs';jobs.mkdir(exist_ok=True)
        (jobs/'new-private-job').mkdir()
        (root/'unrelated-diagnostic.log').write_text('private diagnostic progress')
        QTest.qWait(150)
        self.assertIs(self.w._native_review,self.preview)
        self.assertIsNotNone(self.w.motion_viewer.comparison)
        # Same bytes at a new identity still count as a replacement. Exercise
        # the parent handler directly as well as actual OS watcher delivery.
        replacement=self.policy.with_name('replacement.json')
        replacement.write_bytes(self.policy.read_bytes())
        # Windows can briefly deny replacement immediately after creating a
        # file (also reproduced locally). Retry only that OS operation; a
        # persistent lock still fails, and every invalidation assertion stays.
        for attempt in range(10):
            try:
                replacement.replace(self.policy)
                break
            except PermissionError as error:
                if os.name!='nt' or error.winerror not in (5,32,33) or attempt==9:
                    raise
                QTest.qWait(20)
        directory_changed(self.w,str(self.policy.parent))
        self.assertIsNone(self.w._native_review)
        self.assertIsNone(self.w.motion_viewer.cache)

    def test_deleted_bound_input_clears_on_parent_event_even_without_file_event(self):
        from ucc.desktop.motion_inputs import directory_changed
        publish_comparison(self.w,self.original,self.fitted)
        self.w._motion_watcher.blockSignals(True)
        self.policy.unlink()
        directory_changed(self.w,str(self.policy.parent))
        self.assertIsNone(self.w._native_review)

    def test_mismatched_original_selection_or_project_never_publishes(self):
        self.original.revision+=1
        with self.assertRaises(ValidationError):publish_comparison(self.w,self.original,self.fitted)
        self.original.revision-=1;self.w._native_review=SimpleNamespace()
        with self.assertRaises(ValidationError):publish_comparison(self.w,self.original,self.fitted)
        self.assertIsNone(self.w.motion_viewer)

    def test_original_checked_crossings_offer_one_defined_local_fit_action(self):
        from ucc.preview.surface_review import SurfaceReview
        from ucc.desktop.native_playback import publish_playback
        surface=SurfaceReview('CHECKED','',((1,),(),()),((1,0),(0,0),(0,0)),('a'*64,)*3)
        self.original.cache=replace(self.original.cache,surface_review=surface)
        with patch('ucc.desktop.contact_fit.start_contact_fit') as start:
            publish_playback(self.w,self.original)
            self.assertTrue(self.w.motion_viewer.try_fit.isEnabled())
            self.w.motion_viewer.try_fit.click();start.assert_called_once_with(self.w)
            self.w.motion_viewer.set_fit_busy(True);self.assertFalse(self.w.motion_viewer.try_fit.isEnabled())


if __name__=='__main__':unittest.main()
