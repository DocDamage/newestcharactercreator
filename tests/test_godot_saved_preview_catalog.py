"""Final catalog byte fences; synthetic coordination files, no app catalog."""
from pathlib import Path
import tempfile
import unittest
from ucc.core.errors import ProjectStorageError
from ucc.jobs.godot_saved_preview_catalog import final_catalog_guard
from ucc.jobs.target_action_context import Budget


class SavedCatalogFenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve();self.db=self.root/'synthetic.sqlite';self.db.write_bytes(b'NOT_AN_SQLITE_DATABASE')
    def fence(self,operation):return final_catalog_guard(self.db,Budget(None,60),operation)
    def test_only_known_empty_WAL_and_SHM_readmark_changes_can_be_adopted(self):
        wal=self.db.with_name(self.db.name+'-wal');shm=self.db.with_name(self.db.name+'-shm');shm.write_bytes(b'old read marks')
        def readonly_effects():wal.write_bytes(b'');shm.write_bytes(b'new read marks')
        stamps=self.fence(readonly_effects);self.assertEqual(stamps[wal][2],0);self.assertNotEqual(stamps[shm],(0,0,0,0))
    def test_nonempty_WAL_change_rejects_even_if_main_unchanged(self):
        wal=self.db.with_name(self.db.name+'-wal');wal.write_bytes(b'old committed pages')
        with self.assertRaisesRegex(ProjectStorageError,'semantic bytes changed'):self.fence(lambda:wal.write_bytes(b'new committed pages'))
    def test_main_same_bytes_replacement_rejects(self):
        def replace():
            other=self.root/'replacement.sqlite';other.write_bytes(self.db.read_bytes());other.replace(self.db)
        with self.assertRaisesRegex(ProjectStorageError,'semantic bytes changed'):self.fence(replace)
    def test_journal_namespace_creation_rejects_even_empty(self):
        journal=self.db.with_name(self.db.name+'-journal')
        with self.assertRaisesRegex(ProjectStorageError,'semantic bytes changed'):self.fence(lambda:journal.write_bytes(b''))
