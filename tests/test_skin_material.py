"""Explicit parameter/color and closed recipe/protocol checks; no fake rendering."""
from copy import deepcopy
from dataclasses import replace
import json,math,tempfile,unittest
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.core.skin_material import SkinMaterialSpec,material_recipe,validate_material_recipe,RECIPE_POLICY
from ucc.jobs.protocol import JobRequest
from fixtures.skin_material_logic import MaterialFixture


class SkinMaterialTests(unittest.TestCase):
    def test_explicit_srgb_to_linear_and_closed_round_trip(self):
        spec=SkinMaterialSpec((0,.5,1),.62)
        self.assertEqual(spec.linear_rgba[0],0.);self.assertAlmostEqual(spec.linear_rgba[1],.21404114048223255)
        self.assertEqual(spec.linear_rgba[2:],(1.,1.));self.assertEqual(SkinMaterialSpec.from_dict(spec.to_dict()),spec)
        self.assertFalse(spec.to_dict()['textures']);self.assertEqual(len(spec.sha256),64)

    def test_invalid_parameters_unknown_fields_and_asset_reference_reject(self):
        for rgb,rough in [(None,.5),([.5,.5,.5],.5),((.5,.5),.5),((True,0.,0.),.5),((float('nan'),0.,0.),.5),
            ((1.1,0.,0.),.5),((0.,0.,0.),True),((0.,0.,0.),float('inf')),((0.,0.,0.),-1)]:
            with self.subTest(rgb=rgb,rough=rough),self.assertRaises(ValidationError):SkinMaterialSpec(rgb,rough)
        spec=SkinMaterialSpec((.5,.5,.5),.5)
        for change in ({'textures':True},{'alpha':.5},{'texture_path':'private.png'},{'metallic':1.},{'policy':'unknown'}):
            raw={**spec.to_dict(),**change}
            with self.assertRaises(ValidationError):SkinMaterialSpec.from_dict(raw)

    def test_recipe_preserves_part_expression_and_source_bindings_without_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=MaterialFixture(Path(tmp).resolve());from hashlib import sha256
            sources={name:sha256(path.read_bytes()).hexdigest() for name,path in f.sources.items()}
            recipe=material_recipe(f.project,'a'*64,sources,f.spec)
            self.assertEqual(validate_material_recipe(recipe),recipe)
            self.assertEqual(recipe['project_snapshot'],f.project.to_dict());self.assertFalse(recipe['project_publication_authorized'])
            for field in ('cloud_transmission_authorized','source_rights_changed','engine_import_verified'):
                broken=deepcopy(recipe);broken[field]=True
                with self.assertRaises(ValidationError):validate_material_recipe(broken)
            broken=deepcopy(recipe);broken['source_bindings'].pop('part:'+f.part.part_asset_id)
            with self.assertRaises(ValidationError):validate_material_recipe(broken)

    def test_job_and_result_schemas_close_all_hashes_and_keep_errors_admissible(self):
        from jsonschema import Draft202012Validator
        root=Path(__file__).resolve().parents[1]/'docs/schemas'
        jobs=Draft202012Validator(json.loads((root/'worker-job.v1.schema.json').read_text()))
        results=Draft202012Validator(json.loads((root/'worker-result.v1.schema.json').read_text()))
        for op in ('stage_mpfb_skin_material','verify_mpfb_skin_material'):
            fields={'master_sha256','recipe_sha256'}|({'material_master_sha256','stage_report_sha256','glb_sha256'} if op.startswith('verify') else set())
            job=JobRequest.new(op,input_project='candidate.blend',options={name:'a'*64 for name in fields});jobs.validate(job.as_dict())
            for field in fields:
                raw=job.as_dict();raw['options']=dict(raw['options']);raw['options'].pop(field)
                with self.assertRaises(ValidationError):JobRequest.from_dict(raw)
                self.assertTrue(list(jobs.iter_errors(raw)))
            proof='verification_sha256' if op.startswith('verify') else 'stage_report_sha256'
            record={'protocol_version':1,'job_id':job.job_id,'operation':op,'status':'ok','error':None,
                'details':{'policy':RECIPE_POLICY,proof:'a'*64,'material_master_sha256':'b'*64,'glb_sha256':'c'*64,'engine_import_verified':False}}
            results.validate(record);record['details']['engine_import_verified']=True
            self.assertTrue(list(results.iter_errors(record)));record.update(status='error',error='UNIT_FAILURE',details={});results.validate(record)


if __name__=='__main__':unittest.main()
