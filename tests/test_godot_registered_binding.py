"""Nonshipping metadata fixtures only; never native-content admission."""
from dataclasses import replace
import unittest
from uuid import UUID

from fixtures.target_action_contract import metadata_pair
from ucc.core.models import CharacterProject
from ucc.core.target_action_format import RETAINED_FILES
from ucc.core.errors import ValidationError
from ucc.export.godot_registered_binding import project_registered_native_proofs


def context():
    _, binding = metadata_pair()
    project = CharacterProject(str(UUID(int=50)), "Nonshipping test")
    project = replace(project, project_id=binding.target.project_id,
        revision=binding.target.revision, geometry_state="generated_unverified",
        master_blend="master/versions/" + binding.target.master_sha256 + ".blend",
        animations=("unselected#clip-0000", binding.source.clip_id))
    args = dict(selected_binding_sha256=binding.sha256, project=project,
                project_sha256=binding.target.project_sha256, current_source=binding.source)
    return binding, args


class RegisteredNativeProjectionTests(unittest.TestCase):
    def test_complete_inventory_and_all_nine_fixed_producer_roles(self):
        binding, args = context()
        result = project_registered_native_proofs(binding, **args)
        self.assertEqual({item.name for item in result.retained_files}, RETAINED_FILES)
        self.assertEqual(len(result.retained_files), 45)
        self.assertEqual(tuple(item.job_id for item in result.producer_proofs), binding.producer.worker_job_ids)
        self.assertEqual(tuple(item.role for item in result.producer_proofs), (
            "neutral_first", "neutral_second", "source_intake_first", "source_intake_second",
            "body_first", "body_second", "body_reopen", "playback", "surface_verify"))
        self.assertEqual(len({p.request.name for p in result.producer_proofs}), 9)
        self.assertEqual(len({p.result.name for p in result.producer_proofs}), 9)
        for proof in result.producer_proofs:
            self.assertEqual(proof.request, binding.file_map[proof.request.name])
            self.assertEqual(proof.result, binding.file_map[proof.result.name])
        self.assertEqual(result.native_review, binding.file_map["body_first/review_motion.blend"])
        self.assertEqual(result.native_timeline, binding.file_map["body_first/target_timeline.json"])
        self.assertEqual(result.source_snapshot, binding.file_map["source_snapshot.json"])
        self.assertEqual(result.native_mapping, binding.file_map["native_mapping.json"])

    def test_preserves_all_animation_ids_and_no_readiness_upgrade(self):
        binding, args = context()
        result = project_registered_native_proofs(binding, **args)
        self.assertEqual(result.animation_ids, args["project"].animations)
        self.assertFalse(result.engine_use_authorized)
        self.assertFalse(result.retained_content_verified)

    def test_explicit_binding_project_source_context_mismatch_rejects(self):
        binding, args = context()
        variants = [dict(args, selected_binding_sha256="0"*64), dict(args, project_sha256="0"*64),
            dict(args, current_source=replace(binding.source, catalog_record_sha256="0"*64))]
        for field, value in (("project_id", "foreign"), ("revision", 20),
                ("master_blend", "master/versions/" + "0"*64 + ".blend"), ("animations", ())):
            variants.append(dict(args, project=replace(args["project"], **{field:value})))
        for selected in variants:
            with self.subTest(selected=selected), self.assertRaises(ValidationError):
                project_registered_native_proofs(binding, **selected)

    def test_arbitrary_dictionaries_are_not_admission(self):
        binding, args = context()
        with self.assertRaises(ValidationError):
            project_registered_native_proofs(binding.to_dict(), **args)
        for field in ("project", "current_source"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                project_registered_native_proofs(binding, **dict(args, **{field:args[field].to_dict()}))

    def test_changed_proof_or_producer_cannot_keep_selected_binding_identity(self):
        binding, args = context()
        record = replace(binding.file_map["body_first/result.json"], sha256="0"*64)
        changed = replace(binding, files=tuple(record if item.name==record.name else item for item in binding.files))
        changed_producer = replace(binding.producer, cache_job_id=str(UUID(int=99)))
        for value in (changed, replace(binding, producer=changed_producer)):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                project_registered_native_proofs(value, **args)

    def test_closed_reader_rechecks_typed_metadata_invariants(self):
        binding, args = context()
        # Bypass frozen dataclass construction only to model corrupted in-memory
        # metadata. The production reader must recheck it before projecting.
        object.__setattr__(binding, "files", binding.files[:-1])
        with self.assertRaises(ValidationError):
            project_registered_native_proofs(binding, **args)
