"""Original walk orchestration regressions using nonshipping worker replies."""
from hashlib import sha256
import json
import shutil
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture
from ucc.core.authored_walk_job import AUTHOR, INPUT_BINDINGS, INTENT, REOPEN_BINDINGS, VERIFY, read_walk_intent
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle_evidence import INSPECT
from ucc.jobs.authored_idle_io import private_bytes
from ucc.jobs.authored_walk import (
    AUTHOR_REPORT, AUTHOR_STATUS, CONTACT_CHECKS, RECEIPT, SNAPSHOT, UNAPPROVED, VERIFY_REPORT, VERIFY_STATUS,
    author_original_walk,
)
from ucc.jobs.protocol import JobRequest, JobResult


class AuthoredWalkHostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = HostFixture(temporary.name)
        self.cancel = Event()
        self.fail_gate = False
        self.cancel_on_verify = False

    def run_host(self):
        with patch('ucc.jobs.authored_walk.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = self.worker
            return author_original_walk(self.fixture.store, **self.fixture.args(), cancel=self.cancel, timeout_s=90)

    def worker(self, job, *, staged_inputs, timeout_s, cancel):
        if job.operation == INSPECT:
            return self.fixture.run(job, staged_inputs=staged_inputs, timeout_s=timeout_s, cancel=cancel)
        self.fixture.calls.append(job)
        folder = self.fixture.store.root / '.ucc-jobs' / job.job_id
        folder.mkdir()
        for name, source in staged_inputs.items():
            shutil.copyfile(source, folder / name)
        (folder / 'request.json').write_bytes(canonical_bytes(job.as_dict()))
        options = dict(job.options)
        read_walk_intent((folder / INTENT).read_bytes(), options, self.fixture.inspection)
        target = json.loads((folder / 'idle_anatomical_frame.json').read_bytes())['target']

        def row(name):
            payload = (folder / name).read_bytes()
            return {'bytes': len(payload), 'sha256': sha256(payload).hexdigest()}

        if job.operation == AUTHOR:
            for name in REOPEN_BINDINGS:
                (folder / name).write_bytes(b'NONSHIPPING worker boundary only')
            report = {'policy': 'UCC_PRIVATE_ORIGINAL_WALK_BAKE_V1',
                      'status': 'ORIGINAL_WALK_BAKED_PENDING_INDEPENDENT_REOPEN',
                      'input_pins': {name: row(name) for name in INPUT_BINDINGS},
                      'files': {name: row(name) for name in REOPEN_BINDINGS},
                      'neutral_rest_sha256': target['rest_sha256'], 'stored_action_samples': 300,
                      'usable_action_approved': False, 'visual_quality_approved': False,
                      'contact_quality_approved': False, 'engine_import_verified': False}
            (folder / AUTHOR_REPORT).write_bytes(private_bytes(report))
            status, names = AUTHOR_STATUS, (*REOPEN_BINDINGS, AUTHOR_REPORT)
        else:
            (folder / SNAPSHOT).write_bytes(b'NONSHIPPING normalized snapshot stub')
            report = {'schema_version': 1, 'policy': 'UCC_ORIGINAL_WALK_VERIFICATION_V1', 'status': VERIFY_STATUS,
                      'target': target, 'staged_inputs_preserved': True, **dict.fromkeys(UNAPPROVED, False),
                      'request_sha256': options['request_sha256'], 'walk_request_sha256': options['walk_request_sha256'],
                      'input_sha256': {name: options[key] for name, key in (INPUT_BINDINGS | REOPEN_BINDINGS).items()},
                      'source_snapshot': {'name': SNAPSHOT, **row(SNAPSHOT)},
                      'technical_contact_checks': dict.fromkeys(CONTACT_CHECKS, True),
                      'saved_bake': {'frames': 300, 'evaluated_visible_vertices': 13380,
                                     'stored_clock': [1, 300, 30], 'virtual_frame_stored': False},
                      'fbx_reimport': {'import_clock': [2, 301, 30], 'exact_full_timeline_compared': True,
                                       'virtual_frame_stored': False},
                      'root_motion': 'IN_PLACE', 'armature_root_offset_m': [0., 0., -.045]}
            if self.fail_gate:
                report['technical_contact_checks']['compensated_stance_drift'] = False
            (folder / VERIFY_REPORT).write_bytes(private_bytes(report))
            status, names = VERIFY_STATUS, (VERIFY_REPORT, SNAPSHOT)
        result = JobResult(job.job_id, job.operation, 'ok', {'status': status, 'outputs': {n: row(n) for n in names}})
        (folder / 'result.json').write_bytes(private_bytes(result.as_dict()))
        if job.operation == VERIFY and self.cancel_on_verify:
            self.cancel.set()
        return result, folder

    def test_private_receipt_binds_three_distinct_workers_and_every_delivered_file(self):
        fixture = self.fixture
        before = fixture.store.file.read_bytes(), fixture.master.read_bytes(), fixture.database.read_bytes()
        candidate = self.run_host()
        self.assertEqual(before, (fixture.store.file.read_bytes(), fixture.master.read_bytes(), fixture.database.read_bytes()))
        jobs = fixture.calls
        self.assertEqual([job.operation for job in jobs], [INSPECT, AUTHOR, VERIFY])
        self.assertEqual(len({job.job_id for job in jobs}), 3)
        self.assertTrue(candidate.fbx_path.is_file() and candidate.review_path.is_file())
        receipt_payload = (candidate.directory / RECEIPT).read_bytes()
        self.assertEqual(sha256(receipt_payload).hexdigest(), candidate.receipt_sha256)
        receipt = json.loads(receipt_payload)
        self.assertTrue(all(receipt[key] is False for key in UNAPPROVED))
        self.assertEqual(set(receipt['files']), {p.name for p in candidate.directory.iterdir()} - {RECEIPT})
        for name, binding in receipt['files'].items():
            payload = (candidate.directory / name).read_bytes()
            self.assertEqual(binding, {'bytes': len(payload), 'sha256': sha256(payload).hexdigest()})
        self.assertEqual(receipt['files'][SNAPSHOT]['sha256'], candidate.snapshot_sha256)
        self.assertFalse(any((fixture.store.root / '.ucc-jobs' / job.job_id / 'NEVER_CONSUME.motion').exists()
                             for job in jobs))

    def test_failed_contact_check_leaves_destination_unpublished(self):
        self.fail_gate = True
        with self.assertRaisesRegex(ValidationError, 'all nine contact'):
            self.run_host()
        self.assertFalse(self.fixture.destination.path.exists())

    def test_cancelled_verification_leaves_destination_unpublished(self):
        self.cancel_on_verify = True
        with self.assertRaisesRegex(ProjectStorageError, 'cancelled by caller'):
            self.run_host()
        self.assertFalse(self.fixture.destination.path.exists())

    def test_walk_worker_envelopes_reject_missing_or_extra_provenance(self):
        pins = dict.fromkeys(INPUT_BINDINGS.values(), 'a' * 64)
        JobRequest.new(AUTHOR, input_project='candidate.blend', options=pins)
        with self.assertRaisesRegex(ValidationError, 'closed phase'):
            JobRequest.new(VERIFY, input_project='candidate.blend', options=pins)
        with self.assertRaisesRegex(ValidationError, 'closed phase'):
            JobRequest.new(AUTHOR, input_project='candidate.blend', options={**pins, 'arbitrary_path': 'outside'})
