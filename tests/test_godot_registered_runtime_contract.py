"""Closed metadata/byte boundaries, using isolated nonshipping logic fixtures."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from fixtures.godot_registered_retention_logic import RetentionFixture
from ucc.core.errors import ProjectStorageError,ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_runtime_contract import (FALSE_FLAGS,MAX_MANIFEST_BYTES,
    RegisteredInputSelection,RegisteredRuntimeManifest,RetainedInputFile,RetainedProofReference)
from ucc.jobs import godot_registered_runtime_files as files
from ucc.jobs.godot_registered_runtime_admission import preparation_paths,proof_references
from ucc.jobs.godot_registered_runtime_storage import _metadata_records
from ucc.jobs.target_action_context import Budget
from ucc.export.godot_runtime_contract import NativeRuntimeRequest


class RegisteredRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.f=RetentionFixture(Path(temp.name).resolve());self.budget=Budget(None,60)
        request=NativeRuntimeRequest.from_bytes((self.f.work/"runtime_request.json").read_bytes())
        records=_metadata_records(preparation_paths(self.f.store,self.f.preparation),request,self.budget)
        self.manifest=RegisteredRuntimeManifest(str(UUID(int=5000)),self.f.selection,self.f.receipt_sha,
            self.f.preparation.recipe_sha256,request.sha256,self.f.stage.name,self.f.fresh.name,
            records,proof_references(self.f.binding),self.f.permissions)

    def test_exact_canonical_roundtrip_all_false_and_four_bound_proofs(self):
        raw=canonical_bytes(self.manifest.to_dict());parsed=RegisteredRuntimeManifest.from_bytes(raw)
        self.assertEqual(parsed,self.manifest);self.assertEqual(parsed.sha256,sha256(raw).hexdigest())
        self.assertEqual(len(parsed.proofs),4);self.assertEqual(len(parsed.files),33)
        self.assertTrue(all(parsed.to_dict()[key] is False for key in FALSE_FLAGS))
        self.assertEqual(RegisteredInputSelection.from_dict(self.f.selection.to_dict()),self.f.selection)
        self.assertEqual(self.f.selection.loader_args()["binding_sha256"],self.f.binding.sha256)

    def test_unknown_missing_duplicate_or_unbound_records_rejected(self):
        raw=self.manifest.to_dict()
        for mutate in (lambda d:d.update(extra=False),lambda d:d.pop("editing_authorized"),
                lambda d:d["files"].pop(".gdignore"),
                lambda d:d["proofs"]["native_review"].update(name="../review_motion.blend"),
                lambda d:d.update(recipe_sha256="0"*64),
                lambda d:d["files"]["character.glb"].update(bytes=True)):
            value=deepcopy(raw);mutate(value)
            with self.subTest(value=value),self.assertRaises(ValidationError):RegisteredRuntimeManifest.from_dict(value)
        with self.assertRaises(ValidationError):replace(self.manifest,files=self.manifest.files[:-1]+self.manifest.files[:1])
        with self.assertRaises(ValidationError):replace(self.manifest,proofs=self.manifest.proofs[:1]*4)

    def test_no_readiness_flag_can_be_upgraded(self):
        for name in FALSE_FLAGS:
            raw=self.manifest.to_dict();raw[name]=True
            with self.subTest(name=name),self.assertRaises(ValidationError):RegisteredRuntimeManifest.from_dict(raw)

    def test_selection_identity_and_payload_bounds_are_strict(self):
        for changes in (dict(revision=True),dict(revision=-1),dict(binding_sha256="x"*64),dict(project_id=" ../bad ")):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):replace(self.f.selection,**changes)
        for args in (("../private.gd","0"*64,1),(".gdignore","0"*64,0),("character.glb","0"*64,0)):
            with self.assertRaises(ValidationError):RetainedInputFile(*args)
        with self.assertRaises(ValidationError):RetainedProofReference("native_review","review_motion.blend","0"*64,1)

    def test_manifest_same_buffer_duplicate_nonfinite_and_noncanonical_rejection(self):
        raw=canonical_bytes(self.manifest.to_dict())
        variants=[raw+b" ",b'{"policy":1,"policy":2}',b'{"value":NaN}',b'{"value":1e999}',
            b"[1]",b"\xff",b" "*(MAX_MANIFEST_BYTES+1),b"["*2000+b"]"*2000]
        for payload in variants:
            with self.subTest(payload=payload[:50]),self.assertRaises(ValidationError):RegisteredRuntimeManifest.from_bytes(payload)


class RegisteredRuntimeMetadataTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name).resolve()/"selected.json";self.budget=Budget(None,60)

    def test_parse_and_digest_are_bound_to_same_captured_buffer(self):
        old=b'{"selected":"original"}\n';new=b'{"selected":"foreign!"}\n'
        self.path.write_bytes(old);real=json.loads
        def parse(payload,**kwargs):
            self.path.write_bytes(new)
            return real(payload,**kwargs)
        with patch.object(files.json,"loads",side_effect=parse):
            value,raw,digest=files.read_metadata(self.path,1024,self.budget)
        self.assertEqual(value,{"selected":"original"});self.assertEqual(raw,old)
        self.assertEqual(digest,sha256(old).hexdigest());self.assertEqual(self.path.read_bytes(),new)

    def test_malformed_nonfinite_duplicate_and_oversized_fail_closed(self):
        for payload in (b'{"x":1e999}',b'{"x":NaN}',b'{"x":1,"x":2}',b'[]',b'\xff',b'{'*2000):
            self.path.write_bytes(payload)
            with self.subTest(payload=payload[:30]),self.assertRaises(ValidationError):files.read_metadata(self.path,8192,self.budget)
        self.path.write_bytes(b"12345")
        with self.assertRaises(ProjectStorageError):files.read_metadata(self.path,4,self.budget)

    def test_hash_and_length_must_match_selected_metadata(self):
        self.path.write_bytes(b'{}')
        with self.assertRaises(ProjectStorageError):files.read_bytes(self.path,16,self.budget,expected_sha256="0"*64)
        self.assertEqual(files.hash_file(self.path,2,self.budget),(sha256(b'{}').hexdigest(),2))
        with self.assertRaises(ProjectStorageError):files.hash_file(self.path,1,self.budget)
