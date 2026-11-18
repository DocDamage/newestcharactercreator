"""Host only, with the nonshipping authored-idle evidence fixture."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture, pin
from fixtures.target_action_contract import metadata_pair
from ucc.animations.target_action_diagnostic_contract import TargetActionDiagnosticSelection
from ucc.core.authored_idle_visual_review import AuthoredIdleVisualDecision
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle import author_original_idle
from ucc.jobs.authored_idle_loop_preview import POLICY, load_authored_idle_loop_preview
from ucc.jobs.authored_idle_receipt import load_authored_idle_target_mapping
from ucc.jobs.authored_idle_visual_review import (DECISION_FILENAME, POLICY as VISUAL_POLICY,
                                                  publish_authored_idle_visual_decision)
from ucc.jobs.export_destination import plan_destination, rename_new
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
        self.mapping = mapping

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

    def _visual_fixture(self):
        proof_folder = self.fixture.root/'proof'
        proof_folder.mkdir()
        self.proof = proof_folder/'idle-loop-proof.json'
        self._real_authored_evidence()
        self.target = ProjectStore(self.target.root)
        self.target.root.mkdir()
        project = replace(self.fixture.project, revision=self.binding.target.revision)
        payload = canonical_bytes(project.to_dict())
        self.target.file.write_bytes(payload)
        self.binding = replace(self.binding, target=replace(self.binding.target, project_sha256=pin(payload)))
        preview = self._load()
        binding = self.target.root/'animations/actions'/self.binding.sha256
        self.cache_path = binding/'playback/motion_skin.bin'
        self.cache_path.parent.mkdir()
        self.cache_path.write_bytes(self.cache.packed)
        (binding/'native_mapping.json').write_bytes(self.mapping.mapping_json)
        self.output = self.fixture.root/'visual-decision'
        self.decision = AuthoredIdleVisualDecision('rework', 'Invented test reviewer',
                                                 'Investigate the synthetic wrist.\nInspect the loop again.', True)
        return preview.review_identity

    def _publish_visual(self, identity, **changes):
        folder = self.target.root/'animations/actions'/self.binding.sha256
        binding_path = folder/'binding.json'
        selected = SimpleNamespace(directory=folder, binding_path=binding_path,
            binding_sha256=self.binding.sha256, cache=self.cache,
            watched_identities=tuple(ancestry((self.database, self.target.file, binding_path,
                folder/'native_mapping.json', self.cache_path)).items()))
        args = dict(proof_file=self.proof, database_path=self.database, selection=identity.selection,
            expected_identity=identity, decision=self.decision,
            destination=plan_destination(self.output, self.target.root))
        with (patch(_LOADER, return_value=selected) as loader,
              patch('ucc.jobs.runner.run_process', side_effect=AssertionError('Visual decision is native-free'))):
            result = publish_authored_idle_visual_decision(self.target, **(args|changes))
        loader.assert_called_once()
        return result

    def test_visual_decision_has_explicit_attestation_and_closed_choices(self):
        for values in (('approve', 'Reviewer', 'Note', False), ('approve', 'Reviewer', 'Note', 1),
                       ('pending', 'Reviewer', 'Note', True), ('approve', '', 'Note', True),
                       ('approve', 'Reviewer', 'A'*2001, True), ('rework', 'Reviewer', 'Note\x00', True)):
            with self.subTest(values=values[:2]), self.assertRaises(ValidationError):
                AuthoredIdleVisualDecision(*values)

    def test_visual_decision_exports_only_exact_current_identity_and_human_declaration(self):
        identity = self._visual_fixture()
        before = {path:pin(path.read_bytes()) for path in self.fixture.root.rglob('*') if path.is_file()}
        with patch('ucc.jobs.authored_idle_visual_review.check_target_action_catalog') as catalog:
            published = self._publish_visual(identity)
            self.assertEqual(catalog.call_count, 2)
            self.assertEqual(catalog.call_args.args, (self.database,self.binding.source))
        self.assertEqual(identity.proof_sha256, pin(self.proof.read_bytes()))
        self.assertEqual(identity.receipt_sha256, self.candidate.receipt_sha256)
        self.assertEqual(identity.mapping_sha256, self.mapping.mapping_sha256)
        self.assertEqual(identity.cache_sha256, pin(self.cache.packed))
        self.assertEqual(identity.selection.project_sha256, pin(self.target.file.read_bytes()))
        self.assertEqual(published.path, self.output/DECISION_FILENAME)
        raw = published.path.read_bytes()
        self.assertEqual(raw, canonical_bytes({'schema_version':1, 'policy':VISUAL_POLICY, 'private_local_only':True,
            'reviewed_identity':identity.to_dict(), 'visual_decision':self.decision.to_dict()}))
        self.assertEqual(published.sha256, pin(raw))
        self.assertEqual({path:pin(path.read_bytes()) for path in self.fixture.root.rglob('*')
                          if path.is_file() and path != published.path}, before)

    def test_visual_decision_refuses_replaced_proof_and_reserved_output(self):
        identity = self._visual_fixture()
        with self.assertRaisesRegex(ValidationError, 'outside'):
            self._publish_visual(identity, destination=plan_destination(self.proof.parent/'nested', self.target.root))
        with self.assertRaisesRegex(ValidationError, 'outside'):
            self._publish_visual(identity, destination=plan_destination(self.candidate.directory/'nested', self.target.root))
        moved_policy = self.fixture.root/'equivalent-policy.json'
        moved_policy.write_bytes(self.fixture.policy.read_bytes())
        pointer = json.loads(self.proof.read_bytes())
        pointer['source_policy_records'][0]['path'] = str(moved_policy)
        self.proof.write_bytes(canonical_bytes(pointer))
        with self.assertRaisesRegex(ProjectConflict, 'differs from the exact preview'):
            self._publish_visual(identity)
        self.assertFalse(self.output.exists())

    def test_visual_decision_withdraws_on_exact_cache_change_during_rename(self):
        identity = self._visual_fixture()

        def change_cache_at_rename(stage, final):
            rename_new(stage, final)
            if final == self.output:
                info = self.cache_path.stat()
                self.cache_path.write_bytes(b'X'+self.cache.packed[1:])
                os.utime(self.cache_path, ns=(info.st_atime_ns,info.st_mtime_ns))
                self.assertEqual(self.cache_path.stat().st_mtime_ns, info.st_mtime_ns)

        with (patch('ucc.jobs.authored_idle_transactions.rename_new', change_cache_at_rename),
              patch('ucc.jobs.authored_idle_visual_review.check_target_action_catalog')):
            with self.assertRaisesRegex(ProjectStorageError, 'Saved proof bytes or identity changed'):
                self._publish_visual(identity)
        self.assertEqual(self.cache_path.read_bytes(), b'X'+self.cache.packed[1:])
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.output.parent.glob('.ucc-export-*')))


if __name__ == '__main__':
    unittest.main()
