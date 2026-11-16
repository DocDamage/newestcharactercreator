"""Normal stream bounds and per-corner mapping; no model integration claims."""
from dataclasses import replace
from copy import deepcopy
from pathlib import Path
import tempfile,unittest,struct
from ucc.core.errors import ValidationError
from ucc.core.expression_material import STAGE,VERIFY
from ucc.jobs.protocol import JobRequest
from ucc.preview.expression_material import read_material_expression
from fixtures.expression_material_logic import SyntheticExpressionMaterialFixture


class ExpressionMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.f=SyntheticExpressionMaterialFixture(Path(self.tmp.name).resolve())

    def load(self,**kw):
        return read_material_expression(self.f.root,self.f.geometry,self.f.options,self.f.proof,self.f.report,**kw)

    def test_frame_specific_normals_geometry_expansion_and_focus_preserve_source(self):
        cache=self.load();vb,ib=cache.frame(12)
        self.assertEqual(vb[:36],self.f.vertices[12][24:36]+self.f.vertices[12][:12]+self.f.vertices[12][12:24])
        self.assertEqual(ib[:12],struct.pack('<3I',0,1,2));self.assertEqual(cache.frame_normals(12),self.f.raw_normals[12])
        self.assertNotEqual(cache.frame_normals(0),cache.frame_normals(12));self.assertEqual(cache.frame_normals(0),cache.frame_normals(24))
        self.assertEqual(cache.material,self.f.spec);self.assertIs(cache.geometry,self.f.geometry)
        focused=replace(cache,hips=((0.,0.,1.),)*25,radius=.2)
        self.assertEqual(focused.frame(12),cache.frame(12));self.assertEqual(focused.frame_normals(12),cache.frame_normals(12))
        self.assertEqual(len(vb)+len(cache.frame_normals(12)),80268*24)
        for index in (-1,25,False,1.):
            with self.assertRaises(ValidationError):cache.frame_normals(index)

    def test_closed_normal_job_requires_every_original_geometry_binding(self):
        for operation in (STAGE,VERIFY):
            options=dict(self.f.options)
            if operation==STAGE:
                for key in ('normals_sha256','normals_manifest_sha256'):options.pop(key)
            JobRequest.new(operation,input_project='candidate.blend',options=options)
            for key in options:
                bad=dict(options);bad.pop(key)
                with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=bad)
            with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='../outside.blend',options=options)
            with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=options|{'unknown':'a'*64})

    def test_stale_topology_frame_offsets_spec_or_approval_reject(self):
        mutations=[lambda m:m['frames'][0].update(triangles_sha256='f'*64),lambda m:m['frames'][0].update(offset=9),
            lambda m:m['frames'][0].update(frame=True),lambda m:m['material_spec'].update(roughness=.1),
            lambda m:m.update(frame_count=24),lambda m:m.update(visual_quality_approved=True),lambda m:m.update(extra=True)]
        for mutate in mutations:
            self.f.flush(mutate)
            with self.subTest(mutate=mutate),self.assertRaises(ValidationError):self.load()

    def test_coherently_rehashed_nonfinite_or_nonunit_normals_reject(self):
        first=self.f.raw_normals[0]
        for values in [(float('nan'),0.,1.),(0.,0.,0.)]:
            self.f.raw_normals[0]=struct.pack('<3f',*values)+first[12:];self.f.flush()
            with self.assertRaises(ValidationError):self.load()

    def test_wrong_reopen_proof_or_cancel_stops_before_gpu_cache(self):
        self.f.proof['normal_frames']=24
        with self.assertRaises(ValidationError):self.load()
        self.f.flush()
        def cancel():raise ValidationError('UNIT cancellation')
        with self.assertRaisesRegex(ValidationError,'cancellation'):self.load(cancel_check=cancel)

    def test_documented_job_and_result_schemas_keep_normal_contract_closed(self):
        import json
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('Optional jsonschema not installed')
        from ucc.jobs.protocol import JobResult
        from ucc.core.expression_material import POLICY
        directory=Path(__file__).resolve().parents[1]/'docs/schemas'
        jobs=Draft202012Validator(json.loads((directory/'worker-job.v1.schema.json').read_text()))
        results=Draft202012Validator(json.loads((directory/'worker-result.v1.schema.json').read_text()))
        for operation in (STAGE,VERIFY):
            options=dict(self.f.options)
            if operation==STAGE:
                options.pop('normals_sha256');options.pop('normals_manifest_sha256')
                detail={'schema_version':1,'policy':POLICY,'bindings':self.f.base,'owned_material_spec':self.f.spec.to_dict(),
                    'normals_sha256':self.f.options['normals_sha256'],'normals_manifest_sha256':self.f.options['normals_manifest_sha256'],
                    'frame_count':25,'visual_quality_approved':False,'engine_import_verified':False}
            else:detail=self.f.proof
            request=JobRequest.new(operation,input_project='candidate.blend',options=options);jobs.validate(request.as_dict())
            record=JobResult(request.job_id,operation,'ok',detail).as_dict();results.validate(record)
            bad=deepcopy(request.as_dict());bad['options']['extra']='a'*64;self.assertTrue(list(jobs.iter_errors(bad)))
            bad=deepcopy(record);bad['details']['visual_quality_approved']=True;self.assertTrue(list(results.iter_errors(bad)))

    def test_frame_label_reserves_width_for_the_complete_clip(self):
        import test_expression_desktop as desktop
        if desktop.QApplication is None:self.skipTest('Optional PySide6 unavailable')
        from ucc.desktop.expression_viewer import ExpressionViewer
        app=desktop.QApplication.instance() or desktop.QApplication([])
        viewer=ExpressionViewer();self.addCleanup(viewer.close)
        self.assertGreaterEqual(viewer.position.minimumWidth(),viewer.position.fontMetrics().horizontalAdvance('Frame 25 / 25'))
        viewer.position.setText('Frame 1 / 25');first=viewer.position.minimumSizeHint().width()
        viewer.position.setText('Frame 25 / 25');self.assertGreaterEqual(viewer.position.minimumWidth(),max(first,viewer.position.minimumSizeHint().width()))
