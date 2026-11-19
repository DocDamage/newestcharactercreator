from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.persistent_native_playback import retained_preview_fixture
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.jobs.persistent_native_playback import PersistentNativePreview, _restore_frames, _worker_fingerprint
from ucc.jobs.persistent_preview_index import read_index
from ucc.jobs.source_skeleton_files import watch_identity
from ucc.jobs.target_action_context import operation_budget
from ucc.preview.surface_review import SurfaceReview


class PersistentNativePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        job, master, path, self.geometry, hashes, self.metadata, self.authority = retained_preview_fixture(root)
        project = SimpleNamespace(project_id='retained-preview', revision=1)
        store = SimpleNamespace(root=root, file=path, load=lambda: project)
        self.cancel = Event()
        self.preview = PersistentNativePreview(root / 'index', store, project, self.authority, None,
                                               path, self.cancel)
        self.context = {'master': str(master), 'master_sha256': hashes[master]}
        self.record = {
            'job': job, 'surface_job': '', 'cache': self.metadata,
            'proof': {str(path): [pin, list(watch_identity(path))] for path, pin in hashes.items()},
        }
        self.authority.database_path = root / 'catalog.db'
        self.authority.clip_id = 'retained-clip#clip-0000'

    @patch('ucc.jobs.persistent_native_playback.find_catalog_preview_profile', return_value=None)
    def test_live_cache_serializes_all_immutable_frame_and_surface_arrays(self, _profile):
        with operation_budget(self.cancel, 5) as budget:
            result = self.preview._restore_record(self.record, self.context, budget)
        surface = SurfaceReview('CHECKED', '', ((1,), (2, 3)), ((1, 0), (0, 2)),
                                ('a' * 64, 'b' * 64))
        result = replace(result, cache=replace(result.cache, surface_review=surface))
        self.context['blender'] = str(self.geometry)
        with patch.object(PersistentNativePreview, '_context', return_value=self.context):
            self.preview.save(result, self.context)
            loaded = self.preview.restore(None)
        self.assertIsInstance(read_index(self.preview.root, self.preview._slot), dict)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.cache, result.cache)

    @patch('ucc.jobs.persistent_native_playback.find_catalog_preview_profile', return_value=None)
    def test_restart_recaptures_proofs_and_detects_same_byte_replacement(self, _profile):
        with operation_budget(self.cancel, 5) as budget:
            result = self.preview._restore_record(self.record, self.context, budget)
        self.assertEqual(result.cache.packed, self.geometry.read_bytes())
        self.assertEqual(result.cache.source_first_frame, 7)
        self.assertTrue(result.proof_receipt.guard())

        replacement = self.geometry.with_name('replacement.bin')
        replacement.write_bytes(result.cache.packed)
        replacement.replace(self.geometry)
        self.assertFalse(result.proof_receipt.identities_current())
        with operation_budget(self.cancel, 5) as budget:
            with self.assertRaisesRegex(ValidationError, 'replaced'):
                self.preview._restore_record(self.record, self.context, budget)

    def test_bad_partition_or_outside_proof_is_rejected(self):
        self.metadata['chunks'][1][0] = 12
        with self.assertRaisesRegex(ValidationError, 'frame ranges'):
            _restore_frames(self.geometry.read_bytes(), self.metadata, self.authority)
        unrelated = self.preview.store.root / 'unrelated'
        unrelated.write_bytes(b'unrelated')
        self.record['proof'][str(unrelated)] = ['0' * 64, list(watch_identity(unrelated))]
        with operation_budget(self.cancel, 5) as budget:
            with self.assertRaisesRegex(ValidationError, 'escapes'):
                self.preview._restore_record(self.record, self.context, budget)

    def test_cancelled_lookup_accesses_no_index(self):
        self.cancel.set()
        with patch('ucc.jobs.persistent_native_playback.read_index') as read:
            with self.assertRaises(ProjectStorageError):
                self.preview.restore(None)
        read.assert_not_called()

    def test_actual_source_worker_fingerprint_includes_empty_package_files(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / 'src/ucc/jobs/__init__.py').stat().st_size, 0)
        self.assertRegex(_worker_fingerprint(root / 'blender_bridge/entrypoint.py', self.cancel), r'^[0-9a-f]{64}$')
from dataclasses import replace
