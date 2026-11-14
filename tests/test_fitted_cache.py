"""Original synthetic cache contracts, never real animation compatibility proof."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from fixtures.motion_skin_contract import write_cache,file_record
from ucc.core.errors import ValidationError
from ucc.preview.fitted_cache import read_fitted_cache,FIT_HASHES
from ucc.preview.surface_review import SurfaceReview


class FittedCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        data,_report,bindings,self.base=write_cache(self.root)
        self.bindings={k:bindings.get(k,'b'*64) for k in FIT_HASHES}
        path=self.root/'fitted_skin.bin';(self.root/'motion_skin.bin').rename(path)
        data.update(status='FITTED_VERIFIED_SKIN_CACHE_V1',bindings=self.bindings,geometry=file_record(path),contact_quality_verified=False)
        self.data=data;self.hashes=[]
        binary=path.read_bytes()
        for row in data['frames']:
            raw=zlib.decompress(binary[row['offset']:row['offset']+row['compressed_bytes']])
            self.hashes.append(sha256(raw[12*data['vertex_count']:]).hexdigest())
        self.fitted={'frame_count':3,'fps':30.,'source_first_frame':7,'mesh_world':data['world_matrix'],
                     'frames':[{'skin_sha256':r['skin_sha256'],'triangle_sha256':h,'vertex_count':120,'triangle_count':120}
                               for r,h in zip(data['frames'],self.hashes)]}
        self.surface=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,tuple(self.hashes))
        self.report={'status':'REAL_NATIVE_FIT_CACHE_EXPORTED','bindings':self.bindings,'frames_verified':3,'originals_unchanged':True,
                     'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
        self.rewrite()

    def rewrite(self):
        p=self.root/'fitted_skin.json';p.write_text(json.dumps(self.data));self.report['manifest']=file_record(p)

    def load(self,**kw):return read_fitted_cache(self.root,self.report,self.bindings,self.fitted,self.base,self.surface,**kw)

    def test_complete_distinct_fitted_cache_is_immutable_and_pose_topology_bound(self):
        cache=self.load();self.assertEqual(cache.frame_count,3);self.assertNotEqual(cache.frame(0),cache.frame(2))
        first=cache.frame(0);(self.root/'fitted_skin.bin').write_bytes(b'changed');self.assertEqual(cache.frame(0),first)
        self.assertIs(cache.surface_review,self.surface)

    def test_published_schema_closes_fitted_provenance_and_geometry(self):
        try:from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('Optional JSON Schema validator unavailable')
        path=Path(__file__).resolve().parents[1]/'docs/schemas/fitted-skin.v1.schema.json'
        schema=Draft202012Validator(json.loads(path.read_text()));schema.validate(self.data)
        for key,value in (('bindings',{}),('status','NATIVE_VERIFIED_SKIN_CACHE_V1'),('contact_quality_verified',True)):
            bad=deepcopy(self.data);bad[key]=value;self.assertTrue(list(schema.iter_errors(bad)))

    def test_rehashed_wrong_topology_rejected_even_when_all_skin_hashes_match(self):
        self.fitted['frames'][1]['triangle_sha256']='f'*64
        self.surface=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,tuple(r['triangle_sha256'] for r in self.fitted['frames']))
        with self.assertRaisesRegex(ValidationError,'topology'):self.load()

    def test_wrong_scope_missing_verification_flags_timing_world_and_frame_counts_reject(self):
        original=deepcopy(self.data);original_report=deepcopy(self.report)
        for key,value in (('status','NATIVE_VERIFIED_SKIN_CACHE_V1'),('schema_version',True),('frame_count',2),('fps',60),
                          ('source_first_frame',1),('world_matrix',[0]*16),('world_matrix',[10**400]*16),('contact_quality_verified',True),
                          ('geometry',{'name':'motion_skin.bin','bytes':10,'sha256':'a'*64}),('unreviewed_override',True)):
            self.data=deepcopy(original);self.data[key]=value;self.rewrite()
            with self.subTest(key=key),self.assertRaises(ValidationError):self.load()
        self.data=original;self.rewrite()
        for key,value in (('status','REAL_NATIVE_SKIN_CACHE_EXPORTED'),('frames_verified',2),('originals_unchanged',False),
                          ('contact_quality_verified',0),('bindings',{}),('skip_verification',True)):
            self.report=deepcopy(original_report);self.report[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):self.load()

    def test_unavailable_or_crossing_surface_never_published_and_cancel_propagates(self):
        for status,pairs in (('UNAVAILABLE',((0,0),)*3),('CHECKED',((0,0),(1,0),(0,0)))):
            self.surface=SurfaceReview(status,'', ((),)*3,pairs,tuple(self.hashes))
            with self.assertRaises(ValidationError):self.load()
        self.surface=SurfaceReview('CHECKED','',((),)*3,((0,0),)*3,tuple(self.hashes))
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.load(cancel_check=cancel)


if __name__=='__main__':unittest.main()
