"""Closed native producer boundary tests; synthetic fixtures are not MPFB proof."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.godot_native_logic import export_double,stage_report
from fixtures.godot_runtime_logic import RuntimeTransactionFixture
from test_expression_contracts import prepared,source_project
from blender_bridge.godot_outputs import export_glb
from ucc.core.errors import ValidationError,ProjectStorageError
from ucc.export.godot_candidate_contract import EngineInputPermission,canonical_bytes
from ucc.export.godot_native_recipe import build_native_recipe,validate_native_recipe,INPUTS
from ucc.export.godot_runtime_contract import CODE_FILES,CAPABILITY
from ucc.jobs.godot_native_producer import _report,produce_private_native_runtime_inputs
from ucc.jobs.godot_runtime_bundle import retain_private_native_runtime_inputs
from ucc.jobs.protocol import JobRequest
from ucc.library.provenance import LicensePolicy,AssetPolicyError


class NativeRecipeTests(unittest.TestCase):
    def setUp(self):
        self.project=prepared(source_project(hand=True),hand=True)
        self.sources={'master':'e'*64,'expression_library':'d'*64,'motion:unit':'f'*64,
            'part:'+self.project.parts[0].part_asset_id:'c'*64}
        self.policy=LicensePolicy('unit-only','Contract fixture only','unit-test://not-an-asset',
            reviewed=True,no_ai=True,can_use_non_unreal=True)
        self.permissions=tuple(EngineInputPermission(name,value,self.policy,False) for name,value in self.sources.items())
        self.evidence={name:'b'*64 for name in ['native_review','native_timeline','source_snapshot','native_mapping']}
        self.code={name:'a'*64 for name in CODE_FILES}

    def build(self,**changes):
        kwargs={'project':self.project,'project_file_sha256':'1'*64,'source_bindings':self.sources,
            'evidence_bindings':self.evidence,'implementation':self.code,'permissions':self.permissions,
            'motion_asset_id':'motion:unit','capability':CAPABILITY}
        return build_native_recipe(**{**kwargs,**changes})

    def test_roundtrip_binds_master_snapshot_original_sources_and_private_implementation(self):
        raw=self.build();self.assertEqual(validate_native_recipe(raw),raw)
        self.assertEqual(raw['timeline'],{'first_frame':1,'last_frame':300,'fps':30})
        for name in ['engine_import_verified','visual_quality_approved','distribution_license_review_complete',
            'source_redistribution_authorized','cloud_transmission_authorized']:self.assertIs(raw[name],False)

    def test_recipe_cannot_change_role_timeline_project_implementation_or_approval(self):
        mutations=[lambda x:x.update(extra=True),lambda x:x.update(schema_version=True),
            lambda x:x['timeline'].update(last_frame=25),lambda x:x.update(engine_import_verified=True),
            lambda x:x.update(distribution_license_review_complete=True),lambda x:x.update(source_role='ARBITRARY_SCENE'),
            lambda x:x.update(requested_capability='gl_compatibility'),lambda x:x.update(project_snapshot_sha256='0'*64),
            lambda x:x['evidence_bindings'].pop('source_snapshot'),lambda x:x['implementation'].update(extra='a'*64)]
        for change in mutations:
            with self.subTest(change=change):
                raw=deepcopy(self.build());change(raw)
                with self.assertRaises(ValidationError):validate_native_recipe(raw)

    def test_permissions_cover_exact_content_and_do_not_remove_noai(self):
        for permissions in [self.permissions[:-1],self.permissions+(self.permissions[0],),
            (replace(self.permissions[0],source_only=True),*self.permissions[1:]),
            (replace(self.permissions[0],source_sha256='0'*64),*self.permissions[1:])]:
            with self.assertRaises((ValidationError,AssetPolicyError)):self.build(permissions=permissions)
        changed=tuple(replace(p,policy=replace(p.policy,no_ai=False)) if p.asset_id=='expression_library' else p for p in self.permissions)
        with self.assertRaises(ValidationError):self.build(permissions=changed)
        with self.assertRaises(ValidationError):self.build(motion_asset_id=[])

    def test_worker_protocol_and_published_schema_require_every_fixed_hash(self):
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        for operation in ['stage_native_godot_runtime','verify_native_godot_runtime']:
            options={name:'a'*64 for name in set(INPUTS.values())|{'native_recipe_sha256'}}
            if operation.startswith('verify'):options['native_stage_sha256']='b'*64
            raw=JobRequest.new(operation,input_project='candidate.blend',options=options).as_dict();validator.validate(raw)
            for field in options:
                broken=deepcopy(raw);broken['options'].pop(field)
                with self.assertRaises(ValidationError):JobRequest.from_dict(broken)
                self.assertTrue(list(validator.iter_errors(broken)))
            for field,value in [('unexpected','a'*64),('source_sha256',True)]:
                broken=deepcopy(raw);broken['options'][field]=value
                with self.assertRaises(ValidationError):JobRequest.from_dict(broken)
                self.assertTrue(list(validator.iter_errors(broken)))

    def test_native_export_can_disable_optimization_without_changing_v1_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index,option in enumerate([None,False]):
                root=Path(tmp)/str(index);root.mkdir();bpy,human,rig,calls=export_double(root)
                kwargs={} if option is None else {'optimize_animation':option}
                export_glb(bpy,root,human,rig,**kwargs)
                self.assertIs(calls[0]['export_optimize_animation_size'],option is None)
            bpy,human,rig,calls=export_double(Path(tmp))
            for option in [0,1,None,'False']:
                with self.assertRaises(ValueError):export_glb(bpy,Path(tmp),human,rig,optimize_animation=option)
            self.assertEqual(calls,[])

    def test_static_material_export_avoids_sparse_morphs_without_altering_native_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            default=root/'default';default.mkdir();bpy,human,rig,calls=export_double(default)
            export_glb(bpy,default,human,rig)
            self.assertTrue(calls[0]['export_animations'])
            self.assertNotIn('export_try_sparse_sk',calls[0])
            static=root/'static';static.mkdir();bpy,human,rig,calls=export_double(static)
            export_glb(bpy,static,human,rig,include_animation=False,dense_morphs=True)
            self.assertFalse(calls[0]['export_animations'])
            self.assertFalse(calls[0]['export_try_sparse_sk'])
            for field in ('include_animation','dense_morphs'):
                bpy,human,rig,calls=export_double(root)
                with self.assertRaises(ValueError):export_glb(bpy,root,human,rig,**{field:1})
                self.assertEqual(calls,[])

    def test_published_result_schema_closes_native_success_without_rejecting_errors(self):
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-result.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        for operation,status,field in [('stage_native_godot_runtime','REAL_NATIVE_RUNTIME_SOURCE_STAGED_NOT_ENGINE_VERIFIED','native_stage_sha256'),
            ('verify_native_godot_runtime','FRESH_NATIVE_RUNTIME_SOURCE_AND_SAVED_OUTPUT_VERIFIED','native_verification_sha256')]:
            raw={'protocol_version':1,'job_id':'01234567-1234-4567-8901-0123456789ab','operation':operation,'status':'ok','error':None,
                'details':{'policy':'MPFB_NATIVE_RUNTIME_SOURCE_V1','status':status,field:'a'*64,'frame_count':300,'engine_import_verified':False}}
            validator.validate(raw)
            for key,value in [('frame_count',299),('engine_import_verified',True),('extra_approval',True)]:
                changed=deepcopy(raw);changed['details'][key]=value;self.assertTrue(list(validator.iter_errors(changed)))
            raw.update(status='error',details={},error='UNIT_FAILURE_NOT_ENGINE_EVIDENCE');validator.validate(raw)

    def test_source_report_rejects_omissions_nonfinite_errors_and_new_approvals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=root/'native_stage.json'
            raw=stage_report('a'*64);path.write_bytes(canonical_bytes(raw))
            _report(root,path.name,sha256(path.read_bytes()).hexdigest(),'a'*64,raw['status'],lambda:None)
            mutations=[lambda x:x.update(extra=True),lambda x:x.update(schema_version=True),
                lambda x:x['frames'].pop(),lambda x:x['frames'][0].update(raw_error_m=.0000011),
                lambda x:x.update(engine_import_verified=True),lambda x:x['morphs'].update(canonical_morphs_verified=11),
                lambda x:x.update(max_serialized_weight_error=.0000011),lambda x:x.update(raw_copy_weight_policy='NORMALIZED_APPROXIMATION')]
            for change in mutations:
                changed=deepcopy(raw);change(changed);path.write_bytes(canonical_bytes(changed))
                with self.assertRaises(ValidationError):_report(root,path.name,sha256(path.read_bytes()).hexdigest(),'a'*64,raw['status'],lambda:None)

    def test_external_source_guard_runs_under_final_commit_lock_and_blocks_retention(self):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            fixture=RuntimeTransactionFixture(Path(tmp).resolve());calls=[]
            stack.enter_context(patch('ucc.jobs.godot_runtime_bundle.project_sources',return_value={'master':fixture.master}))
            stack.enter_context(patch('ucc.jobs.godot_runtime_bundle.validate_runtime_files',return_value={'UNIT_ONLY':True}))
            def guard():
                locked=(fixture.store.root/'.project.ucc.lock').exists();calls.append(locked)
                if locked:raise ProjectStorageError('UNIT original source changed at final lock')
            with self.assertRaisesRegex(ProjectStorageError,'original source changed'):
                retain_private_native_runtime_inputs(fixture.store,fixture.request,**fixture.kwargs(),source_guard=guard)
            self.assertTrue(calls[-1]);self.assertFalse((fixture.store.root/'.ucc-candidates/godot-runtime-inputs'/fixture.request.job_id).exists())
            self.assertEqual(fixture.store.file.read_bytes(),fixture.original_metadata)


if __name__=='__main__':unittest.main()
