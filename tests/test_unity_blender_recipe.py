"""Strict worker boundary; these scalar hashes are not engine or Blender evidence."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.unity_blender_recipe import recipe,validate_recipe,validate_job,STAGE,VERIFY,FILES,POLICY
from ucc.jobs.protocol import JobRequest,JobResult
from fixtures.unity_contract_logic import request


class UnitySourceRecipeTests(unittest.TestCase):
    def test_published_worker_schemas_reject_scope_and_hash_forgery(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional jsonschema unavailable')
        folder=Path(__file__).resolve().parents[1]/'docs/schemas'
        job_schema=Draft202012Validator(json.loads((folder/'worker-job.v1.schema.json').read_text()))
        result_schema=Draft202012Validator(json.loads((folder/'worker-result.v1.schema.json').read_text()))
        for op in (STAGE,VERIFY):
            options={'master_sha256':'a'*64,'recipe_sha256':'b'*64}
            if op==VERIFY:options.update({n.replace('.','_')+'_sha256':'c'*64 for n in FILES})
            job=JobRequest.new(op,input_project='candidate.blend',options=options)
            job_schema.validate(job.as_dict())
            for field in options:
                raw=job.as_dict();raw['options']={**options,field:True}
                self.assertTrue(list(job_schema.iter_errors(raw)))
            details={'policy':POLICY,'request_sha256':'d'*64,'files':{n:'e'*64 for n in FILES},'engine_import_verified':False}
            if op==VERIFY:details['verification_sha256']='f'*64
            result=JobResult(job.job_id,op,'ok',details).as_dict();result_schema.validate(result)
            for changed in ({'engine_import_verified':True},{'extra':True},{'files':{}}):
                raw=deepcopy(result);raw['details'].update(changed)
                self.assertTrue(list(result_schema.iter_errors(raw)))

    def test_recipe_roundtrip_and_stage_verify_protocol(self):
        value=recipe(request(),SkinMaterialSpec((.5,.3,.2),.65))
        self.assertEqual(validate_recipe(value)[0],request())
        options={'master_sha256':'a'*64,'recipe_sha256':'b'*64}
        JobRequest.new(STAGE,input_project='candidate.blend',options=options)
        JobRequest.new(VERIFY,input_project='candidate.blend',options={**options,**{n.replace('.','_')+'_sha256':'c'*64 for n in FILES}})

    def test_paths_unknown_fields_incomplete_hashes_and_scope_promotion_reject(self):
        options={'master_sha256':'a'*64,'recipe_sha256':'b'*64}
        for op,path,changes in [(STAGE,'../source.blend',{}),(VERIFY,'candidate.blend',{}),(STAGE,'candidate.blend',{'extra':True}),
                                (STAGE,'candidate.blend',{'master_sha256':True})]:
            with self.assertRaises(ValidationError):validate_job(op,path,{**options,**changes})
        value=recipe(request(),SkinMaterialSpec((.5,.3,.2),.65))
        for key,v in [('schema_version',True),('policy','other'),('extra',True)]:
            raw=deepcopy(value);raw[key]=v
            with self.assertRaises(ValidationError):validate_recipe(raw)
        value['export_request']['engine_import_verified']=True
        with self.assertRaises(ValidationError):validate_recipe(value)
