"""Host only, with the nonshipping authored-idle evidence fixture."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture, pin
from fixtures.target_action_contract import metadata_pair
from ucc.animations.target_action_diagnostic_contract import TargetActionDiagnosticSelection
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle import author_original_idle
from ucc.jobs.authored_idle_loop_preview import POLICY, load_authored_idle_loop_preview
from ucc.jobs.authored_idle_receipt import load_authored_idle_target_mapping
from ucc.jobs.target_action_storage import ancestry


_LOADER = 'ucc.jobs.authored_idle_loop_preview.load_target_action'


class AuthoredIdleLoopPreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fixture = HostFixture(temp.name)
        self.proof = self.fixture.root/'loop-proof.json'

    def _real_authored_evidence(self):
        f = self.fixture
        with patch('ucc.jobs.authored_idle.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = f.run
            candidate = author_original_idle(f.store, **f.args(), timeout_s=120)
        mapping = load_authored_idle_target_mapping(f.store, directory=candidate.directory,
            expected_receipt_sha256=candidate.receipt_sha256, source_policy_records=f.records,
            database_path=f.database, blender_exe=f.blender, worker_script=f.worker)
        self.proof.write_bytes(canonical_bytes({
            'schema_version': 1, 'policy': POLICY, 'project_root': str(f.store.root),
            'catalog_path': str(f.database), 'candidate_directory': str(candidate.directory),
            'receipt_sha256': candidate.receipt_sha256, 'source_policy_records': [
                {'asset_id': row.asset_id, 'path': str(row.path), 'sha256': row.sha256} for row in f.records],
            'blender_executable': {'path': str(f.blender), 'sha256': pin(f.blender.read_bytes())},
            'worker_script': {'path': str(f.worker), 'sha256': pin(f.worker.read_bytes())},
        }))
        self.target = SimpleNamespace(root=f.root/'copied-target')
        self.database = f.root/'target.sqlite3'
        self.database.write_bytes(b'invented catalog')
        _, binding = metadata_pair()
        packed = b'invented cache only'
        self.cache = SimpleNamespace(packed=packed, source_first_frame=2, frame_count=300, fps=30., surface_review=object())
        bound_files = tuple(replace(row, sha256=sha256(packed).hexdigest(), bytes=len(packed))
                            if row.name == 'playback/motion_skin.bin' else row for row in binding.files)
        source = replace(binding.source, source_sha256=candidate.source_sha256, snapshot_sha256=candidate.snapshot_sha256)
        self.binding = replace(binding, source=source, target=replace(candidate.target, revision=candidate.target.revision+1),
                               mapping_sha256=mapping.mapping_sha256, files=bound_files)
        self.candidate = candidate

    def _load(self, *, changes=lambda: None):
        binding = self.binding
        folder = self.target.root/'animations/actions'/binding.sha256
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/'binding.json'
        path.write_bytes(canonical_bytes(binding.to_dict()))
        selection = TargetActionDiagnosticSelection(binding.target.project_id, binding.target.revision,
            binding.target.project_sha256, binding.target.master_sha256, binding.source.clip_id, binding.sha256,
            binding.source.source_binding_sha256, binding.source.catalog_record_sha256)

        def target_load(*args, **kwargs):
            selected = SimpleNamespace(watched_identities=tuple(ancestry((self.database, path)).items()),
                directory=folder, binding_path=path, binding_sha256=binding.sha256, cache=self.cache)
            changes()
            return selected

        with patch(_LOADER, side_effect=target_load) as loader:
            result = load_authored_idle_loop_preview(self.target, proof_file=self.proof, selection=selection,
                database_path=self.database, local_preview_confirmed=True)
            loader.assert_called_once()
            return result

    def test_frozen_original_authority_and_ephemeral_catalog_coordination(self):
        self._real_authored_evidence()
        preview = self._load()
        self.assertEqual(preview.binding_sha256, self.binding.sha256)
        self.assertEqual(preview.cache_sha256, pin(self.cache.packed))
        self.assertIn(self.proof, preview.watch_paths)
        self.assertIn(self.fixture.policy, preview.watch_paths)
        self.assertIn(self.candidate.review_path, preview.watch_paths)
        wal = Path(str(self.database)+'-wal')
        wal.write_bytes(b'')
        Path(str(self.database)+'-shm').write_bytes(b'read marks only')
        preview.assert_current()
        wal.write_bytes(b'committed pages present')
        self.assertFalse(preview.identities_current())
        wal.unlink()
        preview.assert_current()
        self.fixture.policy.write_bytes(self.fixture.policy.read_bytes()+b' ')
        with self.assertRaises(ProjectStorageError):
            preview.assert_current()

    def test_post_admission_proof_replacement_cannot_be_rebaselined(self):
        self._real_authored_evidence()
        with self.assertRaises(ProjectStorageError):
            self._load(changes=lambda: self.proof.write_bytes(self.proof.read_bytes()+b' '))

    def test_revision_may_differ_but_neutral_rest_must_match(self):
        self._real_authored_evidence()
        rest = self.binding.target.rest_sha256
        conflicting_rest = ('0' if rest[0] != '0' else '1') + rest[1:]
        self.binding = replace(self.binding, target=replace(self.binding.target, rest_sha256=conflicting_rest))
        with self.assertRaisesRegex(ProjectConflict, 'neutral master, or rest'):
            self._load()

    def test_closed_pointer_does_not_grant_quality(self):
        self._real_authored_evidence()
        raw = json.loads(self.proof.read_bytes())
        raw['loop_quality_approved'] = True
        self.proof.write_bytes(canonical_bytes(raw))
        with self.assertRaises(ValidationError):
            self._load()


if __name__ == '__main__':
    unittest.main()
