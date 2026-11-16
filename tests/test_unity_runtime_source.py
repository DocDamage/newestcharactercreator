"""Closed contracts and fault arithmetic; fixtures do not establish integration."""
from copy import deepcopy
from pathlib import Path
import json,struct,unittest
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec
from ucc.export.unity_runtime_source import recipe,validate_recipe,STAGE,VERIFY,FILES
from ucc.export.unity_runtime_evidence import checked_plan,compare_gpu_record
from ucc.jobs.protocol import JobRequest
from fixtures.unity_contract_logic import request
from fixtures.unity_topology_logic import topology
from fixtures.unity_runtime_logic import source_manifest,vector_buffers


class UnityRuntimeTests(unittest.TestCase):
    def test_published_worker_schemas_preserve_closed_options_and_unverified_scope(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional jsonschema unavailable')
        from ucc.jobs.protocol import JobResult
        from ucc.export.unity_runtime_source import POLICY
        root=Path(__file__).resolve().parents[1]/'docs/schemas'
        job_schema=Draft202012Validator(json.loads((root/'worker-job.v1.schema.json').read_text()))
        result_schema=Draft202012Validator(json.loads((root/'worker-result.v1.schema.json').read_text()))
        for op in (STAGE,VERIFY):
            options={'master_sha256':'a'*64,'recipe_sha256':'b'*64,'bind_reference_sha256':'c'*64}
            if op==VERIFY:options.update({n.replace('.','_')+'_sha256':'d'*64 for n in FILES})
            job=JobRequest.new(op,input_project='candidate.blend',options=options);job_schema.validate(job.as_dict())
            raw=job.as_dict();raw['options']={**options,'extra':True};self.assertTrue(list(job_schema.iter_errors(raw)))
            details={'policy':POLICY,'request_sha256':'a'*64,'files':{n:'b'*64 for n in FILES},'runtime_verified':False}
            if op==VERIFY:details['verification_sha256']='c'*64
            result=JobResult(job.job_id,op,'ok',details).as_dict();result_schema.validate(result)
            result['details']['runtime_verified']=True;self.assertTrue(list(result_schema.iter_errors(result)))

    def test_closed_recipe_and_fixed_job_options(self):
        params=source_manifest()['expression_parameters'];raw=recipe(request(),SkinMaterialSpec((.5,.3,.2),.65),params,'a'*64)
        self.assertEqual(validate_recipe(raw)[0],request())
        options={'master_sha256':'a'*64,'recipe_sha256':'b'*64,'bind_reference_sha256':'c'*64}
        JobRequest.new(STAGE,input_project='candidate.blend',options=options)
        JobRequest.new(VERIFY,input_project='candidate.blend',options={**options,**{n.replace('.','_')+'_sha256':'d'*64 for n in FILES}})
        with self.assertRaises(ValidationError):JobRequest.new(STAGE,input_project='../candidate.blend',options=options)
        for key,value in [('schema_version',True),('extra',True)]:
            changed=deepcopy(raw);changed[key]=value
            with self.assertRaises(ValidationError):validate_recipe(changed)

    def plan(self,raw):
        source=topology()
        return checked_plan(raw,request_sha256='a'*64,master_sha256='b'*64,bind_reference_sha256='d'*64,
            native_mesh_sha256='e'*64,topology_sha256='f'*64,bone_names=source.bone_names,shape_names=source.shape_names)

    def test_full_diagnostic_identity_coverage_and_offsets(self):
        self.assertEqual(len(self.plan(source_manifest())['cases']),178)
        for change in ('offset','bone','shape','scope','neutral'):
            raw=source_manifest()
            if change=='offset':raw['cases'][1]['positions_offset']=0
            elif change=='bone':raw['cases'][1]['bone']=raw['cases'][2]['bone']
            elif change=='shape':raw['cases'][0]['shapes'][0]['value']=.5
            elif change=='scope':raw['runtime_verified']=True
            elif change=='neutral':raw['cases'][-1]['normals_sha256']='a'*64
            with self.assertRaises(ValidationError):self.plan(raw)

    def test_gpu_position_preservation_fixed_position_and_normal_gates(self):
        native,source,normals,ids,matrix=vector_buffers()
        result=compare_gpu_record(native,source,normals,ids,matrix)
        self.assertEqual(result['maximum_source_position_error_m'],0.)
        self.assertEqual(result['maximum_normal_angle_deg'],0.)
        for fault in ('adapter-position','both-positions','normal','nan','truncated'):
            changed=bytearray(native)
            if fault=='adapter-position':struct.pack_into('<f',changed,12,-.249)
            elif fault=='both-positions':
                struct.pack_into('<f',changed,0,-.249);struct.pack_into('<f',changed,12,-.249)
            elif fault=='normal':struct.pack_into('<fff',changed,24,1.,0.,0.)
            elif fault=='nan':struct.pack_into('<f',changed,24,float('nan'))
            else:changed.pop()
            with self.assertRaises(ValidationError):compare_gpu_record(bytes(changed),source,normals,ids,matrix)
