"""Independent file-system delivery faults; no real engine/runtime acceptance."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
import shutil
from unittest.mock import patch
from fixtures.unity_publication_logic import payload_fixture
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.unity_export_payload import (stage_payload, snapshot, check_snapshot,
    verify_unity_export_result, engine_payload, PRIVATE_INPUTS, ROOT_INPUTS, POLICY, RECEIPT)


class UnityPublicationPayloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.engine, self.request, self.stage = payload_fixture(self.root)

    def publish_marker_receipt(self):
        files = stage_payload(self.engine, self.stage, self.request)
        receipt = {'schema_version': 1, 'policy': POLICY, 'request_sha256': self.request.sha256,
            'master_sha256': dict(self.request.source_bindings)['master'], 'files': files,
            'export_published': True, 'final_payload_verified': True,
            'animation_clips_verified': False, 'visual_quality_approved': False,
            'distribution_license_review_complete': False}
        target = self.stage/RECEIPT
        target.write_bytes(canonical_bytes(receipt))
        result = SimpleNamespace(destination=self.stage, request_sha256=self.request.sha256,
            master_sha256=receipt['master_sha256'], receipt_sha256=sha256(target.read_bytes()).hexdigest())
        return result, receipt

    def test_delivery_inventory_excludes_private_original_reference_inputs(self):
        files = stage_payload(self.engine, self.stage, self.request)
        self.assertEqual(set(files), engine_payload() | ROOT_INPUTS)
        self.assertFalse(set(files) & PRIVATE_INPUTS)
        self.assertFalse(any(p.suffix == '.blend' or p.name.startswith('unity_runtime_source') for p in self.stage.rglob('*')))
        self.assertEqual((self.stage/'request.json').read_bytes(), canonical_bytes(self.request.to_dict()))

    def test_final_result_rejects_added_private_dataset_missing_and_altered_files(self):
        result, receipt = self.publish_marker_receipt()
        self.assertEqual(verify_unity_export_result(result), receipt)
        target = self.stage/'unity_runtime_source.bin'
        target.write_bytes(b'UNIT_PRIVATE_DATA_MARKER')
        with self.assertRaises(ProjectStorageError):
            verify_unity_export_result(result)
        target.unlink()
        target = self.stage/'Assets/UCC/Character.prefab'
        original = target.read_bytes()
        target.write_bytes(original+b'UNIT_ALTERED')
        with self.assertRaises(ProjectStorageError):
            verify_unity_export_result(result)
        target.write_bytes(original)
        target.unlink()
        with self.assertRaises(ProjectStorageError):
            verify_unity_export_result(result)

    def test_staging_rejects_supported_filename_with_changed_bytes(self):
        path = self.engine.directory/'Assets/UCC/CharacterSkin.asset'
        path.write_bytes(path.read_bytes()+b'UNIT_ALTERED')
        with self.assertRaisesRegex(ProjectStorageError, 'changed'):
            stage_payload(self.engine, self.stage, self.request)

    def test_unknown_saved_payload_cannot_be_silently_ignored_or_delivered(self):
        target = self.root/'native-import-receipt.json'
        receipt = json.loads(target.read_bytes())
        receipt['saved_files']['Library/UNIT_PRIVATE_CACHE'] = 'a'*64
        target.write_bytes(canonical_bytes(receipt))
        self.engine.receipt_sha256 = sha256(target.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValidationError, 'inventory'):
            stage_payload(self.engine, self.stage, self.request)

    def test_final_receipt_cannot_elevate_diagnostic_scope_to_artist_or_release_approval(self):
        result, receipt = self.publish_marker_receipt()
        for key in ('animation_clips_verified', 'visual_quality_approved', 'distribution_license_review_complete'):
            with self.subTest(key=key):
                changed = receipt | {key: True}
                target = self.stage/RECEIPT
                target.write_bytes(canonical_bytes(changed))
                result.receipt_sha256 = sha256(target.read_bytes()).hexdigest()
                with self.assertRaises(ValidationError):
                    verify_unity_export_result(result)

    def test_snapshot_cancellation_does_not_report_complete_payload(self):
        from threading import Event
        cancel = Event()
        cancel.set()
        with self.assertRaises(ProjectStorageError):
            snapshot(self.engine.directory, cancel)

    def test_even_empty_cache_directory_invalidates_final_delivery(self):
        result, _ = self.publish_marker_receipt()
        (self.stage/'Library').mkdir()
        with self.assertRaisesRegex(ProjectStorageError, 'directory|cache'):
            verify_unity_export_result(result)

    def test_extra_private_recipe_data_cannot_cross_delivery_boundary(self):
        recipe_path = self.engine.directory/'engine_recipe.json'
        recipe = json.loads(recipe_path.read_bytes())
        recipe['UNIT_PRIVATE_REFERENCE_DATA'] = [1, 2, 3]
        recipe_path.write_bytes(canonical_bytes(recipe))
        with self.assertRaisesRegex(ValidationError, 'recipe'):
            stage_payload(self.engine, self.stage, self.request)

    def test_copy_race_cannot_seal_changed_mesh_as_approved_payload(self):
        actual = shutil.copy2
        def corrupt_copy(source, destination, *args, **kwargs):
            result = actual(source, destination, *args, **kwargs)
            if Path(destination).name == 'CharacterSkin.asset':
                Path(destination).write_bytes(b'UNIT_RACE_DURING_COPY')
            return result
        with patch('ucc.jobs.unity_export_payload.shutil.copy2', side_effect=corrupt_copy):
            with self.assertRaisesRegex(ProjectStorageError, 'altered|changed'):
                stage_payload(self.engine, self.stage, self.request)

    def test_copy_race_cannot_inject_private_recipe_after_canonical_review(self):
        actual = shutil.copy2
        def corrupt_copy(source, destination, *args, **kwargs):
            result = actual(source, destination, *args, **kwargs)
            if Path(destination).name == 'engine_recipe.json':
                recipe = json.loads(Path(destination).read_bytes())
                recipe['UNIT_PRIVATE_REFERENCE_DATA'] = [1, 2, 3]
                Path(destination).write_bytes(canonical_bytes(recipe))
            return result
        with patch('ucc.jobs.unity_export_payload.shutil.copy2', side_effect=corrupt_copy):
            with self.assertRaisesRegex(ProjectStorageError, 'altered|changed'):
                stage_payload(self.engine, self.stage, self.request)
