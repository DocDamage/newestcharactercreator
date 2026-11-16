"""Filesystem/catalog transaction faults; explicitly stubbed native admission."""
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from threading import Event
import time

from fixtures.target_action_logic import TargetFixture
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.jobs.godot_candidate_inputs import identity
from ucc.jobs.skin_material_preparation import _BudgetCancel
from ucc.jobs.target_action import (load_target_action, list_target_action_bindings,
    read_target_action_binding, check_target_action_catalog, review_target_action_source)


class TargetActionStorageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.f = TargetFixture(Path(temp.name).resolve())
        self.directory, self.binding = self.f.payload()
        self.cache = object()  # Explicit native-reader test double, never a real cache.

    def load(self, **kwargs):
        with patch('ucc.jobs.target_action_evidence.validate_retained_target_action', return_value=self.cache):
            return load_target_action(self.f.store, binding_sha256=self.binding.sha256, **self.f.load_args(), **kwargs)

    def test_metadata_listing_is_explicit_and_load_rehydrates_same_sealed_binding(self):
        summaries = list_target_action_bindings(self.f.store, clip_id=self.f.clip_id)
        self.assertEqual([row.binding_sha256 for row in summaries], [self.binding.sha256])
        result = self.load()
        self.assertIs(result.cache, self.cache)
        self.assertEqual(result.binding_sha256, self.binding.sha256)
        self.assertEqual(read_target_action_binding(self.f.store, self.binding.sha256), self.binding)
        self.assertIn((self.f.database, (*identity(self.f.database)[:2], 0, 0)), result.watched_identities)
        self.assertNotIn(self.f.database, dict(result.watched_inputs))

    def test_changed_extra_missing_and_empty_cache_directory_reject_before_native_reader(self):
        for fault in ('changed', 'extra', 'missing', 'directory'):
            with self.subTest(fault=fault):
                path = self.directory/'playback/motion_skin.bin'
                original = path.read_bytes()
                extra = self.directory/('Library' if fault == 'directory' else 'extra.bin')
                if fault == 'changed': path.write_bytes(original+b'!')
                elif fault == 'missing': path.unlink()
                elif fault == 'directory': extra.mkdir()
                else: extra.write_bytes(b'FOREIGN')
                with patch('ucc.jobs.target_action_evidence.validate_retained_target_action') as reader:
                    with self.assertRaises(ProjectStorageError):
                        load_target_action(self.f.store, binding_sha256=self.binding.sha256, **self.f.load_args())
                    reader.assert_not_called()
                if not path.exists() or path.read_bytes() != original: path.write_bytes(original)
                if extra.exists(): extra.rmdir() if extra.is_dir() else extra.unlink()

    def test_project_bytes_and_explicit_source_or_catalog_tokens_must_match(self):
        args = self.f.load_args()
        for field in ('expected_project_sha256','expected_source_binding_sha256','expected_catalog_record_sha256'):
            with self.subTest(field=field), self.assertRaises(ProjectConflict):
                load_target_action(self.f.store, binding_sha256=self.binding.sha256, **(args|{field:'f'*64}))

    def test_same_byte_source_replacement_during_native_validation_rejects(self):
        def replace_source(*args, **kwargs):
            original = self.f.source.read_bytes()
            old = self.f.source.with_suffix('.original'); self.f.source.rename(old)
            self.f.source.write_bytes(original)
            return self.cache
        with patch('ucc.jobs.target_action_evidence.validate_retained_target_action', side_effect=replace_source):
            with self.assertRaises(ProjectStorageError):
                load_target_action(self.f.store, binding_sha256=self.binding.sha256, **self.f.load_args())

    def test_complete_callback_cannot_handoff_changed_proof_or_source(self):
        def progress(phase):
            if phase == 'COMPLETE': (self.directory/'playback/motion_skin.bin').write_bytes(b'CHANGED')
        with self.assertRaises(ProjectStorageError): self.load(progress=progress)

    def test_host_code_change_during_saved_admission_blocks_cache_handoff(self):
        host=self.f.root/'mock-host/ucc/jobs';host.mkdir(parents=True)
        selected=host/'target_action_evidence.py';selected.write_text('# NONSHIPPING reader marker\n')
        def changed(*args,**kwargs):
            selected.write_text('# NONSHIPPING changed reader marker\n')
            return self.cache
        with patch('ucc.jobs.target_action_resources.__file__',str(host/'target_action_resources.py')):
            with patch('ucc.jobs.target_action_evidence.validate_retained_target_action',side_effect=changed):
                with self.assertRaisesRegex(ProjectStorageError,'host code'):
                    load_target_action(self.f.store,binding_sha256=self.binding.sha256,**self.f.load_args())

    def test_nested_deadline_and_user_cancel_classify_without_native_work(self):
        user = Event()
        for cancel, text in ((_BudgetCancel(user, time.monotonic()-1), 'total deadline'), (user, 'cancelled')):
            if cancel is user: user.set()
            with self.subTest(reason=text), self.assertRaisesRegex(ProjectStorageError, text): self.load(cancel=cancel)

    def test_catalog_semantic_guard_allows_empty_wal_but_rejects_committed_policy_in_wal(self):
        args = {'expected_database_identity':identity(self.f.database)[:2],
                'expected_parent_identity':identity(self.f.database.parent)[:2]}
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        with writer:
            writer.execute('PRAGMA journal_mode=WAL')
            check_target_action_catalog(self.f.database, self.f.review.source, **args)
            raw = json.loads(writer.execute('SELECT license_json FROM asset_sources').fetchone()[0])
            raw['no_ai'] = False
            writer.execute('UPDATE asset_sources SET license_json=?', (json.dumps(raw),)); writer.commit()
            with self.assertRaises(ProjectConflict):
                check_target_action_catalog(self.f.database, self.f.review.source, **args)

    def test_registered_id_is_required_and_never_stripped(self):
        before = self.f.store.file.read_bytes()
        self.load()
        self.assertEqual(self.f.store.file.read_bytes(), before)
        self.assertEqual(self.f.store.load().animations, (self.f.clip_id,))

    def test_catalog_database_replacement_during_semantic_read_rejects(self):
        expected=identity(self.f.database)[:2]
        parent=identity(self.f.database.parent)[:2]
        def replaced(*args):
            original=self.f.database.read_bytes()
            self.f.database.rename(self.f.database.with_suffix('.old'))
            self.f.database.write_bytes(original)
            return self.f.review.source.catalog_record_sha256
        with patch('ucc.jobs.target_action_context.catalog_record',side_effect=replaced):
            with self.assertRaises(ProjectConflict):
                check_target_action_catalog(self.f.database,self.f.review.source,
                    expected_database_identity=expected,expected_parent_identity=parent)

    def test_catalog_exclusive_lock_fails_with_short_metadata_wait(self):
        writer = sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=DELETE')
        writer.execute('BEGIN EXCLUSIVE')
        start=time.monotonic()
        with self.assertRaises(ProjectStorageError):
            check_target_action_catalog(self.f.database,self.f.review.source,
                expected_database_identity=identity(self.f.database)[:2],
                expected_parent_identity=identity(self.f.database.parent)[:2])
        self.assertLess(time.monotonic()-start,1.)

    def test_clean_wal_read_coordination_stabilizes_namespace_without_ignoring_rows(self):
        writer=sqlite3.connect(self.f.database)
        writer.execute('PRAGMA journal_mode=WAL'); writer.close()
        args={'expected_database_identity':identity(self.f.database)[:2],
              'expected_parent_identity':identity(self.f.database.parent)[:2]}
        def namespace():
            return {p.name for p in self.f.database.parent.iterdir()
                    if p.name.startswith(self.f.database.name)}
        check_target_action_catalog(self.f.database,self.f.review.source,**args)
        warmed=namespace()
        for _ in range(10):
            check_target_action_catalog(self.f.database,self.f.review.source,**args)
            self.assertEqual(namespace(),warmed)
        # This asserts namespace stability only: SHM timestamps can still change
        # on every read and GUI notification handlers must coalesce those events.

    def test_oversized_selected_metadata_is_rejected_before_python_fetch(self):
        writer=sqlite3.connect(self.f.database); self.addCleanup(writer.close)
        writer.execute('UPDATE animation_sources SET warnings_json=?',('x'*(2*1024*1024+1),)); writer.commit()
        with self.assertRaises((ProjectStorageError,ValidationError)):
            check_target_action_catalog(self.f.database,self.f.review.source,
                expected_database_identity=identity(self.f.database)[:2],
                expected_parent_identity=identity(self.f.database.parent)[:2])
