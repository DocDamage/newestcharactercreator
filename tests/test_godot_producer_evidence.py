"""Malformed derived-receipt guards, no model or application acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from fixtures.godot_transaction_contract import GodotTransactionFixture
from fixtures.godot_producer_evidence_contract import unit_producer_receipts
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.godot_producer_evidence import validate_producer_chain


class GodotProducerEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=GodotTransactionFixture(Path(temp.name).resolve())
        self.report,self.verification=unit_producer_receipts(self.f.folder,self.f.request)

    def check(self, report=None, verification=None):
        validate_producer_chain(self.f.folder,self.f.request,report or self.report,
                                verification or self.verification,None)

    def test_derived_scene_is_bound_separately_from_original_motion(self):
        self.check()
        for edit in (lambda v:v.update(bound_files=[]), lambda v:v.update(source_motion_sha256='b'*64),
                     lambda v:v['frames'][0].update(bone_world_error=float('nan'))):
            value=deepcopy(self.verification);edit(value)
            with self.assertRaises(ValidationError):self.check(verification=value)

    def test_rehashed_malformed_recipe_project_is_structured_rejection(self):
        path=self.f.folder/'export_recipe.json';recipe=json.loads(path.read_text())
        recipe['project']=True;path.write_bytes(canonical_bytes(recipe))
        digest=sha256(path.read_bytes()).hexdigest()
        self.report['export_recipe_sha256']=digest
        self.verification['export_recipe_sha256']=digest
        self.verification['bound_files']['export_recipe.json']=digest
        with self.assertRaisesRegex(ValidationError,'recipe differs'):self.check()

    def test_hash_rebound_stage_cannot_replace_fresh_review_binding(self):
        path=self.f.folder/'source_review.blend';path.write_bytes(b'UNIT_CHANGED_NOT_A_MODEL')
        self.report['review_scene_sha256']=sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValidationError,'evidence changed'):self.check()
