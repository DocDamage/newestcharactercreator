"""Synthetic image/manifest forgery checks, never rendered-animation proof."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from fixtures.contact_fit_contract import fitted_contract,write_render_report,record,fixture
from fixtures.private_render_png import png
from ucc.animations.contact_fit import read_fit_plan
from ucc.jobs.native_fit_renders import verify_fit_renders
from ucc.core.errors import ValidationError


class NativeFitRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.images=[png(phase=i*9) for i in range(5)]

    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.folder=Path(tmp.name)
        self.policy,self.options,self.base,self.profile,self.rest,self.data=fitted_contract()
        self.options['fit_report_sha256']='f'*64
        self.plan=read_fit_plan(*fixture()[:5])
        self.report=write_render_report(self.folder,self.options,self.data,self.images)
        self.path=self.folder/'review_frames/manifest.json';self.manifest=json.loads(self.path.read_text())

    def verify(self):return verify_fit_renders(self.folder,self.report,self.options,self.data,self.base,self.plan)

    def save(self):
        self.path.write_text(json.dumps(self.manifest));self.report['private_review_renders']['manifest']=record(self.path)

    def test_fifteen_bound_bitmaps_decode_with_original_root_camera_trajectory(self):
        self.assertEqual(Path(self.verify()).name,'index.html')

    def test_rehashed_scope_coverage_skin_camera_path_and_extra_fields_reject(self):
        for case in ('scope','approve','count','frames','skin','camera','bool','path','extra'):
            original=deepcopy(self.manifest)
            if case=='scope':self.manifest['scope']='SOURCE_FK_VISUALLY_APPROVED'
            if case=='approve':self.manifest['animation_visual_quality_verified']=True
            if case=='count':self.manifest['source_frame_count']=4
            if case=='frames':self.manifest['rendered_frames']=[1,2,3,4,4]
            if case=='skin':self.manifest['images'][0]['evaluated_sha256']='d'*64
            if case=='camera':self.manifest['images'][0]['camera_root_offset_world']=[.01,0.,0.]
            if case=='bool':self.manifest['images'][0]['frame']=True
            if case=='path':self.manifest['images'][0]['name']='../outside.png'
            if case=='extra':self.manifest['images'][0]['assume_contact_valid']=True
            self.save()
            with self.subTest(case=case),self.assertRaises(ValidationError):self.verify()
            self.manifest=original

    def test_blank_png_rehashed_as_valid_metadata_still_rejects(self):
        image=self.folder/'review_frames/frame_0001_front.png';image.write_bytes(png(blank=True))
        self.manifest['images'][0].update(record(image));self.save()
        with self.assertRaises(ValidationError):self.verify()

    def test_changed_index_and_missing_image_do_not_publish_review_paths(self):
        index=self.folder/'review_frames/index.html';index.write_bytes(b'CHANGED')
        with self.assertRaises(ValidationError):self.verify()
        self.report['private_review_renders']['index']=record(index)
        (self.folder/'review_frames/frame_0001_front.png').unlink()
        with self.assertRaises(ValidationError):self.verify()
