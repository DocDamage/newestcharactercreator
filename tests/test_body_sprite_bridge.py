"""Bridge math/protocol/fault contracts on NONSHIPPING doubles; no Blender claim."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

from blender_bridge.body_sprite_frames import action_state,all_frames,compare_complete,compare_frames,validate_clock
from blender_bridge.body_sprite_scene import union_bounds,_properties
from fixtures.body_sprite_bridge_logic import geometry_record,scene,action_pair
from ucc.core.body_sprites import STAGE,VERIFY,WORKER_FIELDS
from ucc.core.errors import ValidationError
from ucc.jobs.protocol import JobRequest

ROOT=Path(__file__).resolve().parents[1]


class BodySpriteBridgeTests(unittest.TestCase):
    def test_motion_framing_uses_complete_window_union_instead_of_first_pose(self):
        self.assertEqual(union_bounds([((0.,0.,0.),(1.,1.,2.)),((-2.,-.5,-.1),(3.,2.,2.5))]),
                         ((-2.,-.5,-.1),(3.,2.,2.5)))
        for samples in ([],[((0,0,0),(1,1,2))]*33,[((0,0,0),(0,1,2))],[((float('nan'),0,0),(1,1,2))]):
            with self.subTest(samples=len(samples)),self.assertRaises(ValueError):union_bounds(samples)

    def test_clock_does_not_inherit_facial24fps_or_crop_full_action_to_sample(self):
        value=scene();validate_clock(value)
        for field,change in (('fps',24),('fps_base',1.1),('frame_end',32),('frame_start',149),('use_preview_range',True)):
            broken=scene();setattr(broken.render if field in ('fps','fps_base') else broken,field,change)
            with self.subTest(field=field),self.assertRaises(ValueError):validate_clock(broken)

    def test_character_intent_properties_are_bounded_and_finite(self):
        self.assertEqual(_properties({'body':{'height':.5},'flags':[True,'original'] }),{'body':{'height':.5},'flags':[True,'original']})
        for values in ({'height':float('nan')},{'unknown':object()}):
            with self.assertRaises(ValueError):_properties(values)

    def test_full_skin_observation_reaches_unselected_last_frame_and_rejects_fault(self):
        value=scene();api=NS(context=NS(scene=value));record=geometry_record();observed=[]
        timeline={'full_timeline_frames':[{'evaluated_sha256':record['evaluated_sha256'],'target_pose_sha256':record['pose_sha256']} for _ in range(300)]}
        def measure(*unused):observed.append(value.current);return dict(record)
        with patch('blender_bridge.body_sprite_frames.geometry',side_effect=measure):
            actual=all_frames(api,None,None,[],timeline)
        self.assertEqual(observed,list(range(1,301)));compare_complete(actual,[record]*300)
        def corrupted(*unused):return dict(record,positions_sha256='f'*64) if value.current==300 else dict(record)
        with patch('blender_bridge.body_sprite_frames.geometry',side_effect=corrupted):
            corrupted_result=all_frames(api,None,None,[],timeline)
        with self.assertRaises(ValueError):compare_complete(corrupted_result,actual)
        with self.assertRaises(ValueError):all_frames(api,None,None,[],{'full_timeline_frames':timeline['full_timeline_frames'][:32]})

    def test_actual_action_digest_catches_outside_window_key_and_unused_actions(self):
        api,rig,curve=action_pair();before=action_state(api,rig)
        curve.keyframe_points[296].co[1]=.000001
        self.assertNotEqual(action_state(api,rig),before)
        api.data.actions['UNUSED_UNIT_ACTION']=object()
        with self.assertRaises(ValueError):action_state(api,rig)
        api,rig,curve=action_pair();curve.mute=True
        with self.assertRaises(ValueError):action_state(api,rig)

    def test_rehashed_image_report_cannot_replace_independently_observed_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'body-00-0149.png'
            path.write_bytes(b'NONSHIPPING_NOT_A_PNG_OR_RENDER')
            row={'file':path.name,'target_frame':149,'source_frame':150,'rgba_sha256':'a'*64,'geometry':geometry_record(),'sha256':sha256(path.read_bytes()).hexdigest()}
            compare_frames(root,[row],[row])
            changed=deepcopy(row);changed['rgba_sha256']='b'*64
            path.write_bytes(b'NONSHIPPING_REHASHED_REPLACEMENT_NOT_A_RENDER');changed['sha256']=sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):compare_frames(root,[row],[changed])
            escaped=dict(row,file='../outside.png')
            with patch('blender_bridge.body_sprite_frames.digest',side_effect=AssertionError('No arbitrary raster read')):
                with self.assertRaises(ValueError):compare_frames(root,[row],[escaped])

    def test_runtime_and_published_schema_both_require_exact_closed_bindings(self):
        from jsonschema import Draft202012Validator
        validator=Draft202012Validator(json.loads((ROOT/'docs/schemas/worker-job.v1.schema.json').read_text()))
        for operation in (STAGE,VERIFY):
            options={field:'a'*64 for field in WORKER_FIELDS}
            if operation==VERIFY:options.update(scene_sha256='b'*64,stage_sha256='c'*64)
            request=JobRequest.new(operation,input_project='candidate.blend',options=options);validator.validate(request.as_dict())
            for name in options:
                broken=dict(options);broken.pop(name)
                with self.subTest(operation=operation,field=name),self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=broken)
                raw=request.as_dict();raw['options']=broken;self.assertTrue(list(validator.iter_errors(raw)))
            for changed in ({**options,'arbitrary_source_path':'private.blend'},{**options,'master_sha256':True}):
                with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='candidate.blend',options=changed)
            with self.assertRaises(ValidationError):JobRequest.new(operation,input_project='../candidate.blend',options=options)

    def test_source_packaging_closure_contains_body_contract_and_all_bridge_helpers(self):
        from importlib.util import module_from_spec,spec_from_file_location
        from ucc.core.worker_payload import validate_worker_payload
        spec=spec_from_file_location('body_sprite_payload_builder',ROOT/'ci/build_worker_payload.py');builder=module_from_spec(spec);spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory).resolve()/'payload';manifest=builder.build_payload(ROOT,output)
            self.assertIn('ucc.core.body_sprites',manifest['modules'])
            for name in ('body_sprite_workers.py','body_sprite_frames.py','body_sprite_scene.py'):
                self.assertEqual((output/'blender_bridge'/name).read_bytes(),(ROOT/'blender_bridge'/name).read_bytes())
            validate_worker_payload(output)
            contract=output/'worker_support/ucc/core/body_sprites.py';contract.write_bytes(contract.read_bytes()+b'\n# NONSHIPPING corruption\n')
            with self.assertRaises(ValueError):validate_worker_payload(output)


if __name__=='__main__':unittest.main()
