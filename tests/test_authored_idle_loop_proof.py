"""Exclusive proof publication against nonshipping retained authoring evidence."""

from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture, pin
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle import author_original_idle
from ucc.jobs.authored_idle_loop_preview import POLICY, _pointer
from ucc.jobs.authored_idle_loop_proof import PROOF_FILENAME, publish_authored_idle_loop_proof
from ucc.jobs.authored_idle_transactions import IdlePublication
from ucc.jobs.export_destination import plan_destination


class AuthoredIdleLoopProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fixture = HostFixture(temp.name)
        with patch('ucc.jobs.authored_idle.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = self.fixture.run
            self.candidate = author_original_idle(self.fixture.store, **self.fixture.args(), timeout_s=120)
        self.output = self.candidate.directory.parent/'local-proof'
        self.destination = plan_destination(self.output, self.fixture.store.root)

    def publish(self, **changes):
        fixture = self.fixture
        arguments = dict(directory=self.candidate.directory, expected_receipt_sha256=self.candidate.receipt_sha256,
            source_policy_records=fixture.records, database_path=fixture.database, blender_exe=fixture.blender,
            worker_script=fixture.worker, destination=self.destination)
        with patch('ucc.jobs.runner.run_process', side_effect=AssertionError('Proof must never start a worker')):
            return publish_authored_idle_loop_proof(fixture.store, **(arguments | changes))

    def assert_no_output(self):
        self.assertEqual(set(self.output.parent.iterdir()), {self.candidate.directory})

    def test_publishes_exact_canonical_proof_and_leaves_original_inputs(self):
        fixture = self.fixture
        before = {path: pin(path.read_bytes()) for path in fixture.root.rglob('*') if path.is_file()}
        result = self.publish()
        self.assertEqual(result.path, self.output/PROOF_FILENAME)
        payload = result.path.read_bytes()
        pointer = _pointer(payload)
        self.assertEqual(pointer, {'schema_version': 1, 'policy': POLICY, 'project_root': str(fixture.store.root),
            'catalog_path': str(fixture.database), 'candidate_directory': str(self.candidate.directory),
            'receipt_sha256': self.candidate.receipt_sha256,
            'source_policy_records': [{'asset_id': row.asset_id, 'path': str(row.path), 'sha256': row.sha256}
                                      for row in fixture.records],
            'blender_executable': {'path': str(fixture.blender), 'sha256': pin(fixture.blender.read_bytes())},
            'worker_script': {'path': str(fixture.worker), 'sha256': pin(fixture.worker.read_bytes())}})
        self.assertEqual(payload, canonical_bytes(pointer))
        self.assertEqual(result.sha256, pin(payload))
        self.assertEqual({path: pin(path.read_bytes()) for path in fixture.root.rglob('*')
                          if path.is_file() and path != result.path}, before)

    def test_refuses_wrong_receipt_and_revoked_policy(self):
        with self.assertRaises(ValidationError):
            self.publish(expected_receipt_sha256='0'*64)
        self.fixture.policy.write_bytes(self.fixture.policy.read_bytes() + b' ')
        with self.assertRaises(ProjectConflict):
            self.publish()
        self.assert_no_output()

    def test_refuses_candidate_project_catalog_and_tool_destinations(self):
        fixture = self.fixture
        for path in (self.candidate.directory/'proof', fixture.store.root/'proof',
                     Path(str(fixture.database)+'-wal'), fixture.blender.parent/'proof', fixture.worker.parent/'proof'):
            with self.subTest(path=path), self.assertRaisesRegex(ValidationError, 'outside'):
                self.publish(destination=plan_destination(path, fixture.store.root))
            self.assertFalse(path.exists())

    def test_refuses_raced_destination_and_cleans_only_the_owned_stage(self):
        commit = IdlePublication.commit

        def race_before_commit(publication, guard, budget):
            self.output.mkdir()
            (self.output/'foreign').write_bytes(b'foreign data')
            return commit(publication, guard, budget)

        with patch.object(IdlePublication, 'commit', race_before_commit), self.assertRaises(ProjectStorageError):
            self.publish()
        self.assertEqual((self.output/'foreign').read_bytes(), b'foreign data')
        self.assertFalse((self.output/PROOF_FILENAME).exists())
        self.assertEqual(set(self.output.parent.iterdir()), {self.output, self.candidate.directory})

    def test_rechecks_tool_identity_and_cancel_inside_publication(self):
        commit = IdlePublication.commit
        cancel = Event()

        def cancel_before_commit(publication, guard, budget):
            cancel.set()
            return commit(publication, guard, budget)

        with patch.object(IdlePublication, 'commit', cancel_before_commit), self.assertRaisesRegex(ProjectStorageError, 'cancelled'):
            self.publish(cancel=cancel)
        self.assert_no_output()

        def change_tool_before_commit(publication, guard, budget):
            worker = self.fixture.worker
            worker.write_bytes(worker.read_bytes() + b'changed')
            return commit(publication, guard, budget)

        with patch.object(IdlePublication, 'commit', change_tool_before_commit), self.assertRaisesRegex(ProjectStorageError, 'source changed'):
            self.publish()
        self.assert_no_output()

    def test_refuses_staged_bytes_substituted_before_snapshot_and_preserves_them(self):
        initialize = IdlePublication.__init__
        edits = []

        def edit_staged_proof(publication, store, destination, stage, names, budget):
            path = stage/PROOF_FILENAME
            path.write_bytes(b'foreign edit')
            edits.append(path)
            initialize(publication, store, destination, stage, names, budget)

        with patch.object(IdlePublication, '__init__', edit_staged_proof):
            with self.assertRaisesRegex(ProjectStorageError, 'canonical pointer'):
                self.publish()
        self.assertFalse(self.output.exists())
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].read_bytes(), b'foreign edit')
