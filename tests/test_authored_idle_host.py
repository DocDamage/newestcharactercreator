"""Host boundary regressions with isolated invented worker evidence; ZERO native."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from fixtures.authored_idle_host import HostFixture, pin
from ucc.animations.authored_idle_mapping_math import check_same_rig_full_clock
from ucc.animations.native_profile import validate_native_profile
from ucc.core.authored_idle import CLEAR_IDLE_PROFILE, AuthoredIdleInspectionRequest, AuthoredIdleRequest
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from ucc.jobs.authored_idle import author_original_idle
from ucc.jobs.authored_idle_evidence import INSPECT, AUTHOR, VERIFY, QUALITY_EXECUTION
from ucc.jobs.authored_idle_io import private_bytes
from ucc.jobs.authored_idle_receipt import load_authored_idle_candidate, load_authored_idle_target_mapping
from ucc.jobs.authored_idle_sources import prepare_idle_context
from ucc.jobs.target_action_context import Budget


class AuthoredIdleHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.f = HostFixture(self.temp.name)

    def run_host(self, **changes):
        with patch('ucc.jobs.authored_idle.BlenderJobRunner') as runner:
            runner.return_value.run.side_effect = self.f.run
            return author_original_idle(self.f.store, **(self.f.args()|changes), timeout_s=120)

    def load(self, result, **changes):
        return load_authored_idle_candidate(self.f.store, directory=result.directory,
            expected_receipt_sha256=result.receipt_sha256, source_policy_records=self.f.records,
            database_path=self.f.database, blender_exe=self.f.blender, worker_script=self.f.worker,
            **changes)

    def load_mapping(self, result, **changes):
        arguments = dict(directory=result.directory, expected_receipt_sha256=result.receipt_sha256,
            source_policy_records=self.f.records, database_path=self.f.database,
            blender_exe=self.f.blender, worker_script=self.f.worker)
        return load_authored_idle_target_mapping(self.f.store, **(arguments | changes))

    def test_clear_profile_survives_three_worker_intents_and_cross_phase_relabel_rejects(self):
        inspected = replace(self.f.inspection, profile=CLEAR_IDLE_PROFILE)
        candidate = self.run_host(inspection_request=inspected)
        jobs = self.f.store.root/'.ucc-jobs'
        saved_inspection = candidate.directory/'idle_inspection_request.json'
        self.assertEqual(AuthoredIdleInspectionRequest.from_bytes(saved_inspection.read_bytes()), inspected)
        author = AuthoredIdleRequest.from_bytes((jobs/candidate.author_job_id/'idle_authoring_request.json').read_bytes())
        verification = AuthoredIdleRequest.from_bytes((jobs/candidate.verification_job_id/'idle_authoring_request.json').read_bytes())
        self.assertEqual(author.profile, CLEAR_IDLE_PROFILE)
        self.assertEqual(author, verification)
        self.assertEqual(self.load(candidate).request, author)
        self.assertEqual(self.load_mapping(candidate).candidate, candidate)

        # Rehash the substituted, valid V1 inspection through the delivered receipt.
        # The existing author and verifier still declare the clear recipe.
        payload = canonical_bytes(self.f.inspection.to_dict())
        saved_inspection.write_bytes(payload)
        receipt_file = candidate.directory/'authored_idle_receipt.json'
        receipt = json.loads(receipt_file.read_bytes())
        receipt['inspection_request_sha256'] = pin(payload)
        receipt['files'][saved_inspection.name] = {'bytes': len(payload), 'sha256': pin(payload)}
        raw = private_bytes(receipt)
        receipt_file.write_bytes(raw)
        with self.assertRaisesRegex(ValidationError, 'recipe profile differs'):
            self.load(replace(candidate, receipt_sha256=pin(raw)))

    def test_target_mapping_binds_current_candidate_without_writing(self):
        result = self.run_host()
        before = {path: pin(path.read_bytes()) for path in self.f.root.rglob('*') if path.is_file()}
        mapping = self.load_mapping(result)
        after = {path: pin(path.read_bytes()) for path in self.f.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(mapping.candidate, result)
        self.assertEqual(mapping.mapping_sha256, pin(mapping.mapping_json))
        profile = json.loads(mapping.mapping_json)
        self.assertEqual(mapping.mapping_json, canonical_bytes(profile))
        self.assertEqual(validate_native_profile(profile, result.source_sha256,
            result.snapshot_sha256, result.target.master_sha256), profile)
        self.assertEqual(len(profile['pairs']), 51)
        self.assertEqual([j.operation for j in self.f.calls], [INSPECT, AUTHOR, VERIFY])

    def test_target_mapping_rejects_changed_verifier_before_mapping(self):
        result = self.run_host()
        path = self.f.store.root/'.ucc-jobs'/result.verification_job_id/'request.json'
        path.write_bytes(path.read_bytes() + b' ')
        with patch('ucc.jobs.authored_idle_receipt.build_original_idle_profile') as mapper:
            with self.assertRaises(ValidationError):
                self.load_mapping(result)
            mapper.assert_not_called()

    def test_target_mapping_rechecks_current_policy_after_build(self):
        result = self.run_host()
        original = self.f.policy.read_bytes()

        def change_policy_after_admission(*args, **kwargs):
            self.f.policy.write_bytes(original + b' ')
            return {}

        with patch('ucc.jobs.authored_idle_receipt.build_original_idle_profile',
                side_effect=change_policy_after_admission):
            with self.assertRaisesRegex(ProjectStorageError, 'source, review, catalog or runtime bytes changed'):
                self.load_mapping(result)

    def test_target_mapping_rechecks_verifier_pin_after_build(self):
        result = self.run_host()
        path = self.f.store.root/'.ucc-jobs'/result.verification_job_id/'result.json'

        def change_verifier_after_admission(*args, **kwargs):
            path.write_bytes(path.read_bytes() + b' ')
            return {}

        with patch('ucc.jobs.authored_idle_receipt.build_original_idle_profile',
                side_effect=change_verifier_after_admission):
            with self.assertRaisesRegex(ValidationError, 'actual request/result bytes changed'):
                self.load_mapping(result)

    def test_target_mapping_observes_cancellation_during_full_clock_check(self):
        result = self.run_host()
        cancel = Event()

        def cancel_as_clock_check_begins(*args, **kwargs):
            cancel.set()
            return check_same_rig_full_clock(*args, **kwargs)

        with patch('ucc.animations.authored_idle_mapping.check_same_rig_full_clock',
                side_effect=cancel_as_clock_check_begins):
            with self.assertRaisesRegex(ProjectStorageError, 'cancelled by caller'):
                self.load_mapping(result, cancel=cancel)

    def test_three_phase_closed_delivery_preserves_sources_and_legacy_snapshot(self):
        project_before = self.f.store.file.read_bytes(); master_before = self.f.master.read_bytes()
        catalog_before = self.f.database.read_bytes()
        result = self.run_host(); admitted = self.load(result)
        self.assertEqual([j.operation for j in self.f.calls], [INSPECT, AUTHOR, VERIFY])
        self.assertEqual(len({j.job_id for j in self.f.calls}), 3)
        self.assertNotEqual(admitted.request.job_id, self.f.inspection.job_id)
        self.assertEqual(admitted.request.target, result.target)
        self.assertEqual(admitted.request.project_snapshot_json, self.f.inspection.project_snapshot_json)
        self.assertEqual(json.loads(admitted.request.project_snapshot_json)['animations'], list(self.f.project.animations))
        self.assertEqual(self.f.store.file.read_bytes(), project_before)
        self.assertEqual(self.f.master.read_bytes(), master_before); self.assertEqual(self.f.database.read_bytes(), catalog_before)
        self.assertTrue(result.review_path.is_relative_to(self.f.store.root/'.ucc-jobs'))
        self.assertFalse((result.directory/'authored_idle_review.blend').exists())
        receipt = json.loads(admitted.receipt_json)
        self.assertFalse(receipt['registered_in_catalog']); self.assertFalse(receipt['usable_action_approved'])
        self.assertFalse(receipt['sprite_use_authorized']); self.assertEqual(receipt['required_quality_execution'], QUALITY_EXECUTION)
        self.assertEqual(pin(admitted.source_snapshot_json), result.snapshot_sha256)
        self.assertNotEqual(admitted.source_snapshot_json, private_bytes(json.loads(admitted.source_snapshot_json)))
        for job in self.f.calls:
            folder = self.f.store.root/'.ucc-jobs'/job.job_id
            self.assertFalse((folder/'NEVER_CONSUME.motion').exists())

    def test_missing_policy_stops_before_native_boundary(self):
        with self.assertRaises(ValidationError): self.run_host(source_policy_records=())
        self.assertEqual(self.f.calls, [])

    def test_changed_policy_or_unmatched_per_use_record_stops_before_worker(self):
        self.f.policy.write_bytes(self.f.policy.read_bytes()+b' ')
        with self.assertRaises(ProjectConflict): self.run_host()
        self.assertEqual(self.f.calls, [])

    def test_inspector_wrong_target_and_unknown_summary_cannot_author(self):
        def mutate(job, folder, summary): summary['extra_claim'] = True
        self.f.mutate = mutate
        with self.assertRaises(ValidationError): self.run_host()
        self.assertEqual(len(self.f.calls), 1); self.assertFalse(self.f.destination.path.exists())

    def test_inspector_different_saved_target_cannot_author(self):
        def mutate(job, folder, summary): summary['target']['project_sha256'] = 'f'*64
        self.f.mutate = mutate
        with self.assertRaises(ValidationError): self.run_host()
        self.assertEqual(len(self.f.calls), 1)

    def test_actual_raw_job_request_boolean_protocol_is_not_equal_to_version_one(self):
        def after(job, folder):
            value = json.loads((folder/'request.json').read_bytes()); value['protocol_version'] = True
            (folder/'request.json').write_text(json.dumps(value), encoding='utf-8')
        self.f.after = after
        with self.assertRaisesRegex(ValidationError,'request/result'): self.run_host()
        self.assertEqual(len(self.f.calls), 1)

    def test_verified_partial_snapshot_with_rehashed_manifest_is_rejected(self):
        def mutate(job, folder, summary):
            if job.operation != VERIFY: return
            path = folder/'authored_idle_source_snapshot.json'; data = json.loads(path.read_bytes())
            data['frames'].pop(); path.write_bytes(private_bytes(data))
            summary['outputs'][0] = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': pin(path.read_bytes())}
            path = folder/'authored_idle_verification.json'; data = json.loads(path.read_bytes())
            data['actual_fbx_source']['source_snapshot'] = summary['outputs'][0]; path.write_bytes(private_bytes(data))
            summary['outputs'][1] = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': pin(path.read_bytes())}
        self.f.mutate = mutate
        with self.assertRaises(ValidationError): self.run_host()
        self.assertEqual(len(self.f.calls), 3); self.assertFalse(self.f.destination.path.exists())

    def test_saved_project_change_after_author_is_preserved_and_stops_verifier(self):
        revised = []
        def after(job, folder):
            if job.operation == AUTHOR:
                current = self.f.store.load()
                revised.append(self.f.store.save(replace(current, name='USER_EDIT_PRESERVED', revision=current.revision+1), expected_revision=current.revision))
        self.f.after = after
        with self.assertRaises(ProjectConflict): self.run_host()
        self.assertEqual([j.operation for j in self.f.calls], [INSPECT, AUTHOR])
        self.assertEqual(self.f.store.load(), revised[0]); self.assertFalse(self.f.destination.path.exists())

    def test_cancel_after_author_stops_verifier_and_records_failure(self):
        cancel = Event()
        self.f.after = lambda job, folder: cancel.set() if job.operation == AUTHOR else None
        with self.assertRaisesRegex(ProjectStorageError, 'cancelled'): self.run_host(cancel=cancel)
        self.assertEqual(len(self.f.calls), 2); self.assertFalse(self.f.destination.path.exists())
        self.assertEqual(len(list((self.f.store.root/'.ucc-jobs').glob('authored-idle-*/job_status-FAILED.json'))), 1)

    def test_completed_author_file_tamper_stops_verification_admission(self):
        def after(job, folder):
            if job.operation == VERIFY:
                author = self.f.store.root/'.ucc-jobs'/self.f.calls[1].job_id
                (author/'original_idle.fbx').write_bytes(b'FOREIGN_CHANGED_SOURCE')
        self.f.after = after
        with self.assertRaises(ValidationError): self.run_host()
        self.assertFalse(self.f.destination.path.exists())

    def test_declaring_completed_quality_with_integer_flags_rejected(self):
        result = self.run_host(); path = result.directory/'authored_idle_receipt.json'
        value = json.loads(path.read_bytes()); value['required_quality_execution']['root_neutral_measured'] = 1
        path.write_bytes(private_bytes(value)); result = replace(result, receipt_sha256=pin(path.read_bytes()))
        with self.assertRaisesRegex(ValidationError, 'scope'): self.load(result)

    def test_catalog_sidecar_added_during_worker_is_preserved_and_rejected(self):
        sidecar = Path(str(self.f.database)+'-wal')
        self.f.after = lambda job, folder: sidecar.write_bytes(b'EXTERNAL_WAL_WRITER')
        with self.assertRaises(ProjectStorageError): self.run_host()
        self.assertEqual(sidecar.read_bytes(), b'EXTERNAL_WAL_WRITER'); self.assertEqual(len(self.f.calls), 1)

    def test_hardlink_added_after_admission_invalidates_selected_input(self):
        context = prepare_idle_context(self.f.store, self.f.inspection, self.f.records, self.f.database,
            self.f.blender, self.f.worker, self.f.destination, Budget(None,120))
        alias = self.f.root/'catalog-alias.db'; alias.hardlink_to(self.f.database)
        with self.assertRaises(ProjectStorageError): context.guard()

    def test_policy_race_between_review_and_snapshot_is_not_adopted(self):
        from ucc.jobs.authored_idle_sources import admit_policies
        def race(*args):
            admitted = admit_policies(*args); self.f.policy.write_bytes(b'REVOKED'); return admitted
        with patch('ucc.jobs.authored_idle_sources.admit_policies', side_effect=race):
            with self.assertRaises(ProjectConflict): self.run_host()
        self.assertEqual(self.f.calls, [])

    def test_master_race_between_review_and_snapshot_is_not_adopted(self):
        from ucc.jobs.authored_idle_sources import admit_policies
        def race(*args):
            admitted = admit_policies(*args); self.f.master.write_bytes(b'BLENDER_FOREIGN_CHANGED_MASTER'); return admitted
        with patch('ucc.jobs.authored_idle_sources.admit_policies', side_effect=race):
            with self.assertRaises(ProjectConflict): self.run_host()
        self.assertEqual(self.f.calls, [])

    def test_rehashed_policy_with_revoked_authoring_is_not_permission(self):
        policy = json.loads(self.f.policy.read_bytes()); policy['authoring_and_derived_rig_allowed'] = False
        self.f.policy.write_bytes(private_bytes(policy))
        record = replace(self.f.records[0],sha256=pin(self.f.policy.read_bytes()))
        request = replace(self.f.inspection,permissions=(replace(self.f.inspection.permissions[0],source_policy_sha256=record.sha256),))
        with self.assertRaises(ProjectConflict): self.run_host(source_policy_records=(record,),inspection_request=request)
        self.assertEqual(self.f.calls, [])

    def test_exclusive_destination_race_preserves_foreign_folder(self):
        def after(job, folder):
            if job.operation == VERIFY:
                self.f.destination.path.mkdir(); (self.f.destination.path/'foreign.txt').write_bytes(b'USER')
        self.f.after = after
        with self.assertRaises(ProjectStorageError): self.run_host()
        self.assertEqual((self.f.destination.path/'foreign.txt').read_bytes(), b'USER')

    def test_postpublication_failure_withdraws_owned_delivery(self):
        with patch('ucc.jobs.authored_idle.load_authored_idle_candidate', side_effect=ProjectStorageError('late failure')):
            with self.assertRaisesRegex(ProjectStorageError, 'late failure'): self.run_host()
        self.assertFalse(self.f.destination.path.exists())
        self.assertEqual(len(list(self.f.destination.path.parent.glob('.ucc-export-*'))), 1)

    def test_replaced_owned_workdir_rejected_before_next_write_or_worker(self):
        def after(job, folder):
            if job.operation == INSPECT:
                work = self.f.store.root/'.ucc-jobs'/('authored-idle-'+self.f.inspection.job_id)
                work.rename(work.with_name('retained-original')); work.mkdir()
        self.f.after = after
        with self.assertRaises(ValidationError): self.run_host()
        self.assertEqual(len(self.f.calls), 1)
        work = self.f.store.root/'.ucc-jobs'/('authored-idle-'+self.f.inspection.job_id)
        self.assertEqual(list(work.iterdir()), [])


if __name__ == '__main__': unittest.main()
