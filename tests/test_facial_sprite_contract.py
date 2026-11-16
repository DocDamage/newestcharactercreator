"""Closed animated source/clip identity and job admission; no render assertions."""
from copy import deepcopy
from dataclasses import replace
import unittest
from ucc.core.errors import ValidationError
from ucc.core.facial_sprites import FacialSpriteRequest,STAGE,VERIFY,TARGET_BINDINGS
from ucc.core.sprite_render import canonical,SpriteRenderRequest
from ucc.jobs.protocol import JobRequest
from fixtures.facial_sprite_logic import request


class FacialSpriteContractTests(unittest.TestCase):
    def test_immutable_clip_and_closed_roundtrip_keep_neutral_separate(self):
        r=request();self.assertEqual(FacialSpriteRequest.from_dict(r.to_dict()),r)
        with self.assertRaises(ValidationError):SpriteRenderRequest.from_dict(r.to_dict())
        copy=r.clip;copy['parameters']['mouth_open']=0.;self.assertEqual(r.clip['parameters']['mouth_open'],.5)
        with self.assertRaises(ValidationError):replace(r,clip_json=r.clip_json.rstrip())

    def test_timing_source_strength_target_and_capability_substitutions_reject(self):
        r=request()
        changes=[lambda d:d.update(animation_clips=False),lambda d:d.update(visual_quality_approved=True),
            lambda d:d.update(schema_version=True),lambda d:d.update(extra=True),
            lambda d:d['expression_clip']['source'].update(revision=2),
            lambda d:d['expression_clip']['source'].update(library_sha256='f'*64),
            lambda d:d['expression_clip']['timeline'].update(fps=30),
            lambda d:d['expression_clip']['parameters'].update(mouth_open=True),
            lambda d:d['expression_clip']['targets'][0].update(sha256='a'*64),
            lambda d:d['expression_clip'].update(parameters={k:0. for k in d['expression_clip']['parameters']})]
        for i,change in enumerate(changes):
            raw=deepcopy(r.to_dict());change(raw)
            with self.subTest(i=i),self.assertRaises(ValidationError):FacialSpriteRequest.from_dict(raw)

    def test_every_pinned_target_and_closed_input_path_required(self):
        fields={'master_sha256':'a'*64,'recipe_sha256':'b'*64,'clip_sha256':'c'*64,**TARGET_BINDINGS}
        for op in (STAGE,VERIFY):
            options=dict(fields)
            if op==VERIFY:options.update(scene_sha256='d'*64,stage_sha256='e'*64)
            JobRequest.new(op,input_project='candidate.blend',options=options)
            for name in options:
                broken=dict(options);broken.pop(name)
                with self.subTest(op=op,name=name),self.assertRaises(ValidationError):JobRequest.new(op,input_project='candidate.blend',options=broken)
            with self.assertRaises(ValidationError):JobRequest.new(op,input_project='../candidate.blend',options=options)
            with self.assertRaises(ValidationError):JobRequest.new(op,input_project='candidate.blend',options={**options,next(iter(TARGET_BINDINGS)):'a'*64})

    def test_published_schema_requires_exact_targets_and_saved_frame_proof(self):
        import json
        from pathlib import Path
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional jsonschema unavailable')
        schema=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'docs/schemas/worker-job.v1.schema.json').read_text()))
        options={'master_sha256':'a'*64,'recipe_sha256':'b'*64,'clip_sha256':'c'*64,**TARGET_BINDINGS}
        for op in (STAGE,VERIFY):
            if op==VERIFY:options.update(scene_sha256='d'*64,stage_sha256='e'*64)
            raw=JobRequest.new(op,input_project='candidate.blend',options=dict(options)).as_dict();schema.validate(raw)
            raw['options'][next(iter(TARGET_BINDINGS))]='a'*64;self.assertTrue(list(schema.iter_errors(raw)))
