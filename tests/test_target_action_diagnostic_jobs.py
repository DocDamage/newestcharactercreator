"""Diagnostic IO/authority regressions; no native acceptance inferred from doubles."""
from contextlib import ExitStack, closing
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.target_action_diagnostic_jobs_logic import DiagnosticJobsFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs import target_action_diagnostic as job
from ucc.library.provenance import AssetPolicyError


class TargetDiagnosticJobsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.f = DiagnosticJobsFixture(Path(temp.name).resolve())
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.loader = self.stack.enter_context(patch.object(job, 'load_target_action',
            side_effect=lambda *a,**k:self.f.prepared))
        self.stack.enter_context(patch.object(job.TargetActionBinding, 'from_bytes',
            side_effect=lambda raw:self.f.binding))
        self.stack.enter_context(patch.object(job, 'check_target_action_catalog', side_effect=self.f.logical))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('No execution allowed')))

    def load(self, **kwargs):
        return job.inspect_saved_target_action(self.f.store, **(self.f.args()|kwargs))

    def test_scalar_immutable_report_and_guard_reloads_typed_authority(self):
        result = self.load(); result.guard()
        self.assertEqual(self.loader.call_count, 2)
        self.assertEqual(result.report.clock.elapsed_span_s, 299/30)
        self.assertEqual(len(result.report.mapped_joint_gaps), 1)
        self.assertFalse(result.report.to_dict()['usable_action_approved'])
        self.assertNotIn('first_vertices', result.report.to_dict())
        self.assertIn(self.f.database, result.watch_paths)
        self.assertIn(self.f.database.parent.parent, result.watch_paths)
        self.assertEqual(set(result.watch_paths), {path for path, stamp in result.watched_identities
            if stamp != (0, 0, 0, 0)})
        with self.assertRaises(FrozenInstanceError): result.database_path = Path('other')

    def test_memory_cache_must_match_original_captured_binding_hash(self):
        self.f.cache.packed = b'OTHER_UNBOUND_CACHE'
        with self.assertRaisesRegex(ValidationError, 'cache bytes differ'): self.load()

    def test_hardlink_added_during_final_logical_guard_fails_without_rehash(self):
        link_directory = self.f.root/'unwatched-links'; link_directory.mkdir()
        self.f.refresh()
        def add_link(*args, **kwargs):
            self.f.logical()
            os.link(self.f.source, link_directory/'new-link')
        with patch.object(job, 'check_target_action_catalog', side_effect=add_link):
            with self.assertRaisesRegex(ProjectStorageError, 'single-link'): self.load()

    def test_explicit_confirmation_and_typed_selection_required(self):
        for value in (False, 1, 'true'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.load(local_preview_confirmed=value)
        with self.assertRaises(ValidationError): self.load(selection=self.f.selection.to_dict())
        self.loader.assert_not_called()

    def test_pre_cancel_and_guard_cancel(self):
        event = Event(); event.set()
        with self.assertRaisesRegex(ProjectStorageError, 'cancelled'): self.load(cancel=event)
        result = self.load()
        with self.assertRaisesRegex(ProjectStorageError, 'cancelled'): result.guard(cancel=event)

    def test_background_guard_uses_fresh_budget_after_initial_deadline(self):
        readers = []
        original = job.ProofReads
        def collect(budget):
            result = original(budget); readers.append(result); return result
        with patch.object(job, 'ProofReads', side_effect=collect): value = self.load()
        readers[0].budget.deadline = -1
        value.guard(timeout_s=60)

    def test_duplicate_metadata_keys_are_rejected_from_captured_bytes(self):
        raw = b'{"full_timeline_frames":[],"full_timeline_frames":[]}'
        self.f.timeline.write_bytes(raw)
        from hashlib import sha256
        self.f.binding.file_map['body_first/target_timeline.json'].sha256 = sha256(raw).hexdigest()
        self.f.binding.file_map['body_first/target_timeline.json'].bytes = len(raw)
        self.f.prepared.watched_inputs = tuple((path, sha256(path.read_bytes()).hexdigest())
            for path, _ in self.f.prepared.watched_inputs)
        from ucc.jobs.godot_candidate_inputs import identity
        self.f.prepared.watched_identities = tuple((path, identity(path))
            for path, _ in self.f.prepared.watched_identities)
        with self.assertRaises(ValidationError): self.load()

    def test_relative_catalog_path_rejected(self):
        with self.assertRaisesRegex(ProjectStorageError, 'noncanonical'):
            self.load(database_path=Path('synthetic.sqlite'))

    def test_stale_current_selection_propagates_existing_loader_rejection(self):
        self.loader.side_effect = ProjectConflict('selection stale')
        with self.assertRaisesRegex(ProjectConflict, 'stale'): self.load()

    def test_hash_mismatch_after_typed_admission_fails(self):
        self.f.timeline.write_bytes(self.f.timeline.read_bytes()+b' ')
        with self.assertRaises(ProjectStorageError): self.load()

    def test_malformed_nonfinite_and_misordered_timeline_rejected(self):
        for mutate in (lambda d:d['full_timeline_frames'][0].update(root_world_head=[float('nan'),0,0]),
                       lambda d:d['full_timeline_frames'][2].update(frame=1),
                       lambda d:d.update(full_timeline_frames=[])):
            with self.subTest(mutate=mutate):
                f = DiagnosticJobsFixture(Path(tempfile.mkdtemp()).resolve())
                self.addCleanup(__import__('shutil').rmtree, f.root)
                self.f = f; mutate(f.data); f.refresh()
                with self.assertRaises(ValidationError): self.load()

    def test_same_identity_size_mtime_byte_change_rejected_by_original_hash(self):
        value = self.load(); stat = self.f.source.stat()
        self.f.source.write_bytes(b'changed!')
        os.utime(self.f.source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaises(ProjectStorageError): value.guard()

    def test_committed_wal_policy_revocation_is_not_adopted(self):
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL'); writer.execute('PRAGMA wal_autocheckpoint=0')
        value = self.load(); before = self.f.database.read_bytes()
        writer.execute('UPDATE policy SET allowed=0'); writer.commit()
        self.assertEqual(before, self.f.database.read_bytes())
        with self.assertRaises(AssetPolicyError): value.guard()

    def test_late_revocation_after_measurement_rejected_by_final_logical_guard(self):
        original = job.measure_target_action_diagnostic
        def revoke(*args, **kwargs):
            report = original(*args, **kwargs)
            with closing(sqlite3.connect(self.f.database)) as db:
                db.execute('UPDATE policy SET allowed=0'); db.commit()
            return report
        with patch.object(job, 'measure_target_action_diagnostic', side_effect=revoke):
            with self.assertRaises(AssetPolicyError): self.load()

    def test_fresh_guard_does_not_rebaseline_successful_reload(self):
        value = self.load()
        def replace_source(*args, **kwargs):
            self.f.source.write_bytes(b'changed!'); self.f.refresh(); return self.f.prepared
        self.loader.side_effect = replace_source
        with self.assertRaises(ProjectStorageError): value.guard()

    def test_wal_commit_after_logical_read_is_caught_by_final_byte_fence(self):
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL'); writer.execute('PRAGMA wal_autocheckpoint=0')
        def read_then_revoke(*args, **kwargs):
            self.f.logical()
            writer.execute('UPDATE policy SET allowed=0'); writer.commit()
        with patch.object(job, 'check_target_action_catalog', side_effect=read_then_revoke):
            with self.assertRaisesRegex(ProjectStorageError, 'semantic bytes changed'): self.load()

    def test_original_catalog_identity_is_not_rebaselined_after_measurement(self):
        original = job.measure_target_action_diagnostic
        def replace_catalog(*args, **kwargs):
            report = original(*args, **kwargs)
            other = self.f.root/'replacement.sqlite'
            other.write_bytes(self.f.database.read_bytes()); other.replace(self.f.database)
            return report
        # Exercise the real identity part even though the selected logical rows
        # are deliberately synthetic in this fixture.
        def logical(database, source, *, expected_database_identity, expected_parent_identity):
            from ucc.jobs.godot_candidate_inputs import identity
            if identity(database)[:2] != expected_database_identity:
                raise ProjectConflict('Original catalog identity replaced')
            self.f.logical()
        with patch.object(job, 'measure_target_action_diagnostic', side_effect=replace_catalog), \
                patch.object(job, 'check_target_action_catalog', side_effect=logical):
            with self.assertRaises(ProjectConflict): self.load()
