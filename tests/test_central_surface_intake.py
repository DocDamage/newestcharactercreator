"""Nonshipping metadata forgeries; fixture contacts are not physical evidence."""
from copy import deepcopy
from hashlib import sha256
import struct
import unittest

from fixtures.central_enclosure_contract import central_contract
from ucc.core.errors import ValidationError
from ucc.preview.central_surface import _parse_variant,POLICY


def surface_contract():
    volume,cache,_,polygons,_=central_contract();rows=[]
    _,indices=cache.frame(0)
    def polygon(triangle):
        vertices=struct.unpack_from('<III',indices,triangle*12)
        return next(i for i,p in enumerate(polygons) if set(vertices)<=set(p))
    for reference in volume['frames']:
        expected=reference['observation'];body=expected['body_triangle_ids'];observation={'body_triangle_ids':list(body)}
        for side in ('left','right'):
            selected=expected[side]['selected_triangles'];contact=side=='left'
            observation[side]={'pair_count':int(contact),'pair_sha256':sha256(struct.pack('<II',selected[0],body[0]) if contact else b'').hexdigest(),
                'hand_triangles':selected[:1] if contact else [],'central_triangles':body[:1] if contact else [],
                'selected_hand_triangles':list(selected),'hand_polygons':[polygon(selected[0])] if contact else [],
                'body_polygons':[polygon(body[0])] if contact else []}
        rows.append({**{k:v for k,v in reference.items() if k!='observation'},'observation':observation})
    return {'frames':rows},cache,volume,polygons


class CompleteTrunkIntakeTests(unittest.TestCase):
    def setUp(self):self.data,self.cache,self.volume,self.polygons=surface_contract()

    def load(self,**kwargs):return _parse_variant(self.data,self.cache,self.volume,self.polygons,**kwargs)

    def test_all_frames_map_actual_triangles_to_stable_polygons_and_keep_per_hand_counts(self):
        result=self.load();self.assertEqual(result.surface.policy,POLICY)
        self.assertEqual(result.surface.pairs,((1,0),)*3)
        self.assertEqual(result.surface.flagged_frames,(0,1,2))
        for row,hand,body in zip(self.data['frames'],result.hand_polygons,result.body_polygons):
            self.assertEqual(hand[0],frozenset(row['observation']['left']['hand_polygons']))
            self.assertEqual(body[0],frozenset(row['observation']['left']['body_polygons']))
            self.assertFalse(hand[1]);self.assertFalse(body[1])

    def test_complete_scope_frame_hash_count_highlight_and_polygon_forgeries_reject(self):
        original=deepcopy(self.data)
        for fault in ('coverage','frame','skin','topology','body_scope','selection','hand_scope','body_highlight',
                      'impossible_count','bool_count','empty_digest','bad_digest','bool_id','duplicate','hand_poly','body_poly','extra'):
            self.data=deepcopy(original);row=self.data['frames'][0];obs=row['observation'];hit=obs['left']
            if fault=='coverage':self.data['frames'].pop()
            if fault=='frame':row['frame']=True
            if fault=='skin':row['skin_sha256']='0'*64
            if fault=='topology':row['triangle_sha256']='0'*64
            if fault=='body_scope':obs['body_triangle_ids'].pop()
            if fault=='selection':hit['selected_hand_triangles'].pop()
            if fault=='hand_scope':hit['hand_triangles']=obs['body_triangle_ids'][:1]
            if fault=='body_highlight':hit['central_triangles']=hit['selected_hand_triangles'][:1]
            if fault=='impossible_count':hit['pair_count']=2
            if fault=='bool_count':hit['pair_count']=True
            if fault=='empty_digest':hit['pair_sha256']=sha256().hexdigest()
            if fault=='bad_digest':hit['pair_sha256']='invalid'
            if fault=='bool_id':hit['hand_triangles']=[True]
            if fault=='duplicate':hit['hand_triangles']*=2
            if fault=='hand_poly':hit['hand_polygons']=hit['body_polygons'][:]
            if fault=='body_poly':hit['body_polygons']=hit['hand_polygons'][:]
            if fault=='extra':obs['quality_approved']=True
            with self.subTest(fault=fault),self.assertRaises(ValidationError):self.load()

    def test_empty_surface_pairs_do_not_claim_clearance_or_invent_a_quality_approval(self):
        for row in self.data['frames']:
            for side in ('left','right'):
                hit=row['observation'][side];hit.update(pair_count=0,pair_sha256=sha256().hexdigest(),
                    hand_triangles=[],central_triangles=[],hand_polygons=[],body_polygons=[])
        result=self.load();self.assertFalse(result.surface.flagged_frames)
        self.assertFalse(hasattr(result,'anatomical_clearance_verified'))

    def test_cancellation_returns_no_partial_sequence(self):
        count=0
        def cancelled():
            nonlocal count
            count+=1
            if count==4:raise RuntimeError('cancelled during complete intake')
        with self.assertRaisesRegex(RuntimeError,'cancelled during complete intake'):self.load(cancel_check=cancelled)


if __name__=='__main__':unittest.main()
