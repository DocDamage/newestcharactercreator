"""Pure analytical/nonshipping skeleton segments; no engine or private data."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json
import struct
import unittest
from unittest.mock import patch

from fixtures.source_skeleton_contract import analytical_source_snapshot
from ucc.animations.source_skeleton import build_source_skeleton_cache
from ucc.core.errors import ValidationError


class CancelledForTest(Exception):
    pass


class SourceSkeletonTests(unittest.TestCase):
    def build(self, data=None, *, raw=None, **kwargs):
        data = analytical_source_snapshot() if data is None else data
        raw = json.dumps(data).encode() if raw is None else raw
        return build_source_skeleton_cache(raw,source_sha256=data['source_sha256'],
                                          snapshot_sha256=sha256(raw).hexdigest(),**kwargs)

    def test_nonidentity_rest_pose_world_and_real_tail_analytical_endpoints(self):
        cache = self.build()
        for index in (0,1,3):
            segments = tuple(struct.iter_unpack('<6f',cache.frame(index)))
            self.assertEqual(segments[0],(92.+index,207.,309.,92.+index,205.,309.))
            self.assertEqual(segments[1],(100.+index,200.,300.,99.+index,200.,300.))
            self.assertEqual(segments[2],(95.+index,200.,300.,94.+index,200.,300.))

    def test_small_valid_rest_scale_is_inverted_without_false_singularity(self):
        from blender_bridge.fbx_source import pose_digest
        data = analytical_source_snapshot(); scale = 1e-5
        bone = data['bones'][0]
        for r in range(3):
            for c in range(3):bone['matrix'][r*4+c] *= scale
        bone['tail']=[2.,3.,4.+2*scale]
        for row in data['frames']:
            for r in range(3):
                for c in range(3):row['poses'][0][r*4+c] *= scale
            row['pose_sha256']=pose_digest(row['armature_world'],row['poses'])
        cache=self.build(data)
        expected=struct.unpack('<6f',struct.pack('<6f',92.,207.,309.,92.,207.-2*scale,309.))
        self.assertEqual(tuple(struct.iter_unpack('<6f',cache.frame(0)))[0],expected)

    def test_complete_multiroot_order_and_already_global_pose_not_parent_reapplied(self):
        cache = self.build()
        self.assertEqual(cache.bone_names,('RootA','RootB','Child'))
        self.assertEqual(cache.parent_indices,(None,None,0))
        self.assertEqual(cache.bone_count,3)
        self.assertEqual(len(cache.frames),4)
        self.assertTrue(all(len(frame)==3*24 for frame in cache.frames))
        self.assertEqual(tuple(struct.iter_unpack('<6f',cache.frame(0)))[2][:3],(95.,200.,300.))

    def test_clock_origin_full_count_and_span_are_preserved(self):
        for first,count in ((1,300),(1,180),(1,210),(-5,4),(2,300)):
            with self.subTest(first=first,count=count):
                cache = self.build(analytical_source_snapshot(first,count))
                self.assertEqual((cache.source_first_frame,cache.frame_count,cache.fps),(first,count,30.))
                self.assertEqual(cache.clock.source_frame_at_index(count-1),first+count-1)
                self.assertEqual(cache.clock.sample_span_s,(count-1)/30)
                self.assertEqual(cache.clock.nominal_coverage_s,count/30)

    def test_world_bounds_cover_every_packed_head_and_tail(self):
        cache = self.build()
        self.assertEqual(cache.minimum,(92.,200.,300.))
        self.assertEqual(cache.maximum,(103.,207.,309.))
        self.assertAlmostEqual(cache.radius,(11**2+7**2+9**2)**.5/2)
        self.assertEqual(cache.coordinate_space,'BLENDER_WORLD_Z_UP')

    def test_frame_indices_reject_outside_bool_and_noninteger(self):
        cache = self.build()
        for index in (-1,4,True,1.,'1',None):
            with self.subTest(index=index),self.assertRaises(ValidationError):
                cache.frame(index)

    def test_cache_is_immutable_and_does_not_retain_mutable_snapshot(self):
        data = analytical_source_snapshot();before = deepcopy(data);cache = self.build(data)
        self.assertEqual(data,before)
        frame = cache.frame(0);data['frames'][0]['poses'][0][3]=123.
        self.assertEqual(cache.frame(0),frame)
        with self.assertRaises(FrozenInstanceError):cache.frames=()
        with self.assertRaises(TypeError):cache.frames[0][0]=0
        self.assertNotIn(str(frame),repr(cache))

    def test_exact_snapshot_and_source_hashes_are_required(self):
        data = analytical_source_snapshot();raw = json.dumps(data).encode()
        for source,snapshot in (('b'*64,sha256(raw).hexdigest()),
                                (data['source_sha256'],'b'*64),(True,sha256(raw).hexdigest())):
            with self.subTest(source=source),self.assertRaises(ValidationError):
                build_source_skeleton_cache(raw,source_sha256=source,snapshot_sha256=snapshot)

    def test_captured_bytes_type_and_size_are_bounded(self):
        data = analytical_source_snapshot();raw = json.dumps(data).encode()
        for value in ('{}',bytearray(raw),b''):
            with self.subTest(value=type(value)),self.assertRaises(ValidationError):
                build_source_skeleton_cache(value,source_sha256=data['source_sha256'],snapshot_sha256='a'*64)
        with patch('ucc.animations.source_skeleton.MAX_SNAPSHOT_BYTES',len(raw)-1):
            with self.assertRaises(ValidationError):self.build(raw=raw)

    def test_duplicate_nonfinite_invalid_json_or_schema_reject(self):
        data = analytical_source_snapshot();raw = json.dumps(data).encode()
        for payload in (b'{"schema_version":1,"schema_version":1}',b'NaN',b'{',b'[]',
                        raw.replace(b'100.0',b'1e999',1)):
            with self.subTest(payload=payload[:30]),self.assertRaises(ValidationError):self.build(raw=payload)
        for change in ({'schema_version':True},{'engine_import_verified':True},{'first_frame':True}):
            with self.subTest(change=change),self.assertRaises(ValidationError):self.build(data|change)

    def test_incomplete_pose_timeline_or_rest_orientation_reject(self):
        for fault in ('missing_sample','missing_pose','bad_rest','rehashed_bad_matrix'):
            data = analytical_source_snapshot()
            if fault=='missing_sample':data['frames'].pop()
            elif fault=='missing_pose':data['frames'][0]['poses'].pop()
            elif fault=='bad_rest':data['bones'][0]['tail']=[2.,5.,4.]
            else:
                row=data['frames'][0];row['poses'][0][0]=float('inf')
            with self.subTest(fault=fault),self.assertRaises(ValidationError):self.build(data)

    def test_object_motion_changes_both_endpoints_without_inventing_skin(self):
        cache = self.build()
        first = tuple(struct.iter_unpack('<6f',cache.frame(0)))
        last = tuple(struct.iter_unpack('<6f',cache.frame(3)))
        for a,b in zip(first,last):
            self.assertEqual(tuple(y-x for x,y in zip(a,b)),(3.,0.,0.,3.,0.,0.))
        self.assertFalse(hasattr(cache,'triangles'))
        self.assertFalse(hasattr(cache,'target_preview_verified'))

    def test_cancellation_before_hash_and_during_derivation_propagates(self):
        def immediate():raise CancelledForTest('caller cancellation')
        with self.assertRaises(CancelledForTest):self.build(cancel_check=immediate)
        calls=[]
        self.build(cancel_check=lambda:calls.append(None))
        cutoff=len(calls)-2;current=[]
        def late():
            current.append(None)
            if len(current)>=cutoff:raise CancelledForTest('late cancellation')
        with self.assertRaises(CancelledForTest):self.build(cancel_check=late)


if __name__=='__main__':unittest.main()
