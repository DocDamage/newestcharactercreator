"""NONSHIPPING filesystem receipt faults; mocked workers never prove Unity quality."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json
import os
from fixtures.unity_export_transaction import UnityTransactionFixture
from ucc.core.errors import ProjectStorageError
import ucc.jobs.unity_export as backend


class UnityReceiptCutoffTests(TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.f=UnityTransactionFixture(Path(temporary.name).resolve())
        self.mocks=[]
        for active in self.f.patches():
            self.mocks.append(active.start());self.addCleanup(active.stop)

    def invoke(self,**options):
        return backend.export_unity(self.f.store,**(self.f.options|options))

    def journal(self):
        path=self.f.store.root/'.ucc-jobs'/('unity-export-'+self.f.request.job_id)/'job_status.json'
        return json.loads(path.read_bytes())

    def assert_withdrawn_receipts_truthful(self):
        self.assertFalse(self.f.destination.path.exists())
        self.assertEqual(self.f.store.load(),self.f.project)
        self.assertTrue(self.journal()['rolled_back'])
        for stage in self.f.root.glob('.ucc-export-*'):
            receipt=stage/'export_receipt.json'
            if receipt.exists():
                record=json.loads(receipt.read_bytes())
                self.assertFalse(record['export_published'])
                self.assertFalse(record['final_payload_verified'])

    def test_receipt_fsync_failure_cannot_retain_success_claim_after_rollback(self):
        receipt=self.f.destination.path/'export_receipt.json';fired=[False];actual=os.fsync
        def fail_receipt(descriptor):
            if receipt.exists() and not fired[0]:
                fired[0]=True;raise OSError('UNIT_UNITY_RECEIPT_FSYNC_FAILURE')
            return actual(descriptor)
        with patch.object(backend.os,'fsync',side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError,'UNIT_UNITY_RECEIPT_FSYNC_FAILURE'):
                self.invoke()
        self.assertTrue(fired[0]);self.assert_withdrawn_receipts_truthful()

    def test_first_receipt_digest_deadline_cannot_retain_success_claim(self):
        receipt=self.f.destination.path/'export_receipt.json';clock=[0.];fired=[False]
        actual=backend._digest
        def expire(path,cancel=None):
            if Path(path)==receipt and not fired[0]:clock[0]=2.;fired[0]=True
            return actual(path,cancel)
        with patch.object(backend.time,'monotonic',side_effect=lambda:clock[0]),patch.object(backend,'_digest',side_effect=expire):
            with self.assertRaisesRegex(ProjectStorageError,'deadline'):
                self.invoke(timeout_s=1.)
        self.assertTrue(fired[0]);self.assertEqual(self.journal()['failure_reason'],'total_deadline')
        self.assert_withdrawn_receipts_truthful()

    def test_first_journal_fsync_preserves_raw_error_and_failed_diagnostics(self):
        work=self.f.store.root/'.ucc-jobs'/('unity-export-'+self.f.request.job_id)
        temporary=work/'job_status.tmp';fired=[False];actual=os.fsync
        def fail_journal(descriptor):
            if temporary.is_file() and not fired[0]:
                fired[0]=True;raise OSError('UNIT_UNITY_JOURNAL_FSYNC_FAILURE')
            return actual(descriptor)
        with patch.object(backend.os,'fsync',side_effect=fail_journal):
            with self.assertRaisesRegex(OSError,'UNIT_UNITY_JOURNAL_FSYNC_FAILURE'):
                self.invoke()
        self.assertTrue(fired[0]);self.assertFalse(temporary.exists())
        record=self.journal()
        self.assertEqual(record['state'],'FAILED');self.assertEqual(record['raw_error_type'],'OSError')
        self.assertIn('UNIT_UNITY_JOURNAL_FSYNC_FAILURE',record['raw_error'])
        self.assertFalse(record['export_published']);self.mocks[2].assert_not_called()
        self.assertEqual(self.f.store.load(),self.f.project)
