"""Closed metadata faults only; these never establish a saved target Action."""
from dataclasses import replace
import unittest

from fixtures.target_action_contract import metadata_pair
from ucc.core.errors import ValidationError
from ucc.core.target_action import TargetActionBinding, TargetActionFile
from ucc.core.target_action_format import MAX_FILE_BYTES, RETAINED_FILES, canonical_bytes
from ucc.core.target_action_request import TargetActionRequest


class TargetActionContractTests(unittest.TestCase):
    def test_metadata_roundtrip_retains_private_clock_and_complete_inventory(self):
        request, binding = metadata_pair()
        self.assertEqual(TargetActionRequest.from_bytes(canonical_bytes(request.to_dict())), request)
        self.assertEqual(TargetActionBinding.from_bytes(canonical_bytes(binding.to_dict())), binding)
        self.assertEqual(len(binding.files), 45)
        self.assertEqual(set(binding.file_map), RETAINED_FILES)
        self.assertNotIn("binding.json", binding.file_map)
        clock = binding.to_dict()["clock"]
        self.assertEqual((clock["source_first_frame"], clock["target_first_frame"]), (2, 1))
        self.assertEqual(clock["playback_policy"], "ONCE_HOLD_LAST")
        self.assertFalse(binding.to_dict()["admission"]["engine_import_verified"])
        self.assertEqual(replace(binding, files=tuple(reversed(binding.files))).sha256, binding.sha256)

    def test_false_consent_or_readiness_promotion_cannot_enter_request(self):
        request, _ = metadata_pair()
        with self.assertRaises(ValidationError):
            replace(request, local_preview_confirmed=False)
        for name in ("engine_import_verified", "editing_authorized", "cloud_transmission_authorized"):
            value = request.to_dict()
            value[name] = True
            with self.subTest(field=name), self.assertRaises(ValidationError):
                TargetActionRequest.from_dict(value)

    def test_unknown_fields_boolean_numbers_and_wrong_profile_are_rejected(self):
        _, binding = metadata_pair()
        changes = (
            lambda value: value["source"].update(no_ai=False),
            lambda value: value["clock"].update(target_first_frame=True),
            lambda value: value["target"].update(revision=True),
            lambda value: value.update(profile="UNIT_UNSUPPORTED"),
            lambda value: value["admission"].update(usable_action_approved=True),
        )
        for change in changes:
            value = binding.to_dict()
            change(value)
            with self.subTest(change=change), self.assertRaises(ValidationError):
                TargetActionBinding.from_dict(value)

    def test_duplicate_noncanonical_and_nonfinite_json_are_rejected(self):
        _, binding = metadata_pair()
        payload = canonical_bytes(binding.to_dict())
        for invalid in (payload[:-1]+b',"schema_version":1}', payload+b"\n",
                        payload.replace(b'"revision":4', b'"revision":NaN')):
            with self.subTest(payload=invalid[:40]), self.assertRaises(ValidationError):
                TargetActionBinding.from_bytes(invalid)

    def test_preparation_and_worker_identity_substitution_is_rejected(self):
        _, binding = metadata_pair()
        with self.assertRaises(ValidationError):
            replace(binding, preparation_request_sha256="0"*64)
        value = binding.to_dict()
        value["producer"]["source_intake_worker_job_ids"][0] = value["producer"]["neutral_worker_job_ids"][0]
        with self.assertRaises(ValidationError):
            TargetActionBinding.from_dict(value)

    def test_retained_files_are_exact_bounded_and_cannot_escape(self):
        _, binding = metadata_pair()
        for name in ("../outside", "/outside", "C:/outside", "binding.json"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                TargetActionFile(name, "f"*64, 1)
        with self.assertRaises(ValidationError):
            replace(binding, files=binding.files[:-1])
        with self.assertRaises(ValidationError):
            replace(binding, files=tuple(replace(item, bytes=MAX_FILE_BYTES) for item in binding.files))
        with self.assertRaises(ValidationError):
            TargetActionFile("source_snapshot.json", "f"*64, True)
