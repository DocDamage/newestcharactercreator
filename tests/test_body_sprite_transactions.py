"""Real exclusive rename/journal faults; no native scenes or rendered assets."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ucc.jobs.body_sprite_transactions import write_journal, BodySpritePublication
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.target_action_context import operation_budget


class BodySpriteTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.work = self.root/'job'; self.work.mkdir()
        project = self.root/'project'; project.mkdir(); self.store = SimpleNamespace(root=project)

    def test_one_off_initial_fsync_failure_preserves_error_and_allows_failed_journal(self):
        actual = os.fsync; count = [0]
        def fail_once(fd):
            count[0] += 1
            if count[0]==1: raise OSError('UNIT_INITIAL_FSYNC')
            return actual(fd)
        with patch('ucc.jobs.body_sprite_transactions.os.fsync',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'UNIT_INITIAL_FSYNC'): write_journal(self.work,'a'*64,'START')
            self.assertFalse((self.work/'job_status.tmp').exists())
            write_journal(self.work,'a'*64,'FAILED')
        self.assertEqual(json.loads((self.work/'job_status.json').read_text())['state'],'FAILED')

    def test_one_off_atomic_replace_failure_allows_failed_journal(self):
        actual = os.replace; count = [0]
        def fail_once(source,destination):
            count[0] += 1
            if count[0]==1: raise OSError('UNIT_REPLACE')
            return actual(source,destination)
        with patch('ucc.jobs.body_sprite_transactions.os.replace',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'UNIT_REPLACE'): write_journal(self.work,'a'*64,'START')
            write_journal(self.work,'a'*64,'FAILED')
        self.assertEqual(json.loads((self.work/'job_status.json').read_text())['state'],'FAILED')

    def test_replaced_foreign_journal_temporary_is_not_removed(self):
        def replace_foreign(source,destination):
            Path(source).unlink(); Path(source).write_bytes(b'UNIT_FOREIGN_TEMPORARY')
            raise OSError('UNIT_FOREIGN_REPLACEMENT')
        with patch('ucc.jobs.body_sprite_transactions.os.replace',side_effect=replace_foreign):
            with self.assertRaisesRegex(OSError,'UNIT_FOREIGN_REPLACEMENT'): write_journal(self.work,'a'*64,'START')
        self.assertEqual((self.work/'job_status.tmp').read_bytes(),b'UNIT_FOREIGN_TEMPORARY')

    def publication(self,budget):
        destination = plan_destination(self.root/'new-private-output',self.store.root)
        stage = destination.stage('UNIT_OWNER'); (stage/'frame.UNIT').write_bytes(b'UNIT_ONLY_NOT_AN_IMAGE')
        return BodySpritePublication(self.store,destination,stage,{'frame.UNIT'},budget)

    def test_clean_new_owned_publication_can_be_withdrawn_without_deletion(self):
        with operation_budget(None,30) as budget:
            publication = self.publication(budget); publication.commit(lambda:None,budget)
            error = RuntimeError('UNIT_POSTCOMMIT'); publication.withdraw(error)
            self.assertFalse(publication.destination.path.exists())
            self.assertEqual((publication.stage/'frame.UNIT').read_bytes(),b'UNIT_ONLY_NOT_AN_IMAGE')

    def test_foreign_modified_contents_inside_same_directory_are_not_relocated(self):
        with operation_budget(None,30) as budget:
            publication = self.publication(budget); publication.commit(lambda:None,budget)
            path = publication.destination.path/'frame.UNIT'; path.write_bytes(b'UNIT_FOREIGN_EDIT')
            error = RuntimeError('UNIT_POSTCOMMIT'); publication.withdraw(error)
            self.assertEqual(path.read_bytes(),b'UNIT_FOREIGN_EDIT'); self.assertFalse(publication.stage.exists())
            self.assertTrue(any('rollback failed' in note for note in error.__notes__))

    def test_foreign_added_file_inside_same_directory_is_not_relocated(self):
        with operation_budget(None,30) as budget:
            publication = self.publication(budget); publication.commit(lambda:None,budget)
            foreign = publication.destination.path/'foreign.txt'; foreign.write_text('UNIT_FOREIGN')
            error = RuntimeError('UNIT_POSTCOMMIT'); publication.withdraw(error)
            self.assertEqual(foreign.read_text(),'UNIT_FOREIGN'); self.assertFalse(publication.stage.exists())

    def test_raced_existing_destination_is_never_replaced(self):
        with operation_budget(None,30) as budget:
            publication = self.publication(budget)
            publication.destination.path.mkdir(); foreign = publication.destination.path/'foreign.txt'; foreign.write_text('UNIT_FOREIGN')
            from ucc.core.errors import ProjectStorageError
            with self.assertRaises(ProjectStorageError): publication.commit(lambda:None,budget)
            self.assertEqual(foreign.read_text(),'UNIT_FOREIGN'); self.assertTrue(publication.stage.exists())


if __name__ == '__main__': unittest.main()
