"""Closed sprite requests, explicit rights and bounded cameras; no model fixtures."""
from copy import deepcopy
from dataclasses import replace
import unittest
from ucc.core.errors import ValidationError
from ucc.core.sprite_render import SpriteRenderRequest,SpritePermission,SpriteSettings,STAGE,VERIFY
from ucc.jobs.protocol import JobRequest
from fixtures.sprite_render_logic import request


class SpriteRenderContractTests(unittest.TestCase):
    def test_closed_roundtrip_no_approval_or_capability_upgrade(self):
        original=request();self.assertEqual(SpriteRenderRequest.from_dict(original.to_dict()),original)
        for key,value in [('animation_clips',True),('visual_quality_approved',True),('distribution_license_review_complete',True),('extra',1)]:
            raw=deepcopy(original.to_dict());raw[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):SpriteRenderRequest.from_dict(raw)
        raw=original.to_dict();raw['permissions'][0]['ai_input_allowed']=True
        with self.assertRaises(ValidationError):SpriteRenderRequest.from_dict(raw)

    def test_every_source_needs_exact_separate_render_grant_and_NoAI(self):
        original=request();permission=original.permissions[0]
        for change in ({'reviewed':False},{'private_sprite_render_allowed':False},{'no_ai':False},{'ue_only':True},{'redistribute_source_allowed':True},{'authorization':'  '}):
            with self.subTest(change=change),self.assertRaises(ValidationError):replace(permission,**change)
        with self.assertRaises(ValidationError):replace(original,permissions=original.permissions[:-1])
        with self.assertRaises(ValidationError):replace(original,permissions=(replace(permission,source_sha256='f'*64),*original.permissions[1:]))
        with self.assertRaises(ValidationError):replace(original,source_bindings=(*original.source_bindings[:-1],original.source_bindings[0]))

    def test_camera_budget_and_finite_angles(self):
        self.assertEqual(SpriteSettings(128,8,-45,15).angles(),(315,0,45,90,135,180,225,270))
        for kwargs in ({'resolution':True},{'resolution':1024},{'directions':16},{'yaw_deg':float('nan')},{'pitch_deg':31},{'pitch_deg':True}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValidationError):SpriteSettings(**kwargs)

    def test_worker_paths_and_hash_fields_are_closed(self):
        options={'master_sha256':'a'*64,'recipe_sha256':'b'*64}
        JobRequest.new(STAGE,input_project='candidate.blend',options=options)
        with self.assertRaises(ValidationError):JobRequest.new(STAGE,input_project='other.blend',options=options)
        with self.assertRaises(ValidationError):JobRequest.new(STAGE,input_project='candidate.blend',options={**options,'path':'C:/outside'})
        with self.assertRaises(ValidationError):JobRequest.new(VERIFY,input_project='candidate.blend',options=options)
        JobRequest.new(VERIFY,input_project='candidate.blend',options={**options,'scene_sha256':'c'*64,'stage_sha256':'d'*64})

    def test_published_job_schema_matches_closed_worker_options(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional jsonschema not installed')
        import json
        from pathlib import Path
        schema=json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        for op,fields in ((STAGE,('master_sha256','recipe_sha256')),(VERIFY,('master_sha256','recipe_sha256','scene_sha256','stage_sha256'))):
            data=JobRequest.new(op,input_project='candidate.blend',options={k:'a'*64 for k in fields}).as_dict();validator.validate(data)
            data['options']['extra']='not a path grant';self.assertTrue(list(validator.iter_errors(data)))
