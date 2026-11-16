"""Coverage/provenance/malformed-data guards; fixtures never certify engine output."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import struct,tempfile
import unittest
from unittest.mock import patch

from fixtures.godot_sampling_logic import sample_report
from ucc.core.errors import ValidationError
from ucc.export.godot_native_samples import interaction_cases,validate_sample_report,OPERATION,POLICY
from ucc.export.godot_native_recipe import INPUTS
from ucc.jobs.godot_native_sampling import validate_reference_stream,sample_native_runtime_interactions
from ucc.jobs.protocol import JobRequest


class NativeSamplingTests(unittest.TestCase):
    def validate(self,raw):
        return validate_sample_report(raw,request_sha256='a'*64,production_sha256='b'*64,recipe_sha256='c'*64,verification_sha256='d'*64)

    def test_coverage_includes_every_integer_three_interval_samples_and_all_facial_profiles(self):
        cases=interaction_cases();counts=Counter(r['profile'] for r in cases)
        self.assertEqual(len(cases),2697)
        self.assertEqual(counts,{'neutral_integer':300,'temporal_neutral_face':897,'face_eye_left_closure':300,
            'face_eye_right_closure':300,'face_mouth_corners':300,'face_mouth_open':300,'face_all_roles':300})
        for profile in counts:
            group=[r for r in cases if r['profile']==profile]
            if profile=='temporal_neutral_face':
                self.assertEqual({(r['frame'],r['subframe']) for r in group},{(i,s) for i in range(1,300) for s in (.25,.5,.75)})
            else:self.assertEqual([r['frame'] for r in group],list(range(1,301)))
        self.assertEqual(len({(r['profile'],r['frame'],r['subframe']) for r in cases}),2697)

    def test_report_preserves_actual_nonunit_race_sum_and_unapproved_flags(self):
        raw=sample_report();checked=self.validate(raw)
        self.assertEqual(checked['race_mix'],{'african':.33,'asian':.33,'caucasian':.33})
        self.assertFalse(checked['engine_import_verified']);self.assertFalse(checked['distribution_license_review_complete'])

    def test_missing_reordered_changed_cases_or_source_hashes_cannot_be_relabelled(self):
        mutations=[lambda r:r['cases'].pop(),lambda r:r['cases'].reverse(),lambda r:r['cases'][0].update(frame=2),
            lambda r:r['cases'][300].update(subframe=.2),lambda r:r.update(request_sha256='0'*64),
            lambda r:r.update(production_receipt_sha256='0'*64),lambda r:r.update(samples=True),
            lambda r:r.update(engine_import_verified=True),lambda r:r.update(extra=True),
            lambda r:r['files']['expected_vec4.f32'].update(bytes=16),lambda r:r['views'][0].update(size=0.),
            lambda r:r['race_mix'].update(asian=float('nan'))]
        for mutation in mutations:
            raw=sample_report();mutation(raw)
            with self.subTest(mutation=mutation),self.assertRaises(ValidationError):self.validate(raw)

    def test_reference_stream_rejects_nonfinite_wrong_homogeneous_nonunit_and_partial_records(self):
        with tempfile.TemporaryDirectory() as tmp,patch('ucc.jobs.godot_native_sampling.REFERENCE_BYTES',16):
            path=Path(tmp)/'UNIT_FLOAT_RECORD_NOT_MODEL.f32'
            for values,normal,valid in [((1.,2.,3.,1.),False,True),((0.,0.,1.,0.),True,True),
                ((0.,0.,2.,0.),True,False),((0.,0.,1.,1.),True,False),((float('nan'),0.,0.,1.),False,False),
                ((101.,0.,0.,1.),False,False)]:
                path.write_bytes(struct.pack('<4f',*values))
                if valid:validate_reference_stream(path,normal=normal,check=lambda:None)
                else:
                    with self.assertRaises(ValidationError):validate_reference_stream(path,normal=normal,check=lambda:None)
            path.write_bytes(b'UNIT_PARTIAL')
            with self.assertRaises(ValidationError):validate_reference_stream(path,normal=False,check=lambda:None)

    def test_new_worker_job_and_success_error_schemas_are_closed(self):
        from jsonschema import Draft202012Validator
        root=Path(__file__).resolve().parents[1]/'docs/schemas'
        job_validator=Draft202012Validator(json.loads((root/'worker-job.v1.schema.json').read_text()))
        result_validator=Draft202012Validator(json.loads((root/'worker-result.v1.schema.json').read_text()))
        fields=set(INPUTS.values())|{'native_recipe_sha256','native_stage_sha256','native_verification_sha256','runtime_request_sha256','production_receipt_sha256'}
        request=JobRequest.new(OPERATION,input_project='candidate.blend',options={name:'a'*64 for name in fields}).as_dict();job_validator.validate(request)
        for name in fields:
            broken=deepcopy(request);broken['options'].pop(name)
            with self.assertRaises(ValidationError):JobRequest.from_dict(broken)
            self.assertTrue(list(job_validator.iter_errors(broken)))
        result={'protocol_version':1,'job_id':request['job_id'],'operation':OPERATION,'status':'ok','error':None,
            'details':{'policy':POLICY,'status':'FRESH_NATIVE_INTERACTION_REFERENCES_MEASURED','native_samples_sha256':'a'*64,'sample_count':2697,'engine_import_verified':False}}
        result_validator.validate(result);result['details']['sample_count']=2397
        self.assertTrue(list(result_validator.iter_errors(result)))
        result.update(status='error',details={},error='UNIT_FAILURE');result_validator.validate(result)

    def test_invalid_source_object_or_total_timeout_reject_before_worker_or_filesystem_access(self):
        for timeout in [True,float('nan'),-.1,3601]:
            with self.assertRaises(ValidationError):sample_native_runtime_interactions(None,None,produced=None,source_fbx=None,authorized_source_root=None,timeout_s=timeout)


if __name__=='__main__':unittest.main()
