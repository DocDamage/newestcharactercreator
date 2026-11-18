"""Finite private evidence/receipt boundaries using invented test-only values."""
from hashlib import sha256
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures.authored_idle_contract import metadata
from fixtures.authored_idle_host import HostFixture
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import read_document
from ucc.jobs.authored_idle_evidence import read_idle_json, checked_frame, record
from ucc.jobs.authored_idle_io import private_bytes
from ucc.jobs.target_action_context import Budget


class IdleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()/'evidence.json'; self.budget = Budget(None,60)

    def test_private_frame_exceeding_intent_limit_admitted_with_exact_utf8_hash(self):
        frame = HostFixture.frame(metadata()[1]); frame['neutral']['human_name'] = 'NONSHIPPING_é'
        for side in ('L','R'):
            frame['sole_patches'][side] = {'indices': list(range(2048)),
                'neutral_world': [[1.123456789012345,2.234567890123456,3.345678901234567]]*2048}
        payload = private_bytes(frame); self.assertGreater(len(payload),256*1024)
        self.path.write_bytes(payload); pin = sha256(payload).hexdigest()
        parsed = read_idle_json(self.path,self.budget,pin)
        checked_frame(parsed,metadata()[1],pin,{'bone_count':163,'skeleton_fingerprint':frame['skeleton_fingerprint']})
        with self.assertRaises(ValidationError): read_document(payload)

    def test_duplicate_private_field_error_never_contains_untrusted_key(self):
        sentinel='NONSHIPPING_PRIVATE_SENTINEL'
        self.path.write_bytes(('{"'+sentinel+'":1,"'+sentinel+'":2}').encode())
        with self.assertRaises(ValidationError) as caught: read_idle_json(self.path,self.budget)
        self.assertNotIn(sentinel,str(caught.exception)); self.assertTrue(caught.exception.__suppress_context__)

    def test_overflow_nonfinite_and_duplicate_documents_rejected(self):
        for payload in (b'{"x":1e999}',b'{"x":NaN}',b'{"x":1,"x":2}'):
            self.path.write_bytes(payload)
            with self.subTest(payload=payload), self.assertRaises(ValidationError): read_idle_json(self.path,self.budget)

    def test_raced_growth_is_stopped_before_more_than_limit_plus_one_is_read(self):
        self.path.write_bytes(b'1234'); requests=[]
        class Growth(io.BytesIO):
            def read(self,n=-1): requests.append(n); return super().read(n)
        with patch.object(Path,'open',return_value=Growth(b'1234567890123456')):
            with self.assertRaisesRegex(ValidationError,'grew'): record(self.path,self.budget,maximum=4)
        self.assertEqual(requests,[5])

    def test_selected_raw_legacy_bytes_cannot_be_replaced_by_recanonicalized_bytes(self):
        payload=b'{ "z":1, "a":2 }'; self.path.write_bytes(payload)
        self.assertEqual(read_idle_json(self.path,self.budget,sha256(payload).hexdigest(),canonical=False),{'z':1,'a':2})
        with self.assertRaises(ValidationError): read_idle_json(self.path,self.budget,sha256(private_bytes({'z':1,'a':2})).hexdigest(),canonical=False)


if __name__=='__main__': unittest.main()
