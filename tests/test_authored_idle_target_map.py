"""Proof-to-mapping handoff with a real catalog and invented retained worker evidence."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture, pin
from fixtures.fbx_snapshot_contract import report
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.catalog_clip import VerifiedCatalogClip
from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.animation_reference_storage import publish_source_binding
from ucc.jobs.authored_idle import author_original_idle
from ucc.jobs.authored_idle_loop_proof import publish_authored_idle_loop_proof
from ucc.jobs.authored_idle_target_map import MAPPING_FILENAME, publish_authored_idle_target_mapping
from ucc.jobs.authored_idle_transactions import IdlePublication
from ucc.jobs.catalog_clip import _saved_reference
from ucc.jobs.export_destination import plan_destination
from ucc.jobs.target_action_context import review_target_action_source
from ucc.library.provenance import LicensePolicy


class AuthoredIdleTargetMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp.cleanup)
        cls.source = HostFixture(temp.name)
        fixture = cls.source
        with patch('ucc.jobs.authored_idle.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = fixture.run
            cls.candidate = author_original_idle(fixture.store, **fixture.args(), timeout_s=120)
        cls.proof = publish_authored_idle_loop_proof(fixture.store, directory=cls.candidate.directory,
            expected_receipt_sha256=cls.candidate.receipt_sha256, source_policy_records=fixture.records,
            database_path=fixture.database, blender_exe=fixture.blender, worker_script=fixture.worker,
            destination=plan_destination(fixture.root/'outputs/proof', fixture.store.root)).path

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.source.root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.store = ProjectStore(self.root/'target')
        self.database = self.root/'target.sqlite3'
        self.output = self.root/'map'
        project = self.source.project
        master = self.store.root/project.master_blend
        master.parent.mkdir(parents=True)
        master.write_bytes(self.source.master.read_bytes())
        initial = self.store.save(replace(project, revision=0))
        fbx = self.candidate.directory/'original_idle.fbx'
        snapshot = (self.candidate.directory/'authored_idle_source_snapshot.json').read_bytes()
        data = json.loads(snapshot)
        policy = LicensePolicy('Nonshipping test', 'Invented private local review', 'local://unit',
                               reviewed=True, local_preview_allowed=True, no_ai=True)
        measured = report(data, snapshot) | validate_snapshot(data, self.candidate.source_sha256) | {
            'two_workers_agree': True, 'source_bytes_unchanged': True, 'policy': policy.to_dict()}
        asset_id = 'unit-idle'
        self.clip = asset_id+'#clip-0000'
        with AnimationCatalog(self.database) as catalog:
            catalog.index_file(asset_id, fbx, policy)
            catalog.record_fbx_intake(asset_id, data, measured, expected_entry=catalog.library.get(asset_id))
        entry, indexed, receipt, receipt_sha = _saved_reference(self.database, self.clip, self.candidate.source_sha256, policy)
        verified = VerifiedCatalogClip(self.clip, entry.asset_id, entry.sha256, policy, receipt['snapshot_sha256'],
            receipt_sha, receipt['skeleton_fingerprint'], 2, 301, indexed.clips[0])
        publish_source_binding(self.store, initial.project_id, verified)
        self.store.save(replace(initial, revision=initial.revision+1, animations=(self.clip,)),
                        expected_revision=initial.revision)

    def review(self):
        project = self.store.load()
        return review_target_action_source(self.store, database_path=self.database, clip_id=self.clip,
            expected_project_id=project.project_id, expected_revision=project.revision,
            expected_master_blend=project.master_blend, expected_project_sha256=pin(self.store.file.read_bytes()))

    def publish(self, **changes):
        arguments = dict(proof_file=self.proof, database_path=self.database, expected_review=self.review(),
                         destination=plan_destination(self.output, self.store.root))
        with patch('ucc.jobs.runner.run_process', side_effect=AssertionError('No native launch permitted')):
            return publish_authored_idle_target_mapping(self.store, **(arguments | changes))

    def test_publishes_ordinary_reviewed_profile_without_mutating_inputs(self):
        before = {path: pin(path.read_bytes()) for path in self.source.root.rglob('*') if path.is_file()}
        published = self.publish()
        review = self.review()
        self.assertEqual(published.path, self.output/MAPPING_FILENAME)
        profile, digest = read_native_profile(published.path, review.source.source_sha256,
                                             review.source.snapshot_sha256, review.master_sha256)
        self.assertEqual(digest, published.sha256)
        self.assertEqual(published.path.read_bytes(), canonical_bytes(profile))
        self.assertEqual({path: pin(path.read_bytes()) for path in self.source.root.rglob('*')
                          if path.is_file() and path != published.path}, before)

    def test_rejects_transitively_changed_proof_and_actual_wrong_target_master(self):
        original = self.source.policy.read_bytes()
        try:
            self.source.policy.write_bytes(original+b' ')
            with self.assertRaises(ProjectConflict):
                self.publish()
        finally:
            self.source.policy.write_bytes(original)
        alternate = b'BLENDER'+b'NONSHIPPING WRONG MASTER'*50
        relative = f'master/versions/{pin(alternate)}.blend'
        (self.store.root/relative).write_bytes(alternate)
        project = self.store.load()
        self.store.save(replace(project, revision=project.revision+1, master_blend=relative),
                        expected_revision=project.revision)
        with self.assertRaisesRegex(ProjectConflict, 'exact attached source, snapshot or saved master'):
            self.publish()
        self.assertFalse(self.output.exists())

    def test_rejects_different_current_registered_source_and_reserved_output(self):
        review = self.review()
        for key in ('source_sha256', 'snapshot_sha256'):
            wrong = replace(review, source=replace(review.source, **{key:'0'*64}))
            with self.subTest(key=key), patch('ucc.jobs.authored_idle_target_map.source_review', return_value=wrong):
                with self.assertRaisesRegex(ProjectConflict, 'exact attached source'):
                    self.publish(expected_review=wrong)
        for output in (self.source.store.root/'map', self.candidate.directory/'map', self.proof.parent/'map',
                       self.store.root/'map', Path(str(self.database)+'-journal')):
            with self.subTest(output=output), self.assertRaisesRegex(ValidationError, 'outside'):
                self.publish(destination=plan_destination(output, self.store.root))
            self.assertFalse(output.exists())

    def test_rechecks_target_at_commit_and_removes_owned_stage_on_failure(self):
        original_commit = IdlePublication.commit

        def change_project_before_commit(transaction, guard, budget):
            current = self.store.load()
            self.store.save(replace(current, revision=current.revision+1, name='Changed selection'),
                            expected_revision=current.revision)
            return original_commit(transaction, guard, budget)

        with patch.object(IdlePublication, 'commit', change_project_before_commit):
            with self.assertRaisesRegex(ProjectConflict, 'Saved character'):
                self.publish()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.ucc-export-*')))
