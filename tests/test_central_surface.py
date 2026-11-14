"""Nonshipping identity tests; fake BVH responses are not collision evidence."""
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from fixtures.central_enclosure_contract import central_contract
from blender_bridge.central_geometry import central_geometry
from blender_bridge.central_surface import observe_central_surfaces


class RecordingTree:
    calls=[]

    @classmethod
    def FromPolygons(cls,points,faces,*,all_triangles):
        instance=cls();instance.index=len(cls.calls)
        cls.calls.append((list(points),list(faces),all_triangles))
        return instance

    def overlap(self,body):
        assert body.index==0
        return [(0,0),(0,1)] if self.index==1 else []


class CompleteTrunkSurfaceTests(unittest.TestCase):
    def setUp(self):
        data,cache,_,polygons,_=central_contract();vertices,indices=cache.frame(0)
        self.points=list(struct.iter_unpack('<fff',vertices));self.triangles=list(struct.iter_unpack('<III',indices))
        self.polygons=polygons
        self.poly_ids=[next(i for i,p in enumerate(polygons) if set(t)<=set(p)) for t in self.triangles]
        self.members=set(data['region_vertex_ids']['central_body'])
        self.hands={s:set(data['region_vertex_ids'][s+'_hand']) for s in ('left','right')}
        self.geometry=central_geometry(self.points,self.triangles,self.poly_ids,polygons,self.members,tuple(data['world_matrix']))
        RecordingTree.calls=[]

    def observe(self,geometry=None,**kwargs):
        return observe_central_surfaces(geometry or self.geometry,self.triangles,self.poly_ids,self.hands,RecordingTree,**kwargs)

    def test_exact_global_triangle_order_and_stable_polygon_identities_are_retained(self):
        result=self.observe();left=result['left'];body=self.geometry.body_triangle_ids
        selected=[i for i,t in enumerate(self.triangles) if set(t)<=self.hands['left']]
        self.assertEqual(result['body_triangle_ids'],list(body))
        self.assertEqual(left['selected_hand_triangles'],selected)
        self.assertEqual(left['pair_count'],2)
        self.assertEqual(left['hand_triangles'],selected[:1])
        self.assertEqual(left['central_triangles'],list(body[:2]))
        self.assertEqual(left['hand_polygons'],[self.poly_ids[selected[0]]])
        self.assertEqual(left['body_polygons'],sorted({self.poly_ids[i] for i in body[:2]}))
        self.assertEqual(result['right']['pair_count'],0)

    def test_virtual_cap_faces_never_enter_the_actual_body_bvh(self):
        self.observe()
        self.assertEqual(RecordingTree.calls[0][1],list(self.geometry.body_faces))
        self.assertTrue(self.geometry.cap_faces)
        self.assertEqual(len(RecordingTree.calls),3)

    def test_reordered_compact_faces_and_omitted_body_identity_fail_before_query(self):
        for geometry in (replace(self.geometry,body_faces=tuple(reversed(self.geometry.body_faces))),
                         replace(self.geometry,body_triangle_ids=self.geometry.body_triangle_ids[:-1])):
            with self.assertRaisesRegex(ValueError,'BODY_'):self.observe(geometry)
        self.assertFalse(RecordingTree.calls)

    def test_missing_overlapping_hand_selection_or_excess_work_has_no_partial_result(self):
        original=self.hands
        for hands in ({'left':set(),'right':original['right']},
                      {'left':original['left'],'right':original['left']},
                      {'left':original['left']}):
            self.hands=hands
            with self.assertRaises(ValueError):self.observe()
        self.hands=original
        with patch('blender_bridge.central_surface.MAX_PAIR_WORK',1),self.assertRaisesRegex(ValueError,'WORKLOAD'):
            self.observe()
        self.assertFalse(RecordingTree.calls)

    def test_cancellation_and_highlight_budget_never_return_partial_hand_verdicts(self):
        def cancelled():raise RuntimeError('unit cancellation')
        with self.assertRaisesRegex(RuntimeError,'unit cancellation'):self.observe(cancel_check=cancelled)
        self.assertFalse(RecordingTree.calls)
        with patch('blender_bridge.central_surface.MAX_HIGHLIGHTS',1),self.assertRaisesRegex(ValueError,'HIGHLIGHTS'):
            self.observe()


if __name__=='__main__':unittest.main()
