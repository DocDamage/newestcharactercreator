"""Nonshipping geometry primitives; actual MPFB evidence is a separate gate."""
import json
import math
from pathlib import Path
import unittest

from blender_bridge.closed_skin import closed_skin_geometry
from blender_bridge.skin_winding import signed_ray,consistent_winding,DIRECTIONS,MAX_RAY_HITS


def cube():
    data=json.loads((Path(__file__).parent/'fixtures/closed_skin_cube.json').read_text(encoding='utf-8'))
    return data['points'],data['triangles']


def boxes_ray(boxes):
    """Independent analytic ray/box boundaries, including overlapping solids."""
    def cast(origin,direction,remaining):
        hits=[]
        for low,high in boxes:
            for axis in range(3):
                for value,sign in ((low[axis],-1),(high[axis],1)):
                    if abs(direction[axis])<1e-15:continue
                    distance=(value-origin[axis])/direction[axis]
                    if distance<=0 or distance>remaining:continue
                    hit=tuple(origin[i]+distance*direction[i] for i in range(3))
                    if all(low[i]-1e-12<=hit[i]<=high[i]+1e-12 for i in range(3)):
                        normal=tuple(sign if i==axis else 0 for i in range(3));hits.append((distance,hit,normal))
        if not hits:return None,None,None,None
        distance,hit,normal=min(hits)
        return hit,normal,0,distance
    return cast


class ClosedSkinTests(unittest.TestCase):
    def test_actual_geometry_prerequisites_scale_and_translation(self):
        points,faces=cube()
        for scale,offset in ((1.,0.),(.001,100.),(5.,-200.)):
            with self.subTest(scale=scale):
                diagonal,volume=closed_skin_geometry([[v*scale+offset for v in p] for p in points],faces)
                self.assertAlmostEqual(diagonal,math.sqrt(3)*scale,places=10)
                self.assertAlmostEqual(volume,scale**3,delta=scale**3*1e-8)

    def test_open_inverted_duplicate_degenerate_and_disconnected_reject(self):
        p,f=cube()
        invalid=[(p,f[:-1]),(p,[list(reversed(t)) for t in f]),(p,f+[f[0]]),
                 (p,f+[[0,0,1]]),(p+[[v+3 for v in x] for x in p],f+[[v+8 for v in t] for t in f]),
                 (p,[[*f[0][:2],True]]+f[1:]),([[float('nan'),0.,0.]]+p[1:],f)]
        for points,faces in invalid:
            with self.subTest(faces=len(faces)),self.assertRaises(ValueError):closed_skin_geometry(points,faces)

    def test_pinched_closed_shells_cannot_hide_behind_edge_counts(self):
        p,f=cube();other=[[v-1 for v in x] for x in p]
        # Two closed cubes share one vertex (first cube 0, second cube 6).
        remap={6:0};points=list(p)
        for i,point in enumerate(other):
            if i!=6:remap[i]=len(points);points.append(point)
        faces=f+[[remap[v] for v in t] for t in f]
        with self.assertRaisesRegex(ValueError,'NONMANIFOLD_VERTEX'):closed_skin_geometry(points,faces)

    def test_topology_cancellation_is_propagated(self):
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):closed_skin_geometry(*cube(),cancel_check=cancel)


class SkinWindingTests(unittest.TestCase):
    def counts(self,point,boxes):
        return [signed_ray(boxes_ray(boxes),point,tuple(v/math.hypot(*d) for v in d),4.,1e-6) for d in DIRECTIONS]

    def test_inside_without_any_surface_crossing_is_nonzero(self):
        box=[((0.,0.,0.),(1.,1.,1.))]
        self.assertEqual(self.counts((.41,.47,.53),box),[1,1,1])
        self.assertEqual(consistent_winding(self.counts((.41,.47,.53),box)),'NONZERO')
        self.assertEqual(consistent_winding(self.counts((2.,2.,2.),box)),'ZERO')

    def test_overlap_is_two_not_even_parity_false_clear(self):
        boxes=[((0.,0.,0.),(1.,1.,1.)),((.2,.2,.2),(1.2,1.2,1.2))]
        self.assertEqual(self.counts((.41,.47,.53),boxes),[2,2,2])
        self.assertEqual(consistent_winding([2,2,2]),'NONZERO')

    def test_disagreement_missing_boolean_and_partial_never_clear(self):
        for counts in ([0,1,0],[0,None,0],[False,0,0],[0,0],[]):
            with self.subTest(counts=counts):self.assertEqual(consistent_winding(counts),'AMBIGUOUS')

    def test_ray_near_hit_grazing_nonfinite_and_limit_are_unknown(self):
        for normal,distance in (((1.,0.,0.),0.),((0.,1.,0.),.1),((float('nan'),0.,0.),.1)):
            ray=lambda *args:((.1,0.,0.),normal,0,distance)
            self.assertIsNone(signed_ray(ray,(0.,0.,0.),(1.,0.,0.),1.,1e-6))
        count=0
        def ray(origin,*args):
            nonlocal count
            count+=1
            return (origin[0]+.001,0.,0.),(1.,0.,0.),0,.001
        self.assertIsNone(signed_ray(ray,(0.,0.,0.),(1.,0.,0.),1.,1e-6))
        self.assertEqual(count,MAX_RAY_HITS)

    def test_ray_work_budget_or_cancellation_propagates(self):
        def cancel():raise RuntimeError('budget or cancel')
        with self.assertRaisesRegex(RuntimeError,'budget or cancel'):
            signed_ray(boxes_ray([]),(0.,0.,0.),(1.,0.,0.),1.,1e-6,consume=cancel)
