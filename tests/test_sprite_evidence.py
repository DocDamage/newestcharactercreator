"""Malformed proof rejection before image admission; metadata is UNIT_ONLY."""
from pathlib import Path
from hashlib import sha256
import json,tempfile,unittest
from ucc.core.errors import ValidationError
from ucc.sprites.render_evidence import checked_sprite_evidence
from fixtures.sprite_render_logic import request,incomplete_evidence_metadata


class SpriteEvidenceTests(unittest.TestCase):
    def test_boolean_numeric_substitution_cannot_satisfy_saved_scene_proof(self):
        for key,value in (('schema_version',True),('verified_reopen',1),('saved_scene_rebuilt_or_repaired',0),('visual_quality_approved',0)):
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp).resolve();bindings={k:'a'*64 for k in ('master_sha256','recipe_sha256','scene_sha256')}
                report,proof=incomplete_evidence_metadata(bindings);path=folder/'sprite_stage.json';path.write_text(json.dumps(report))
                bindings['stage_sha256']=sha256(path.read_bytes()).hexdigest();proof['bindings']=bindings;proof[key]=value
                (folder/'sprite_verification.json').write_text(json.dumps(proof))
                with self.assertRaisesRegex(ValidationError,'independent saved-scene re-render evidence'):checked_sprite_evidence(folder,request(),bindings)
