"""Original tiny synthetic cache boundaries; never animation-pack proof."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from fixtures.motion_skin_contract import write_cache,file_record
from ucc.core.errors import ValidationError
from ucc.preview.motion_cache import read_motion_cache,unpack_frame,MAX_BYTES
from ucc.preview.playback_clock import PlaybackClock
from ucc.jobs.protocol import JobRequest


class MotionCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.data,self.report,self.bindings,self.timeline=write_cache(self.root)

    def load(self):return read_motion_cache(self.root,self.report,self.bindings,self.timeline)

    def rewrite(self):
        path=self.root/"motion_skin.json";path.write_text(json.dumps(self.data));self.report["manifest"]=file_record(path)

    def test_complete_geometry_frames_and_adaptive_triangles_preserved_in_immutable_memory(self):
        cache=self.load();self.assertEqual((cache.frame_count,cache.vertex_count,cache.triangle_count),(3,120,120))
        self.assertNotEqual(cache.frame(0)[0],cache.frame(2)[0]);self.assertNotEqual(cache.frame(0)[1],cache.frame(2)[1])
        expected=cache.frame(0);(self.root/"motion_skin.bin").write_bytes(b"REPLACED_ON_DISK")
        self.assertEqual(cache.frame(0),expected)
        for frame in (-1,3,True):
            with self.assertRaises(ValidationError):cache.frame(frame)

    def test_counts_fps_policy_approvals_and_world_transform_reject(self):
        original=deepcopy(self.data)
        for key,value in (("frame_count",True),("frame_count",2),("fps",60),("vertex_count",100000),
                          ("triangle_count",200000),("schema_version",True),("coordinate_space","Y_UP"),
                          ("animation_visual_quality_verified",True),("engine_import_verified",0),
                          ("world_matrix",[0]*16),("world_matrix",[float('nan')]*16)):
            self.data=deepcopy(original);self.data[key]=value;self.rewrite()
            with self.subTest(key=key,value=value),self.assertRaises(ValidationError):self.load()

    def test_frame_gaps_overlap_truncation_unknown_fields_and_wrong_hip_reject(self):
        original=deepcopy(self.data)
        for key,value in (("frame",2),("offset",0),("offset",9),("compressed_bytes",MAX_BYTES),
                          ("skin_sha256","b"*64),("raw_sha256","b"*64),("hip_world",[0,0,2]),("arbitrary_path","../x")):
            self.data=deepcopy(original);self.data["frames"][0][key]=value;self.rewrite()
            with self.subTest(key=key),self.assertRaises(ValidationError):self.load()

    def test_rehashed_wrong_skin_and_invalid_indices_still_reject(self):
        for mutation in ("skin","nan","index","degenerate"):
            self.data,self.report,self.bindings,self.timeline=write_cache(self.root)
            record=self.data["frames"][0];binary=(self.root/"motion_skin.bin").read_bytes()
            raw=bytearray(zlib.decompress(binary[record["offset"]:record["offset"]+record["compressed_bytes"]]))
            if mutation=="skin":struct.pack_into("<f",raw,0,.123)
            if mutation=="nan":struct.pack_into("<f",raw,0,float('nan'))
            if mutation=="index":struct.pack_into("<I",raw,1440,120)
            if mutation=="degenerate":struct.pack_into("<III",raw,1440,1,1,2)
            compressed=zlib.compress(raw,1);delta=len(compressed)-record["compressed_bytes"]
            binary=binary[:8]+compressed+binary[8+record["compressed_bytes"]:]
            record["compressed_bytes"]=len(compressed);record["raw_sha256"]=sha256(raw).hexdigest()
            for row in self.data["frames"][1:]:row["offset"]+=delta
            path=self.root/"motion_skin.bin";path.write_bytes(binary);self.data["geometry"]=file_record(path);self.rewrite()
            with self.subTest(mutation=mutation),self.assertRaises(ValidationError):self.load()

    def test_decompression_caps_and_concatenation(self):
        for packed,size in ((zlib.compress(b"a"*100000),10),(zlib.compress(b"a")+zlib.compress(b"b"),1),
                            (zlib.compress(b"a")[:-1],1),(b"notzlib",100)):
            with self.assertRaises(ValidationError):unpack_frame(packed,size)

    def test_trailing_bytes_and_wrong_binary_sha_reject(self):
        path=self.root/"motion_skin.bin";path.write_bytes(path.read_bytes()+b"trailing")
        with self.assertRaises(ValidationError):self.load()
        self.data["geometry"]=file_record(path);self.rewrite()
        with self.assertRaises(ValidationError):self.load()

    def test_unreopened_wrong_source_and_cancel_reject(self):
        self.report["saved_review_verification"]["uncorrected_skin_frames_verified"]=2
        with self.assertRaises(ValidationError):self.load()
        self.report["saved_review_verification"]["uncorrected_skin_frames_verified"]=3
        self.report["bindings"]={**self.bindings,"source_sha256":"f"*64}
        with self.assertRaises(ValidationError):self.load()
        self.report["bindings"]=self.bindings
        def cancelled():raise RuntimeError("cancelled")
        with self.assertRaisesRegex(RuntimeError,"cancelled"):read_motion_cache(self.root,self.report,self.bindings,self.timeline,cancel_check=cancelled)

    def test_protocol_has_six_identities_no_paths_or_override(self):
        JobRequest.new("cache_native_fbx_body",input_project="candidate.blend",options=self.bindings)
        for options in ({**self.bindings,"frames":10},{**self.bindings,"source_sha256":"bad"},{}):
            with self.assertRaises(ValidationError):JobRequest.new("cache_native_fbx_body",input_project="candidate.blend",options=options)

    def test_duplicate_json_unknown_fields_and_changed_world_axes_reject(self):
        original=deepcopy(self.data)
        for change in ("duplicate","unknown","reflection","shear","first_frame"):
            self.data=deepcopy(original)
            if change=="unknown":self.data["execute_shader"]="untrusted"
            if change=="reflection":self.data["world_matrix"][0]=-1
            if change=="shear":self.data["world_matrix"][1]=.1
            if change=="first_frame":self.data["source_first_frame"]=8
            self.rewrite()
            if change=="duplicate":
                path=self.root/"motion_skin.json";path.write_text(path.read_text()[:-1]+',"fps":30}')
                self.report["manifest"]=file_record(path)
            with self.subTest(change=change),self.assertRaises(ValidationError):self.load()

    def test_redirected_binary_is_rejected(self):
        path=self.root/"motion_skin.bin";target=self.root/"original.bin";path.rename(target)
        try:path.symlink_to(target)
        except OSError:self.skipTest("Creating symlinks needs Windows privileges")
        with self.assertRaises(ValidationError):self.load()


class PlaybackClockTests(unittest.TestCase):
    def test_elapsed_time_preserves_fps_despite_late_timers(self):
        clock=PlaybackClock(300,30.);clock.play(10.)
        self.assertEqual(clock.advance(10.1),3);self.assertEqual(clock.advance(15.),150)
        self.assertEqual(clock.advance(20.1),3)
        clock.pause(21.);self.assertEqual(clock.frame,30);self.assertEqual(clock.advance(99.),30)

    def test_scrub_pause_resume_and_end_without_loop(self):
        clock=PlaybackClock(300,30.,loop=False);clock.seek(150,1.);clock.play(2.)
        self.assertEqual(clock.advance(3.),180);clock.seek(299,3.);clock.advance(3.04)
        self.assertFalse(clock.playing);self.assertEqual(clock.frame,299)
        clock.play(4.);self.assertEqual(clock.frame,0)
        for index in (-1,300,True):
            with self.assertRaises(ValueError):clock.seek(index,5.)
