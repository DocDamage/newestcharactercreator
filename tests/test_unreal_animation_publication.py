"""Checks for the portable Unreal input contract using fixture bytes only."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.target_action_context import Budget
from ucc.jobs.unreal_animation_preview import PLAYBACK_POLICY, PLAYBACK_RECEIPT, VerifiedUnrealPreview, _require_observation
from ucc.jobs.unreal_animation_publication import (
    PORTABLE_FILES, RECEIPT, publish_unreal_animation, verify_unreal_animation_payload,
)


class UnrealAnimationPublicationTests(TestCase):
    def test_only_verified_runtime_files_publish(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root/'work/portable'
            payload = b'UNIT_CONTROL'
            files = {name: sha256(payload).hexdigest() for name in PORTABLE_FILES}
            for name in files:
                path = source/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            recorded = dict(policy=PLAYBACK_POLICY, portable_files=files,
                source_binding_sha256='c'*64, export_published=False, corrected_runtime_verified=True,
                pie_verified=False, normal_loop_wrap_verified=True, lit_motion_verified=True)
            proof_path = source.parent/PLAYBACK_RECEIPT
            store = ProjectStore(root/'saved')
            selected = plan_destination(root/'export', store.root)

            def publish():
                data = canonical_bytes(recorded)
                proof_path.write_bytes(data)
                result = VerifiedUnrealPreview(source, sha256(data).hexdigest())
                return publish_unreal_animation(store, result, database_path=root/'catalog/private.sqlite3',
                                                 destination=selected, guard=lambda: None)

            with self.assertRaises(ValidationError):
                publish()
            self.assertFalse(selected.path.exists())
            recorded['pie_verified'] = True
            result = publish()
            observed = {path.relative_to(result.directory).as_posix()
                        for path in result.directory.rglob('*') if path.is_file()}
            self.assertEqual(observed, PORTABLE_FILES | {'README.txt', RECEIPT})
            self.assertFalse(any('UccNativeAnimation' in name for name in observed))
            (source/'Content/PrivateProof.bin').write_bytes(payload)
            with self.assertRaises(ProjectStorageError):
                verify_unreal_animation_payload(source, files, Budget(None, 5))

    def test_zero_raster_and_boolean_clock_are_rejected(self):
        expected = dict(frames=300, corrected_submit_verified=True)
        report = expected | dict(raster_foreground_pixels=80, raster_changed_pixels=20)
        _require_observation(report, expected, raster=True)
        for changes in ({'raster_changed_pixels': 0}, {'corrected_submit_verified': 1}, {'frames': 299}):
            with self.assertRaises(ValidationError):
                _require_observation(report | changes, expected, raster=True)
