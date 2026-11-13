"""Original nonshipping geometry boundary tests, not body-volume acceptance."""
from collections import Counter
import json
import math
from pathlib import Path
import unittest

from blender_bridge.central_cap import in_cap_box,bounded_cap,ray_avoids_cap_boxes,safe_ray_directions
from blender_bridge.closed_skin import closed_skin_geometry


class CentralCapTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/central_cap_loops.json').read_text(encoding='utf-8'))

    def test_concave_chain_is_oriented_preserves_vertices_and_stays_protected(self):
        points=self.data['concave'];boundary=list(range(len(points)))
        triangles,center,box,metrics=bounded_cap(points,boundary)
        self.assertEqual(len(triangles),len(points));self.assertEqual(metrics['method'],'BOUNDED_ORIENTED_FAN_CHAIN')
        all_points=points+[center]
        edges=Counter(edge for t in triangles for edge in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])))
        for a,b in zip(boundary,boundary[1:]+boundary[:1]):
            self.assertEqual(edges[(b,a)],1);self.assertEqual(edges[(a,b)],0)
        area=0.
        for a,b,c in triangles:
            x,y,z=(all_points[i] for i in (a,b,c));signed=((y[0]-x[0])*(z[1]-x[1])-(y[1]-x[1])*(z[0]-x[0]))/2
            area-=signed
            self.assertTrue(all(in_cap_box(all_points[i],box,0.) for i in (a,b,c)))
        self.assertEqual(area,7.)

    def test_original_cube_open_face_closes_with_positive_volume(self):
        data=json.loads((Path(__file__).parent/'fixtures/closed_skin_cube.json').read_text(encoding='utf-8'))
        points,faces=data['points'],data['triangles'];opened=faces[:2]+faces[4:]
        # Actual body-directed boundary around the missing top face.
        cap,center,box,_=bounded_cap(points,[4,7,6,5])
        diagonal,volume=closed_skin_geometry(points+[center],opened+cap)
        self.assertAlmostEqual(volume,1.);self.assertGreater(diagonal,1.)
        self.assertTrue(in_cap_box((.5,.5,1.),box,0.));self.assertFalse(in_cap_box((.5,.5,.5),box,.01))

    def test_nonplanarity_is_measured_and_coordinates_are_not_flattened(self):
        points=self.data['nonplanar'];copy=[p[:] for p in points]
        triangles,center,box,metrics=bounded_cap(points,list(range(4)))
        self.assertEqual(points,copy);self.assertEqual(len(triangles),4);self.assertTrue(in_cap_box(center,box,0.))
        self.assertEqual(box,((0.,0.,-.1),(1.,1.,.2)))

    def test_collinear_boundary_vertices_are_preserved(self):
        points=self.data['collinear'];triangles,center,box,_=bounded_cap(points,list(range(len(points))))
        self.assertEqual(len(triangles),5);self.assertEqual({v for t in triangles for v in t},set(range(6)))

    def test_repeated_nonfinite_and_degenerate_boundaries_reject(self):
        for points,boundary in (([[0.,0.,0.]]*3,[0,1,2]),
            (self.data['concave'],[0,1,2,1]),(self.data['concave'],[0,1,True]),
            ([[float('nan'),0.,0.],[1.,0.,0.],[0.,1.,0.]],[0,1,2])):
            with self.subTest(boundary=boundary),self.assertRaises(ValueError):bounded_cap(points,boundary)

    def test_all_closure_points_remain_protected_with_explicit_margin(self):
        _,_,box,_=bounded_cap(self.data['nonplanar'],list(range(4)))
        self.assertTrue(in_cap_box((.5,.5,.201),box,.002));self.assertFalse(in_cap_box((.5,.5,.201),box,0.))
        for margin in (-1.,True,float('nan')):
            with self.assertRaises(ValueError):in_cap_box((0.,0.,0.),box,margin)

    def test_bounded_chain_keeps_every_added_point_inside_mandatory_unknown_box(self):
        points=self.data['crossed'];boundary=list(range(len(points)))
        faces,center,box,metrics=bounded_cap(points,boundary)
        self.assertEqual(metrics['method'],'BOUNDED_ORIENTED_FAN_CHAIN');self.assertEqual(len(faces),len(boundary))
        self.assertTrue(in_cap_box(center,box,0.));all_points=points+[center]
        edges=Counter(edge for t in faces for edge in ((t[0],t[1]),(t[1],t[2]),(t[2],t[0])))
        for a,b in zip(boundary,boundary[1:]+boundary[:1]):self.assertEqual(edges[(b,a)],1)
        for face in faces:
            for i in face:self.assertTrue(in_cap_box(all_points[i],box,0.))

    def test_different_closures_agree_outside_box_and_can_disagree_inside_it(self):
        data=json.loads((Path(__file__).parent/'fixtures/closed_skin_cube.json').read_text(encoding='utf-8'))
        points=data['points'];body=data['triangles'][:2]+data['triangles'][4:]
        for index,z in ((4,.7),(5,1.2),(6,.8),(7,1.3)):points[index][2]=z
        a=body+[[4,5,6],[4,6,7]];b=body+[[4,5,7],[5,6,7]];box=((0.,0.,.7),(1.,1.,1.3))
        def winding(query,faces):
            total=0.
            for face in faces:
                x,y,z=[tuple(points[v][i]-query[i] for i in range(3)) for v in face]
                dot=lambda u,v:sum(s*t for s,t in zip(u,v))
                cross=(y[1]*z[2]-y[2]*z[1],y[2]*z[0]-y[0]*z[2],y[0]*z[1]-y[1]*z[0])
                lx,ly,lz=map(lambda v:math.hypot(*v),(x,y,z))
                total+=2*math.atan2(dot(x,cross),lx*ly*lz+dot(x,y)*lz+dot(y,z)*lx+dot(z,x)*ly)
            return total/(4*math.pi)
        for q,expected in (((.5,.5,.4),1.),((.5,.5,2.),0.),((2.,.5,1.),0.)):
            self.assertFalse(in_cap_box(q,box,0.));self.assertAlmostEqual(winding(q,a),expected);self.assertAlmostEqual(winding(q,b),expected)
        query=(.5,.5,1.);self.assertTrue(in_cap_box(query,box,0.))
        self.assertAlmostEqual(winding(query,a),0.);self.assertAlmostEqual(winding(query,b),1.)

    def test_chain_fallback_does_not_swallow_invalid_coordinates_or_indices(self):
        for p,loop in ((self.data['concave'],[0,0,1]),(self.data['concave'],[0,1,False]),
                       ([[float('nan'),0.,0.],[1.,0.,0.],[0.,1.,0.]],[0,1,2])):
            with self.assertRaises(ValueError):bounded_cap(p,loop)

    def test_uncertainty_test_rejects_nonfinite_boolean_and_inverted_bounds(self):
        box=((0.,0.,0.),(1.,1.,1.))
        for point,bounds in (((float('nan'),0.,0.),box),((True,0.,0.),box),((0.,0.,0.),tuple(reversed(box)))):
            with self.assertRaises(ValueError):in_cap_box(point,bounds,0.)

    def test_cancellation_propagates_through_projection_and_chain_fallback(self):
        def cancel():raise RuntimeError('cancelled')
        for key in ('concave','crossed'):
            points=self.data[key]
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'cancelled'):
                bounded_cap(points,list(range(len(points))),cancel_check=cancel)

    def test_rays_exclude_protected_boxes_including_grazing_and_margin(self):
        boxes=[((0.,0.,0.),(1.,1.,1.))]
        self.assertFalse(ray_avoids_cap_boxes((-1.,.5,.5),(1.,0.,0.),boxes,5.,0.))
        self.assertTrue(ray_avoids_cap_boxes((-1.,.5,.5),(-1.,0.,0.),boxes,5.,0.))
        self.assertTrue(ray_avoids_cap_boxes((-1.,2.,.5),(1.,0.,0.),boxes,5.,0.))
        self.assertFalse(ray_avoids_cap_boxes((-1.,1.,.5),(1.,0.,0.),boxes,5.,0.))
        self.assertTrue(ray_avoids_cap_boxes((-1.,.5,.5),(1.,0.,0.),boxes,.5,0.))
        self.assertFalse(ray_avoids_cap_boxes((-1.,1.05,.5),(1.,0.,0.),boxes,5.,.1))
        for direction in ((0.,0.,0.),(True,0.,0.),(float('nan'),0.,0.),(2.,0.,0.)):
            with self.assertRaises(ValueError):ray_avoids_cap_boxes((-1.,0.,0.),direction,boxes,5.,0.)

    def test_direction_selection_uses_three_cap_free_rays_or_no_verdict(self):
        boxes=[((0.,0.,0.),(1.,1.,1.))];point=(-1.,1.5,.5)
        directions=safe_ray_directions(point,boxes,2.);self.assertEqual(len(directions),3)
        for direction in directions:self.assertTrue(ray_avoids_cap_boxes(point,direction,boxes,8.,2e-5))
        self.assertEqual(safe_ray_directions((.5,.5,.5),boxes,2.),())
        for scale in (True,0.,float('nan')):
            with self.assertRaises(ValueError):safe_ray_directions(point,boxes,scale)
