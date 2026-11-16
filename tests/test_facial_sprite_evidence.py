"""Proof capability faults fail before PNG admission; synthetic metadata only."""
from pathlib import Path
from hashlib import sha256
import json,tempfile,unittest
from ucc.core.errors import ValidationError
from ucc.core.facial_sprites import POLICY
from ucc.sprites.facial_evidence import checked_facial_evidence
from fixtures.facial_sprite_logic import request


class FacialSpriteEvidenceTests(unittest.TestCase):
    def test_boolean_schema_and_partial_frame_proof_reject_before_missing_images(self):
        r=request();bindings={'master_sha256':'a'*64,'recipe_sha256':'b'*64,'clip_sha256':'c'*64,'scene_sha256':'d'*64}
        report={'schema_version':1,'policy':POLICY,**bindings,'source_state_sha256':'e'*64,'shader_sha256':'f'*64,
            'configuration':{},'original_scene':'UNIT_NOT_REAL_SCENE','pivot':[.5,.9],'frames':[],
            'timeline':r.clip['timeline'],'blender_version':'5.3.0','blender_build_hash':'UNIT_NOT_BUILD_PROOF','animation_clips':True,'visual_quality_approved':False}
        proof={'schema_version':1,'policy':POLICY,'bindings':bindings,'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
            'source_state_sha256':'e'*64,'shader_sha256':'f'*64,'reference_frames':100,'saved_frames':100,'exact_neutral_endpoints':True,
            'exact_rerender_pixels':True,'visual_quality_approved':False}
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);path=folder/'facial_sprite_stage.json';path.write_text(json.dumps(report));bindings['stage_sha256']=sha256(path.read_bytes()).hexdigest()
            for key,value in (('schema_version',True),('saved_frames',25),('saved_scene_rebuilt_or_repaired',True),('exact_neutral_endpoints',False)):
                raw={**proof,key:value};(folder/'facial_sprite_verification.json').write_text(json.dumps(raw))
                with self.subTest(key=key),self.assertRaisesRegex(ValidationError,'proof lacks'):checked_facial_evidence(folder,r,bindings)
