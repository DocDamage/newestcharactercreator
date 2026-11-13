"""Closed metadata/topology/verification negatives, never Blender proof."""
from copy import deepcopy
from hashlib import sha256
import json,struct,tempfile,unittest,zlib
from pathlib import Path
from fixtures.surface_cache_contract import write_surface_cache
from fixtures.motion_skin_contract import file_record
from ucc.core.errors import ValidationError
from ucc.preview.motion_cache import read_motion_cache
from ucc.jobs.protocol import JobRequest
from blender_bridge.native_surface_review import limb_bones,weighted_region


class SurfaceReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.reset()

    def reset(self):
        self.data,self.report,self.bindings,self.timeline,self.profile,self.surface,self.verified=write_surface_cache(self.root)

    def load(self,verification=True):
        return read_motion_cache(self.root,self.report,self.bindings,self.timeline,profile=self.profile,
                                 surface_verification=self.verified if verification else None)

    def rewrite(self):
        path=self.root/'motion_contacts.json';path.write_text(json.dumps(self.surface))
        record=file_record(path);self.data['surface_review']=self.report['surface_review']=record
        self.verified['bindings']['surface_review_sha256']=record['sha256']
        path=self.root/'motion_skin.json';path.write_text(json.dumps(self.data));self.report['manifest']=file_record(path)

    def test_complete_immutable_review_tracks_pose_specific_triangle_buffers(self):
        cache=self.load();s=cache.surface_review
        self.assertEqual(s.flagged_frames,(1,));self.assertEqual(s.triangles[1],(1,2))
        self.assertNotEqual(s.triangle_hashes[0],s.triangle_hashes[1])
        (self.root/'motion_contacts.json').write_bytes(b'REPLACED')
        self.assertEqual(cache.surface_review.triangles[1],(1,2))

    def test_missing_or_incomplete_fresh_verification_cannot_publish_annotations(self):
        with self.assertRaises(ValidationError):self.load(False)
        for key,value in (('frames_verified',True),('frames_verified',2),('originals_unchanged',False),('contact_quality_verified',True)):
            self.reset();self.verified[key]=value
            with self.subTest(key=key),self.assertRaises(ValidationError):self.load()

    def test_rehashed_bad_coverage_regions_flags_counts_and_indices_reject(self):
        for kind in ('frame','skin','coverage','version','approved','unknown','shared_bone','unknown_bone','wrong_hand','count_bool','id_bool','id_range','duplicate','shared_triangle','digest'):
            self.reset();s=self.surface;hit=s['frames'][1]['left']
            if kind=='frame':s['frames'][0]['frame']=True
            if kind=='skin':s['frames'][0]['skin_sha256']='f'*64
            if kind=='coverage':s['frames'].pop()
            if kind=='version':s['schema_version']=True
            if kind=='approved':s['contact_quality_verified']=True
            if kind=='unknown':s['unchecked_path']='../../source'
            if kind=='shared_bone':s['region_bones']['left_arm']=['WL']
            if kind=='unknown_bone':s['region_bones']['left_arm']=['unknown']
            if kind=='wrong_hand':s['hands']['left']='WR'
            if kind=='count_bool':hit['pair_count']=True
            if kind=='id_bool':hit['hand_triangles']=[True]
            if kind=='id_range':hit['hand_triangles']=[120]
            if kind=='duplicate':hit.update(pair_count=2,hand_triangles=[1,1])
            if kind=='shared_triangle':hit['opposite_arm_triangles']=[1]
            if kind=='digest':s['frames'][0]['left']['pair_sha256']='f'*64
            self.rewrite()
            with self.subTest(kind=kind),self.assertRaises(ValidationError):self.load()

    def test_unavailable_review_never_claims_partial_zero_intersection_success(self):
        self.surface.update(status='UNAVAILABLE',reason='WEIGHTED_REGIONS_UNAVAILABLE')
        for row in self.surface['frames']:row['left']=row['right']=None
        self.rewrite();s=self.load().surface_review
        self.assertEqual(s.status,'UNAVAILABLE');self.assertEqual(s.flagged_frames,())
        self.surface['frames'][0]['left']={'pair_count':0};self.rewrite()
        with self.assertRaises(ValidationError):self.load()

    def test_rehashed_valid_range_topology_change_still_must_match_actual_scene_review(self):
        old=(self.root/'motion_skin.bin').read_bytes();binary=bytearray(old[:8])
        for frame,record in enumerate(self.data['frames']):
            raw=bytearray(zlib.decompress(old[record['offset']:record['offset']+record['compressed_bytes']]))
            if frame==0:struct.pack_into('<III',raw,1440,119,1,11)
            packed=zlib.compress(raw,1);record.update(offset=len(binary),compressed_bytes=len(packed),raw_sha256=sha256(raw).hexdigest());binary.extend(packed)
        path=self.root/'motion_skin.bin';path.write_bytes(binary);self.data['geometry']=file_record(path);self.rewrite()
        with self.assertRaisesRegex(ValidationError,'topology differs'):self.load()

    def test_surface_job_requires_seven_exact_sha_bound_inputs(self):
        options={**self.bindings,'surface_review_sha256':'b'*64}
        JobRequest.new('verify_native_surface_review',input_project='candidate.blend',options=options)
        for bad in ({**options,'path':'../../private'},self.bindings,{**options,'surface_review_sha256':True}):
            with self.assertRaises(ValidationError):JobRequest.new('verify_native_surface_review',input_project='candidate.blend',options=bad)

    def test_rehashed_valid_world_transform_must_match_fresh_scene(self):
        self.data['world_matrix'][3]=1.
        self.rewrite()
        with self.assertRaisesRegex(ValidationError,'independently reproduced'):self.load()
        self.reset();self.verified['world_matrix'][0]=True
        with self.assertRaises(ValidationError):self.load()


class SurfaceRegionTests(unittest.TestCase):
    def test_deform_weight_normalization_and_wrist_ties_partition_vertices(self):
        regions={'left_hand':{'LH'},'right_hand':{'RH'},'left_arm':{'LA'},'right_arm':{'RA'}}
        deform={'LH','RH','LA','RA','body'}
        self.assertEqual(weighted_region({'RH':1.,'RA':1.,'mask':1.},regions,deform),'right_hand')
        self.assertEqual(weighted_region({'LH':.25,'body':.25},regions,deform),'left_hand')
        self.assertIsNone(weighted_region({'RH':.49,'body':.51},regions,deform))
        self.assertIsNone(weighted_region({'mask':1.},regions,deform))

    def test_regions_follow_real_ancestry_without_name_aliases(self):
        p={'body':None,'sL':'body','aL':'sL','wL':'aL','fL':'wL','sR':'body','aR':'sR','wR':'aR','fR':'wR'}
        regions=limb_bones(p,{'left':'wL','right':'wR'},set(p))
        self.assertEqual(regions['left_hand'],{'wL','fL'});self.assertEqual(regions['right_arm'],{'sR','aR'})
        self.assertNotIn('body',set.union(*regions.values()))
        with self.assertRaises(ValueError):limb_bones({'wL':None,'wR':None},{'left':'wL','right':'wR'},{'wL','wR'})
