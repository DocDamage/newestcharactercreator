"""Real temporary filesystem ownership/journal fault tests; no native processes."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ucc.core.errors import ProjectStorageError
from ucc.core.storage import ProjectStore
from ucc.jobs.authored_idle_transactions import IdlePublication, write_journal
from ucc.jobs.export_destination import plan_destination, rename_new
from ucc.jobs.target_action_context import Budget
from ucc.jobs.godot_candidate_inputs import identity


class IdleTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.store = ProjectStore(self.root/'project')
        self.store.root.mkdir(); self.work = self.root/'work'; self.work.mkdir()
        self.output = self.root/'output'; self.output.mkdir()
        self.destination = plan_destination(self.output/'new', self.store.root)

    def publication(self):
        stage = self.destination.stage('synthetic'); (stage/'owned.bin').write_bytes(b'OWNED')
        publication = IdlePublication(self.store, self.destination, stage, {'owned.bin'}, Budget(None,60))
        publication.commit(lambda: None, Budget(None,60)); return publication

    def test_clean_owned_publication_can_be_withdrawn_after_cancel(self):
        publication = self.publication(); error = ProjectStorageError('cancelled')
        publication.withdraw(error)
        self.assertFalse(self.destination.path.exists()); self.assertTrue(publication.stage.is_dir())

    def test_same_bytes_foreign_inode_replacement_is_preserved(self):
        publication = self.publication(); target = self.destination.path/'owned.bin'
        replacement = self.root/'foreign.bin'; replacement.write_bytes(target.read_bytes()); os.replace(replacement,target)
        stamp = target.stat().st_ino; error = ProjectStorageError('late failure'); publication.withdraw(error)
        self.assertTrue(self.destination.path.is_dir()); self.assertEqual(target.stat().st_ino,stamp)
        self.assertFalse(publication.stage.exists()); self.assertTrue(error.__notes__)

    def test_foreign_added_file_is_not_moved_or_deleted(self):
        publication = self.publication(); foreign = self.destination.path/'user.txt'; foreign.write_bytes(b'USER')
        publication.withdraw(ProjectStorageError('late'))
        self.assertEqual(foreign.read_bytes(), b'USER'); self.assertFalse(publication.stage.exists())

    def test_phase_journal_never_overwrites_foreign_regular_record(self):
        target = self.work/'job_status-FAILED.json'; target.write_bytes(b'USER')
        with self.assertRaises(ProjectStorageError): write_journal(self.work,'a'*64,'FAILED')
        self.assertEqual(target.read_bytes(), b'USER')

    def test_journal_publish_race_preserves_foreign_target(self):
        target = self.work/'job_status-STARTED.json'
        def race(source,destination): target.write_bytes(b'USER'); rename_new(source,destination)
        with patch('ucc.jobs.authored_idle_transactions.rename_new',side_effect=race):
            with self.assertRaises(OSError): write_journal(self.work,'a'*64,'STARTED')
        self.assertEqual(target.read_bytes(),b'USER'); self.assertFalse((self.work/'job_status.tmp').exists())

    def test_one_time_fsync_failure_allows_separate_failed_journal(self):
        real = os.fsync; calls = []
        def fault(fd):
            calls.append(fd)
            if len(calls)==1: raise OSError('synthetic fsync failure')
            real(fd)
        with patch('ucc.jobs.authored_idle_transactions.os.fsync', side_effect=fault):
            with self.assertRaisesRegex(OSError,'synthetic'): write_journal(self.work,'a'*64,'STARTED')
            write_journal(self.work,'a'*64,'FAILED')
        self.assertTrue((self.work/'job_status-FAILED.json').is_file()); self.assertFalse((self.work/'job_status.tmp').exists())

    def test_replaced_foreign_journal_temporary_is_retained(self):
        temporary = self.work/'job_status.tmp'; held = self.root/'held-owned.tmp'
        def race(source,destination):
            source.rename(held); source.write_bytes(b'FOREIGN_TEMP'); raise OSError('synthetic rename fault')
        with patch('ucc.jobs.authored_idle_transactions.rename_new',side_effect=race):
            with self.assertRaises(OSError): write_journal(self.work,'a'*64,'STARTED')
        self.assertEqual(temporary.read_bytes(),b'FOREIGN_TEMP'); self.assertTrue(held.exists())

    def test_replaced_directory_before_owned_copy_is_not_written(self):
        from ucc.jobs.authored_idle import _copy_bound
        from ucc.jobs.authored_idle_evidence import record
        from ucc.core.errors import ValidationError
        source = self.root/'source.bin'; source.write_bytes(b'OWNED'); stamp=identity(self.work)
        def race(path,budget):
            row = record(path,budget); self.work.rename(self.root/'old-work'); self.work.mkdir(); return row
        with patch('ucc.jobs.authored_idle.record',side_effect=race):
            with self.assertRaises(ValidationError):
                _copy_bound(source,self.work/'output.bin',record(source,Budget(None,60))['sha256'],Budget(None,60),stamp)
        self.assertEqual(list(self.work.iterdir()),[])


if __name__=='__main__': unittest.main()
