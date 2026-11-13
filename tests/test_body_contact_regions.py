"""Invented rigs/overlap lists test contracts only, not physical contact evidence."""
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch

from blender_bridge.body_contact_regions import central_regions,weighted_central_region,MAX_TRANSIENT_PAIRS
from blender_bridge.native_body_contacts import triangle_pairs,BodyContactInspector


class BodyContactRegionTests(unittest.TestCase):
    def setUp(self):
        self.parents={'root':None,'spine':'root','head':'spine'}
        for side in ('L','R'):
            self.parents.update({f'shoulder{side}':'spine',f'upper{side}':f'shoulder{side}',f'lower{side}':f'upper{side}',
                f'hand{side}':f'lower{side}',f'finger{side}':f'hand{side}'})
        self.deform=set(self.parents)-{'root'};self.hands={'left':'handL','right':'handR'}

    def test_actual_ancestry_excludes_arms_and_includes_head_and_central_chain(self):
        regions=central_regions(self.parents,self.hands,'head',self.deform)
        self.assertEqual(regions,{'left_hand':{'handL','fingerL'},'right_hand':{'handR','fingerR'},'central_body':{'spine','head'}})
        self.assertEqual(weighted_central_region({'handL':.5,'head':.5},regions,self.deform),'left_hand')
        self.assertEqual(weighted_central_region({'handL':.4,'head':.3,'spine':.3},regions,self.deform),'central_body')
        self.assertIsNone(weighted_central_region({'handL':.4,'lowerL':.6},regions,self.deform))
        self.assertEqual(weighted_central_region({'handR':.1,'mask':1.},regions,self.deform),'right_hand')

    def test_missing_cyclic_overlapping_multiroot_and_nonfinite_weights_reject(self):
        for fault in ('missing','cycle','root','overlap'):
            parents=dict(self.parents)
            if fault=='missing':parents.pop('lowerL')
            if fault=='cycle':parents['spine']='head'
            if fault=='root':parents['head']=None
            head='handL' if fault=='overlap' else 'head'
            with self.subTest(fault=fault),self.assertRaises(ValueError):central_regions(parents,self.hands,head,self.deform)
        regions=central_regions(self.parents,self.hands,'head',self.deform)
        for weight in (-.1,1.1,True,float('nan'),float('inf'),10**400):
            with self.assertRaises(ValueError):weighted_central_region({'handL':weight},regions,self.deform)

    def test_compact_chunk_queries_reproduce_global_pair_order_and_sha_with_bounded_lists(self):
        class Tree:
            sizes=[]
            def __init__(self,faces):self.faces=faces
            @classmethod
            def FromPolygons(cls,points,faces,**kwargs):
                cls.sizes.append((len(points),len(faces)));return cls(faces)
            def overlap(self,body):return [(a,b) for a in range(len(self.faces)-1,-1,-1) for b in (2,0)]
        points=[(i,0,0) for i in range(510)]
        hand=[(1000+i,(3*i,3*i+1,3*i+2)) for i in range(170)];body=[(8000+i,(0,1,2)) for i in range(10000)]
        result=triangle_pairs(points,hand,body,Tree)
        expected=sorted((i,8000+b) for i,_ in hand for b in (0,2))
        self.assertEqual(result['pair_count'],340)
        self.assertEqual(result['pair_sha256'],sha256(b''.join(struct.pack('<II',a,b) for a,b in expected)).hexdigest())
        self.assertEqual(result['hand_triangles'],list(range(1000,1170)));self.assertEqual(result['central_triangles'],[8000,8002])
        self.assertTrue(all(n<=3*t and t*len(body)<=MAX_TRANSIENT_PAIRS for n,t in Tree.sizes[1:]))
        with patch('blender_bridge.native_body_contacts.MAX_PAIRS_PER_FRAME',2),self.assertRaisesRegex(ValueError,'PAIR_BUDGET'):
            triangle_pairs(points,hand,body,Tree)

    def test_excessive_work_empty_regions_and_unavailable_partial_results_never_claim_zero(self):
        with self.assertRaisesRegex(ValueError,'WORKLOAD'):
            triangle_pairs([],[(1,(0,1,2))]*2000,[(2,(3,4,5))]*30000,None)
        with self.assertRaisesRegex(ValueError,'REGIONS_UNAVAILABLE'):triangle_pairs([],[],[],None)
        inspector=BodyContactInspector.__new__(BodyContactInspector);inspector.rows=[{'left':{'pair_count':1},'right':{'pair_count':0}}]
        inspector.unavailable('SURFACE_WORKLOAD_EXCEEDED')
        self.assertEqual(inspector.status,'UNAVAILABLE');self.assertIsNone(inspector.rows[0]['left']);self.assertIsNone(inspector.rows[0]['right'])


if __name__=='__main__':unittest.main()
