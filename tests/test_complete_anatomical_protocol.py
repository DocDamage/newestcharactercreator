"""Closed three-report operation metadata; no physical animation evidence."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

from blender_bridge.complete_anatomical_review import OPERATIONS,checked_complete_job,CompleteInspector,inspect_complete
from ucc.jobs.protocol import JobRequest
from ucc.core.errors import ValidationError


class CompleteAnatomicalProtocolTests(unittest.TestCase):
    def test_oversized_third_report_creates_none_of_the_three_outputs(self):
        limits={'body_contacts.json':('body_review_sha256',64),'central_enclosure.json':('enclosure_review_sha256',64),
                'full_trunk_contacts.json':('full_trunk_review_sha256',64)}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);original=folder/'protected-original.blend';original.write_bytes(b'nonshipping sentinel')
            with patch('blender_bridge.complete_anatomical_review.REPORTS',limits),\
                 patch('blender_bridge.complete_anatomical_review.require_unchanged'),\
                 patch('blender_bridge.complete_anatomical_review.measure_complete',return_value=({}, {}, {'large':'x'*100})),\
                 self.assertRaisesRegex(ValueError,'bounded size'):
                inspect_complete(None,folder,{})
            self.assertEqual({p.name for p in folder.iterdir()},{original.name})
            self.assertEqual(original.read_bytes(),b'nonshipping sentinel')

    def test_existing_complete_report_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);report=folder/'full_trunk_contacts.json';report.write_bytes(b'original receipt')
            with patch('blender_bridge.complete_anatomical_review.measure_complete') as measure,\
                 self.assertRaisesRegex(ValueError,'Refuse to replace'):
                inspect_complete(None,folder,{})
            measure.assert_not_called();self.assertEqual(report.read_bytes(),b'original receipt')

    def test_cumulative_highlight_budget_rejects_before_retaining_a_later_frame(self):
        inspector=CompleteInspector.__new__(CompleteInspector)
        inspector.complete_rows=[];inspector.complete_highlights=0
        inspector.enclosure_rows=[{'observation':{'body_triangle_ids':[1]}}]
        observation={'body_triangle_ids':[1],
            'left':{'hand_triangles':[2],'central_triangles':[1]},
            'right':{'hand_triangles':[],'central_triangles':[]}}
        with patch('blender_bridge.complete_anatomical_review.MAX_HIGHLIGHTS',3):
            inspector._record(1,'a'*64,'b'*64,observation)
            with self.assertRaisesRegex(ValueError,'HIGHLIGHTS'):inspector._record(2,'a'*64,'b'*64,observation)
        self.assertEqual(len(inspector.complete_rows),1);self.assertEqual(inspector.complete_highlights,2)

    def test_each_stage_has_exact_source_fit_and_three_report_hashes(self):
        for operation,fields in OPERATIONS.items():
            options={k:'a'*64 for k in fields}
            job=JobRequest.new(operation,input_project='candidate.blend',options=options).as_dict()
            self.assertEqual(checked_complete_job(job),options)
            for fault in ('missing','extra','weak_hash','bool','path'):
                bad=deepcopy(job)
                if fault=='missing':bad['options'].pop(next(iter(fields)))
                if fault=='extra':bad['options']['skip_surface_check']=True
                if fault=='weak_hash':bad['options']['source_sha256']='a'*63
                if fault=='bool':bad['options']['source_sha256']=True
                if fault=='path':bad['input_project']='original.blend'
                with self.subTest(operation=operation,fault=fault):
                    with self.assertRaises(ValueError):checked_complete_job(bad)
                    with self.assertRaises(ValidationError):JobRequest.from_dict(bad)
            if operation.startswith('verify_'):
                for name in ('body_review_sha256','enclosure_review_sha256','full_trunk_review_sha256'):
                    bad=deepcopy(job);bad['options'].pop(name)
                    with self.subTest(operation=operation,missing_report=name),self.assertRaises(ValueError):checked_complete_job(bad)

    def test_schema_closes_every_new_operation_and_report_identity(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        path=Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json'
        validator=Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))
        for operation,fields in OPERATIONS.items():
            job=JobRequest.new(operation,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict()
            validator.validate(job)
            for key in fields:
                bad=deepcopy(job);bad['options'].pop(key)
                self.assertTrue(list(validator.iter_errors(bad)))
            job['options']['allow_partial']=True;self.assertTrue(list(validator.iter_errors(job)))


if __name__=='__main__':unittest.main()
