"""Synthetic SQLite/byte boundaries; mocked native calls are not engine proof."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from threading import Event
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.core.errors import UCCError
from ucc.jobs.native_body import NativeBodyPreview, preview_native_body
from ucc.jobs.native_playback import NativePlayback, prepare_native_playback
from ucc.jobs.native_source_authority import bind_native_catalog_source, NativeProofCapture
from ucc.jobs.target_action_context import operation_budget
from ucc.library.provenance import LicensePolicy


class NativeSourceAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root/'synthetic.fbx'; self.source.write_bytes(b'NONSHIPPING_NOT_AN_FBX')
        self.source_sha = sha256(self.source.read_bytes()).hexdigest()
        self.database = self.root/'catalog.sqlite3'
        self.policy = LicensePolicy('Original synthetic', 'Original test only', 'test://native-authority',
                                    reviewed=True, no_ai=True, local_preview_allowed=True)
        self.data = snapshot(); self.data['source_sha256'] = self.source_sha
        payload = json.dumps(self.data).encode()
        self.report = report(self.data, payload) | {'two_workers_agree':True,
            'source_bytes_unchanged':True, 'policy':self.policy.to_dict()}
        with AnimationCatalog(self.database) as catalog:
            catalog.index_file('source', self.source, self.policy)
            catalog.record_fbx_intake('source',self.data,self.report,
                                     expected_entry=catalog.library.get('source'))
        self.project = self.root/'owned-project'; self.project.mkdir()
        self.metadata = self.project/'project.ucc.json'; self.metadata.write_bytes(b'SYNTHETIC_PROJECT')
        master_bytes=b'SYNTHETIC_NOT_BLEND'
        self.master = self.project/'master/versions'/(sha256(master_bytes).hexdigest()+'.blend')
        self.master.parent.mkdir(parents=True);self.master.write_bytes(master_bytes)
        self.store = SimpleNamespace(root=self.project)

    def bind(self, **overrides):
        options = dict(expected_source_sha256=self.source_sha, expected_policy=self.policy,
                       local_preview_confirmed=True, timeout_s=5)
        return bind_native_catalog_source(self.database,'source#clip-0000',**(options|overrides))

    def revoke(self):
        with AnimationCatalog(self.database) as catalog:
            policy = json.loads(catalog.db.execute('SELECT license_json FROM asset_sources').fetchone()[0])
            policy['local_preview_allowed'] = False
            catalog.db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(policy),))
            catalog.db.commit()

    def body(self, authority):
        return NativeBodyPreview('synthetic-project',1,sha256(self.master.read_bytes()).hexdigest(),
            self.source_sha,{},'synthetic-review.blend','','synthetic-timeline.json',('unit-a','unit-b'),
            source_authority=authority)

    def proof(self):
        with operation_budget(None,5) as budget:
            capture = NativeProofCapture(budget)
            for path in (self.metadata,self.master,self.source):
                capture.before(path);capture.admit(path,sha256(path.read_bytes()).hexdigest())
            return capture.seal()

    def body_options(self, authority):
        return dict(source_fbx=self.source,blender_exe=self.root/'unused.exe',worker_script=self.root/'unused.py',
            permission=self.policy,expected_project_id='synthetic-project',expected_revision=1,
            expected_master_blend=self.master.relative_to(self.project).as_posix(),source_authority=authority,timeout_s=5)

    def playback_options(self):
        return dict(source_fbx=self.source,permission=self.policy,blender_exe=self.root/'unused.exe',
                    worker_script=self.root/'unused.py',timeout_s=5)

    def test_real_stored_binder_preserves_exact_generic_clock_and_immutable_watchset(self):
        authority = self.bind()
        self.assertEqual((authority.clock.source_first_frame,authority.clock.source_last_frame),(1,4))
        self.assertEqual(authority.policy,self.policy)
        self.assertTrue(authority.guard(timeout_s=5))
        self.assertTrue(authority.identities_current())
        for suffix in ('-wal','-journal','-shm'):
            self.assertIn(Path(str(self.database)+suffix),authority.watched_identities)
        self.assertTrue(set(authority.watch_paths).issubset(authority.watched_identities))
        with self.assertRaises(TypeError):authority.watched_identities[self.source]=(0,0,0,0)

    def test_consent_policy_hash_and_cancellation_reject_before_authority(self):
        event=Event();event.set()
        for change in ({'local_preview_confirmed':False},{'expected_source_sha256':'b'*64},
                       {'expected_policy':replace(self.policy,no_ai=False)},
                       {'expected_policy':replace(self.policy,local_preview_allowed=False)}, {'cancel':event}):
            with self.subTest(change=change),self.assertRaises(UCCError):self.bind(**change)

    def test_healthy_repeated_read_only_guards_do_not_adopt_new_policy_baselines(self):
        authority=self.bind();original=dict(authority.watched_identities)
        for _ in range(3):self.assertTrue(authority.guard(timeout_s=5))
        self.assertEqual(dict(authority.watched_identities),original)
        self.assertTrue(authority.identities_current())
        self.revoke()
        with self.assertRaises(UCCError):authority.guard(timeout_s=5)

    def test_existing_nonempty_wal_is_bound_and_held_commit_revocation_rejects(self):
        writer=sqlite3.connect(self.database);self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("UPDATE asset_sources SET indexed_utc='synthetic-metadata'");writer.commit()
        authority=self.bind()
        self.assertTrue(authority.guard(timeout_s=5));self.assertTrue(authority.identities_current())
        old=dict(authority.watched_identities)
        policy=json.loads(writer.execute('SELECT license_json FROM asset_sources').fetchone()[0])
        policy['local_preview_allowed']=False
        writer.execute('UPDATE asset_sources SET license_json=?',(json.dumps(policy),));writer.commit()
        with self.assertRaises(UCCError):authority.guard(timeout_s=5)
        self.assertEqual(dict(authority.watched_identities),old)

    def test_shm_mtime_only_is_normalized_but_replacement_or_size_is_not(self):
        shm=Path(str(self.database)+'-shm');shm.write_bytes(b'UNIT_COORDINATION')
        authority=self.bind();stamp=shm.stat()
        os.utime(shm,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000))
        self.assertTrue(authority.identities_current())
        shm.write_bytes(b'DIFFERENT_SIZE_COORDINATION')
        self.assertFalse(authority.identities_current())

    def test_empty_wal_absence_transition_allowed_but_nonempty_rejects(self):
        authority=self.bind();wal=Path(str(self.database)+'-wal')
        wal.write_bytes(b'');self.assertTrue(authority.identities_current())
        wal.unlink();self.assertTrue(authority.identities_current())
        wal.write_bytes(b'NONEMPTY');self.assertFalse(authority.identities_current())

    def test_wal_directory_cannot_alias_the_missing_empty_sentinel(self):
        authority=self.bind();wal=Path(str(self.database)+'-wal')
        if wal.exists():wal.unlink()
        wal.mkdir()
        self.assertFalse(authority.identities_current())
        with self.assertRaises(UCCError):authority.guard(timeout_s=5)

    def test_coordination_junction_metadata_fails_closed(self):
        # Synthetic junction flag, no OS link/privilege requirement or skip.
        authority=self.bind();shm=Path(str(self.database)+'-shm')
        with patch.object(Path,'is_junction',lambda path:path==shm):
            self.assertFalse(authority.identities_current())

    def test_shm_replacement_and_hardlink_fail_cheap_namespace_guard(self):
        shm=Path(str(self.database)+'-shm');shm.write_bytes(b'UNIT_COORDINATION')
        authority=self.bind();other=self.root/'other-coordination';other.write_bytes(shm.read_bytes())
        os.replace(other,shm)
        self.assertFalse(authority.identities_current())
        shm.unlink();shm.write_bytes(b'UNIT_COORDINATION')
        authority=self.bind();alias=self.root/'hardlink'
        os.link(shm,alias)
        self.assertFalse(authority.identities_current())

    def test_semantic_revocation_during_final_source_read_is_not_adopted(self):
        from ucc.jobs import native_source_authority as module
        original=module.capture
        def changed(*args,**kwargs):
            value=original(*args,**kwargs)
            self.revoke()
            return value
        with patch.object(module,'capture',side_effect=changed):
            with self.assertRaises(UCCError):self.bind()

    def test_source_same_size_restored_mtime_content_change_rejects_heavy_guard(self):
        authority=self.bind();stamp=self.source.stat()
        self.source.write_bytes(b'X'*stamp.st_size);os.utime(self.source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        with self.assertRaises(UCCError):authority.guard(timeout_s=5)

    def test_fresh_snapshot_hash_and_clock_must_match_registered_receipt(self):
        authority=self.bind();authority.require_snapshot(self.data,self.report['snapshot']['sha256'])
        for data,checksum in ((self.data,'b'*64),(self.data|{'first_frame':2,'last_frame':5},authority.snapshot_sha256)):
            with self.assertRaises(UCCError):authority.require_snapshot(data,checksum)

    def test_source_or_policy_substitution_is_rejected(self):
        authority=self.bind()
        for path,policy in ((self.root/'other.fbx',self.policy),(self.source,replace(self.policy,no_ai=False))):
            with self.assertRaises(UCCError):authority.require_source(path,policy)

    def test_proof_capture_rejects_pre_read_same_bytes_inode_replacement(self):
        with operation_budget(None,5) as budget:
            capture=NativeProofCapture(budget);capture.before(self.master)
            other=self.root/'replacement';other.write_bytes(self.master.read_bytes());os.replace(other,self.master)
            with self.assertRaises(UCCError):capture.admit(self.master,sha256(self.master.read_bytes()).hexdigest())

    def test_inherited_proof_preserves_original_watch_identities_and_fresh_guard(self):
        original=self.proof()
        with operation_budget(None,5) as budget:
            capture=NativeProofCapture(budget,previous=original)
            extra=self.root/'synthetic-cache.bin';extra.write_bytes(b'SYNTHETIC_CACHE')
            capture.before(extra);capture.admit(extra,sha256(extra.read_bytes()).hexdigest());extended=capture.seal()
        self.assertTrue(extended.guard(timeout_s=5))
        self.assertEqual({p:extended.watched_identities[p] for p in original.watched_identities},dict(original.watched_identities))
        extra.write_bytes(b'CORRUPTED')
        with self.assertRaises(UCCError):extended.guard(timeout_s=5)

    def test_registered_body_inherits_stage_guard_and_returns_original_proof(self):
        authority=self.bind();calls=[]
        def native(_store,**options):
            for _ in range(5):options['source_guard']();calls.append(1)
            return self.body(None)
        with patch('ucc.jobs.native_body._preview_native_body',side_effect=native):
            result=preview_native_body(self.store,**self.body_options(authority))
        self.assertEqual(len(calls),5);self.assertIs(result.source_authority,authority)
        self.assertTrue(result.proof_receipt.guard(timeout_s=5))

    def test_untrusted_master_path_rejects_before_any_proof_capture_or_worker(self):
        authority=self.bind()
        for value in (str(self.root/'outside.blend'),'../outside.blend','master.blend',True,None):
            with self.subTest(value=value), patch('ucc.jobs.native_body.NativeProofCapture') as capture, \
                    patch('ucc.jobs.native_body._preview_native_body') as worker:
                with self.assertRaises(UCCError):
                    preview_native_body(self.store,**(self.body_options(authority)|{'expected_master_blend':value}))
                capture.assert_not_called();worker.assert_not_called()

    def test_body_final_policy_drift_or_late_cancel_produces_no_admission(self):
        for fault in ('policy','cancel'):
            # Fresh catalog/authority per independent fault.
            if fault=='cancel':
                with AnimationCatalog(self.database) as c:
                    c.db.execute('UPDATE asset_sources SET license_json=?',(json.dumps(self.policy.to_dict()),));c.db.commit()
            authority=self.bind();event=Event()
            def native(_store,**_):
                if fault=='policy':self.revoke()
                else:event.set()
                return self.body(None)
            with patch('ucc.jobs.native_body._preview_native_body',side_effect=native):
                with self.assertRaises(UCCError):preview_native_body(self.store,**(self.body_options(authority)|{'cancel':event}))

    def test_playback_auto_inherits_authority_proof_and_checks_before_return(self):
        authority=self.bind();preview=replace(self.body(authority),proof_receipt=self.proof());calls=[]
        def cache(_store,_preview,**options):
            for _ in range(2):options['source_guard']();calls.append(1)
            return NativePlayback('synthetic-project',1,preview.master_sha256,self.source_sha,None,'unit-cache','synthetic.json')
        with patch('ucc.jobs.native_playback._prepare_native_playback',side_effect=cache):
            result=prepare_native_playback(self.store,preview,**self.playback_options())
        self.assertEqual(len(calls),2);self.assertIs(result.source_authority,authority)
        self.assertTrue(result.proof_receipt.identities_current())

    def test_playback_missing_body_proof_and_wrong_policy_never_call_cache(self):
        authority=self.bind();preview=self.body(authority)
        with patch('ucc.jobs.native_playback._prepare_native_playback') as cache:
            with self.assertRaises(UCCError):prepare_native_playback(self.store,preview,**self.playback_options())
            preview=replace(preview,proof_receipt=self.proof())
            with self.assertRaises(UCCError):prepare_native_playback(self.store,preview,**(self.playback_options()|{'permission':replace(self.policy,no_ai=False)}))
            cache.assert_not_called()

    def test_stripped_authority_cannot_prepare_adjusted_playback(self):
        preview = self.body(self.bind())
        folder = self.project/'.ucc-jobs'/'synthetic-body'
        folder.mkdir(parents=True)
        path = self.master.relative_to(self.project).as_posix()
        self.store.load = lambda: SimpleNamespace(master_blend=path, project_id=preview.project_id, revision=1)
        bindings = {'source_sha256':self.source_sha,'master_sha256':preview.master_sha256,
                    'snapshot_sha256':'a'*64,'mapping_sha256':'b'*64}
        preview = replace(preview,source_authority=None,
                          private_timeline=str(folder/'target_timeline.json'),
                          worker_report={'bindings':bindings,'timeline':{},'visual_review_blend':{}})
        module = 'ucc.jobs.native_playback'
        for adjustment in ('wrist_transitions','forearm_roll','planted_knee'):
            profile = {'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1',adjustment:{}}
            with (self.subTest(adjustment=adjustment),
                  patch(module+'._master_file',return_value=(self.master,preview.master_sha256)),
                  patch(module+'.bound_file'),
                  patch(module+'.read_native_profile',return_value=(profile,bindings['mapping_sha256'])),
                  patch(module+'.BlenderJobRunner') as runner):
                with self.assertRaisesRegex(UCCError,'requires its authenticated catalog source'):
                    prepare_native_playback(self.store,preview,**self.playback_options())
                runner.assert_not_called()


    def test_manual_none_route_does_not_add_guards_or_require_catalog(self):
        sentinel=object()
        with patch('ucc.jobs.native_body._preview_native_body',return_value=sentinel) as body:
            self.assertIs(preview_native_body(self.store,**self.body_options(None)),sentinel)
            self.assertIsNone(body.call_args.kwargs['source_guard'])
        with patch('ucc.jobs.native_playback._prepare_native_playback',return_value=sentinel) as cache:
            self.assertIs(prepare_native_playback(self.store,self.body(None),**self.playback_options()),sentinel)
            self.assertIsNone(cache.call_args.kwargs['source_guard'])


if __name__ == '__main__':unittest.main()
