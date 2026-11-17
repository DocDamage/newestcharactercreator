"""Nonshipping synthetic clock/SQLite tests; not FBX or engine evidence."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fixtures.fbx_snapshot_contract import snapshot, report
from ucc.animations.catalog import AnimationCatalog
from ucc.animations.catalog_clip import VerifiedCatalogClip, MAX_RECEIPT_BYTES
from ucc.animations.metadata import AnimationMetadataError
from ucc.animations.source_clip_clock import SourceClipClock
from ucc.library.provenance import LicensePolicy


class SourceClipClockTests(unittest.TestCase):
    def test_source1_300_separates_endpoint_span_from_sample_coverage(self):
        clock = SourceClipClock(1, 300, 300, 30.)
        self.assertEqual(clock.sample_span_s, 299/30)
        self.assertEqual(clock.nominal_coverage_s, 10.)
        self.assertEqual((clock.source_frame_at_index(0), clock.source_frame_at_index(299)), (1, 300))
        self.assertEqual(clock.to_dict()['evidence_scope'], 'STORED_MEASURED_SOURCE_METADATA_ONLY')

    def test_shorter_and_nonzero_origin_clocks_are_not_coerced(self):
        for first, count in ((1,180), (1,210), (2,300), (-10,12)):
            with self.subTest(first=first, count=count):
                clock = SourceClipClock(first, first+count-1, count, 30)
                self.assertEqual(clock.source_frame_at_index(count-1), first+count-1)
                self.assertEqual(clock.sample_span_s, (count-1)/30)
                self.assertEqual(clock.nominal_coverage_s, count/30)

    def test_strict_clock_types_bounds_and_coherence(self):
        invalid = ((True,300,300,30), (1,True,300,30), (1,300,True,30),
                   (1,300,300,True), (1,300,300,'30'), (1,300,299,30),
                   (1,1,1,30), (1,2401,2401,30), (-100001,-99702,300,30),
                   (99702,100001,300,30), (1,300,300,0), (1,300,300,241),
                   (1,300,300,10**1000), (1,300,300,float('nan')), (1,300,300,float('inf')),
                   (1.,300,300,30), (1,300.,300,30), (1,300,300.,30))
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(AnimationMetadataError):
                SourceClipClock(*args)

    def test_index_validation_never_clamps_or_accepts_boolean(self):
        clock = SourceClipClock(1,300,300,30.)
        for index in (-1,300,True,1.,'1',None):
            with self.subTest(index=index), self.assertRaises(AnimationMetadataError):
                clock.source_frame_at_index(index)

    def test_immutable_and_independent_serialized_readout(self):
        clock = SourceClipClock(1,300,300,30.)
        with self.assertRaises(FrozenInstanceError): clock.fps = 60
        value = clock.to_dict(); value['source_first_frame'] = 2
        self.assertEqual(clock.source_first_frame,1)


class StoredSourceClockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.database = self.root/'owned.sqlite3'
        self.source = self.root/'synthetic-not-real.fbx'; self.source.write_bytes(b'NONSHIPPING_SYNTHETIC_NOT_FBX')
        self.policy = LicensePolicy('Original test', 'Original nonshipping synthetic',
            'original-test://source-clock', reviewed=True, local_preview_allowed=True, no_ai=True)
        self.data = snapshot(); self.data['source_sha256'] = sha256(self.source.read_bytes()).hexdigest()
        originals = self.data['frames']
        self.data['frames'] = [{**deepcopy(originals[i%4]), 'frame':i+1} for i in range(300)]
        self.data['first_frame'], self.data['last_frame'] = 1,300
        payload = json.dumps(self.data).encode()
        self.report = report(self.data,payload)|{'first_frame':1,'last_frame':300,'frame_count':300,
            'two_workers_agree':True,'source_bytes_unchanged':True,'policy':self.policy.to_dict()}
        with AnimationCatalog(self.database) as catalog:
            catalog.index_file('synthetic', self.source,self.policy)
            catalog.record_fbx_intake('synthetic',self.data,self.report,
                                     expected_entry=catalog.library.get('synthetic'))
            self.indexed = catalog.get('synthetic')
            self.raw = catalog.db.execute('SELECT receipt_json FROM animation_fbx_intakes').fetchone()[0]
            self.stored_clip = catalog.db.execute('SELECT metadata_json FROM animation_clips').fetchone()[0]

    def load(self):
        with AnimationCatalog(self.database,read_only=True) as catalog:
            return catalog.source_clock('synthetic')

    def update(self,sql,args=()):
        with AnimationCatalog(self.database) as catalog:
            catalog.db.execute(sql,args); catalog.db.commit()

    def test_stored_readonly_reopen_exact_clock_and_unchanged_bytes(self):
        before = self.database.read_bytes()
        with patch('ucc.jobs.fbx_intake.inspect_selected_fbx',side_effect=AssertionError('No worker')):
            clock = self.load()
        self.assertEqual(clock,SourceClipClock(1,300,300,30.))
        self.assertEqual(self.database.read_bytes(),before)
        self.assertEqual(self.indexed.to_dict()['clips'][0]['duration_seconds'],299/30)
        self.assertNotIn('source_clock',self.indexed.to_dict())

    def test_verified_reference_uses_its_own_source_clock(self):
        receipt = json.loads(self.raw)
        reference = VerifiedCatalogClip('synthetic#clip-0000','synthetic',self.data['source_sha256'],
            self.policy,receipt['snapshot_sha256'],sha256(self.raw.encode()).hexdigest(),
            receipt['skeleton_fingerprint'],1,300,self.indexed.clips[0])
        self.assertEqual(reference.source_clock,SourceClipClock(1,300,300,30.))
        self.assertFalse(reference.target_preview_verified)
        with self.assertRaises(AnimationMetadataError): replace(reference,last_frame=301).source_clock

    def test_metadata_only_read_does_not_revalidate_deleted_source_bytes(self):
        self.source.unlink()
        self.assertEqual(self.load().source_first_frame,1)
        self.assertEqual(self.load().to_dict()['evidence_scope'],'STORED_MEASURED_SOURCE_METADATA_ONLY')

    def test_missing_and_truly_unmeasured_sources_return_none(self):
        with AnimationCatalog(self.database) as catalog:
            self.assertIsNone(catalog.source_clock('missing'))
            catalog.index_file('unmeasured',self.source,self.policy)
            self.assertIsNone(catalog.source_clock('unmeasured'))

    def test_measured_missing_receipt_rejects(self):
        self.update('DELETE FROM animation_fbx_intakes')
        with self.assertRaisesRegex(AnimationMetadataError,'no source clock receipt'):self.load()

    def test_receipt_clock_cannot_be_coherently_shifted_without_current_clip(self):
        value = json.loads(self.raw); value['observation']['first_frame']=2
        value['observation']['last_frame']=301; value['clip']['duration_seconds']=10.
        self.update('UPDATE animation_fbx_intakes SET receipt_json=?',(json.dumps(value),))
        with self.assertRaises(AnimationMetadataError):self.load()

    def test_malformed_receipt_and_metadata_raise_structured_errors(self):
        cases = [('UPDATE animation_fbx_intakes SET receipt_json=?',('{',)),
                 ('UPDATE animation_clips SET metadata_json=?',('{',)),
                 ('UPDATE animation_sources SET bone_names_json=?',('{',)),
                 ('UPDATE animation_sources SET warnings_json=?',('{',))]
        for sql,args in cases:
            with self.subTest(sql=sql):
                # Restore all metadata so each fault is independent.
                self.update('UPDATE animation_fbx_intakes SET receipt_json=?',(self.raw,))
                self.update('UPDATE animation_clips SET metadata_json=?',(self.stored_clip,))
                self.update('UPDATE animation_sources SET bone_names_json=?,warnings_json=?',
                            (json.dumps(self.indexed.bone_names),json.dumps(self.indexed.warnings)))
                self.update(sql,args)
                with self.assertRaises(AnimationMetadataError):self.load()

    def test_nontext_and_oversized_fields_reject_before_get(self):
        faults = [('animation_fbx_intakes','receipt_json',b'{}'),
                  ('animation_fbx_intakes','receipt_json',' '*(MAX_RECEIPT_BYTES+1)),
                  ('animation_clips','metadata_json',b'{}'),
                  ('animation_clips','metadata_json',' '*(MAX_RECEIPT_BYTES+1)),
                  ('animation_sources','bone_names_json',b'[]'),
                  ('animation_sources','format',b'fbx'),
                  ('animation_sources','format','x'*33),
                  ('animation_sources','warnings_json',' '*(MAX_RECEIPT_BYTES+1)),
                  ('asset_sources','license_json',' '*(128*1024+1)),
                  ('asset_sources','source_path',b'local')]
        for table,column,value in faults:
            with self.subTest(table=table,column=column):
                with AnimationCatalog(self.database) as catalog:
                    old = catalog.db.execute(f'SELECT {column} FROM {table}').fetchone()[0]
                    catalog.db.execute(f'UPDATE {table} SET {column}=?',(value,));catalog.db.commit()
                    with patch.object(catalog,'get',side_effect=AssertionError('Preflight must run first')):
                        with self.assertRaises(AnimationMetadataError):catalog.source_clock('synthetic')
                    catalog.db.execute(f'UPDATE {table} SET {column}=?',(old,));catalog.db.commit()

    def test_current_receipt_source_hash_tamper_rejects(self):
        value = json.loads(self.raw);value['source_sha256']='b'*64
        self.update('UPDATE animation_fbx_intakes SET receipt_json=?',(json.dumps(value),))
        with self.assertRaises(AnimationMetadataError):self.load()


if __name__=='__main__':unittest.main()
