"""Boundary-chain and recentering contracts on original nonshipping geometry."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from blender_bridge.central_geometry import central_geometry,outward_probe

IDENTITY=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)


class CentralGeometryTests(unittest.TestCase):
    def setUp(self):
        d=json.loads((Path(__file__).parent/'fixtures/central_patch_tube.json').read_text(encoding='utf-8'))
        self.points=d['points'];self.polygons=d['polygons'];self.members=set(range(8));self.ids=[];self.triangles=[]
        for index,face in enumerate(self.polygons):
            self.triangles.extend([(face[0],face[1],face[2]),(face[0],face[2],face[3])]);self.ids.extend([index,index])

    def build(self,**kwargs):
        args={'points':self.points,'triangles':self.triangles,'polygon_ids':self.ids,'polygons':self.polygons,
            'members':self.members,'world':IDENTITY,'expected_caps':1};args.update(kwargs)
        return central_geometry(**args)

    def test_complete_polygon_patch_has_closed_positive_oriented_chain(self):
        result=self.build();self.assertAlmostEqual(result.signed_volume,1.);self.assertEqual(result.body_vertex_ids,tuple(range(8)))
        self.assertEqual(len(result.body_faces),10);self.assertEqual(len(result.cap_faces),4);self.assertEqual(len(result.boundaries),1)
        self.assertEqual(result.pivot_local,(.5,.5,.5));self.assertEqual(result.origin_world,(.5,.5,.5))
        self.assertEqual(result.bounds,((-.5,-.5,-.5),(.5,.5,.5)))

    def test_world_translation_does_not_enter_relative_geometry(self):
        baseline=self.build();world=list(IDENTITY);world[3]=9999.;world[7]=-8888.;world[11]=7777.
        translated=self.build(world=tuple(world))
        self.assertEqual(baseline.skin_points,translated.skin_points);self.assertEqual(baseline.body_points,translated.body_points)
        self.assertEqual(baseline.cap_boxes,translated.cap_boxes);self.assertEqual(translated.origin_world,(9999.5,-8887.5,7777.5))

    def test_linear_scale_rotation_and_orientation_are_measured(self):
        world=(0.,-2.,0.,0.,3.,0.,0.,0.,0.,0.,4.,0.,0.,0.,0.,1.)
        self.assertAlmostEqual(self.build(world=world).signed_volume,24.)
        inverted=list(IDENTITY);inverted[0]=-1.
        with self.assertRaises(ValueError):self.build(world=tuple(inverted))
        degenerate=list(IDENTITY);degenerate[0]=0.
        with self.assertRaises(ValueError):self.build(world=tuple(degenerate))

    def test_quad_diagonal_changes_keep_polygon_selection_and_boundaries(self):
        baseline=self.build();triangles=[]
        for a,b,c,d in self.polygons:triangles.extend([(a,b,d),(b,c,d)])
        changed=self.build(triangles=triangles)
        self.assertEqual(baseline.body_vertex_ids,changed.body_vertex_ids);self.assertEqual(baseline.boundaries,changed.boundaries)
        self.assertEqual(baseline.cap_boxes,changed.cap_boxes);self.assertAlmostEqual(changed.signed_volume,baseline.signed_volume)

    def test_partial_polygon_is_not_promoted_by_a_convenient_triangle_split(self):
        # Three upper-ring vertices alone cannot add half a mixed polygon.
        a=self.build(members=self.members|{8,9,10});triangles=[]
        for x,y,z,w in self.polygons:triangles.extend([(x,y,w),(y,z,w)])
        b=self.build(members=self.members|{8,9,10},triangles=triangles)
        self.assertEqual(a.body_vertex_ids,b.body_vertex_ids);self.assertEqual(a.boundaries,b.boundaries)

    def test_incomplete_wrong_duplicate_or_boolean_triangulation_rejects(self):
        for case in ('missing','wrong','duplicate','boolean','polygon'):
            triangles=list(self.triangles);ids=list(self.ids);polygons=deepcopy(self.polygons)
            if case=='missing':triangles.pop();ids.pop()
            if case=='wrong':ids[0]=1
            if case=='duplicate':triangles[1]=triangles[0]
            if case=='boolean':ids[0]=True
            if case=='polygon':polygons[0].append(polygons[0][0])
            with self.subTest(case=case),self.assertRaises(ValueError):self.build(triangles=triangles,polygon_ids=ids,polygons=polygons)

    def test_production_four_boundary_scope_and_cancellation_are_strict(self):
        with self.assertRaisesRegex(ValueError,'BOUNDARY_COUNT'):self.build(expected_caps=4)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):self.build(cancel_check=cancel)
        bad=list(IDENTITY);bad[-1]=0.
        with self.assertRaises(ValueError):self.build(world=bad)

    def test_hand_probes_follow_actual_transformed_face_orientation(self):
        points=((0.,0.,0.),(3.,0.,0.),(0.,3.,0.))
        self.assertEqual(outward_probe(points,(0,1,2),.01),(1.,1.,.01))
        self.assertEqual(outward_probe(points,(0,2,1),.01),(1.,1.,-.01))
        for tri,offset in (((0,0,1),.01),((0,1,3),.01),((0,1,True),.01),((0,1,2),True),((0,1,2),0.)):
            with self.assertRaises(ValueError):outward_probe(points,tri,offset)
        with self.assertRaises(ValueError):outward_probe(((0.,0.,0.),(1.,0.,0.),(2.,0.,0.)),(0,1,2),.01)
