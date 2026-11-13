"""Invented mesh metadata tests static-face failure states, not real geometry."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blender_bridge.body_contact_areas import AreaInspector


class BodyAreaWorkerTests(unittest.TestCase):
    def inspector(self):
        inspector=AreaInspector.__new__(AreaInspector)
        inspector.polygons=None;inspector.polygon_sha=None;inspector.area_reason=''
        return inspector

    def test_each_frame_must_reproduce_the_complete_ordered_polygon_vertices(self):
        inspector=self.inspector()
        def mesh(vertices):return SimpleNamespace(polygons=[SimpleNamespace(vertices=vertices)],loops=[0]*4)
        with patch('blender_bridge.body_contact_areas.BodyContactInspector.inspect'):
            inspector.inspect(mesh((0,1,2,3)),1,'a'*64,'b'*64)
            original=inspector.polygon_sha;self.assertEqual(inspector.polygons,[[0,1,2,3]])
            inspector.inspect(mesh((0,1,2,3)),2,'a'*64,'c'*64)
            self.assertEqual(inspector.polygon_sha,original);self.assertEqual(inspector.area_reason,'')
            inspector.inspect(mesh((0,3,2,1)),3,'a'*64,'d'*64)
            self.assertEqual(inspector.area_reason,'POLYGON_TOPOLOGY_CHANGED')
            self.assertEqual(inspector.polygon_sha,original)

    def test_face_and_loop_budgets_stop_before_allocating_excessive_polygon_data(self):
        class SizedOnly:
            def __init__(self,size):self.size=size
            def __len__(self):return self.size
            def __iter__(self):raise AssertionError('Excessive mesh was iterated before its budget check')
        for polygons,loops in ((100001,1),(1,1000001)):
            inspector=self.inspector();mesh=SimpleNamespace(polygons=SizedOnly(polygons),loops=SizedOnly(loops))
            with patch('blender_bridge.body_contact_areas.BodyContactInspector.inspect'):
                inspector.inspect(mesh,1,'a'*64,'b'*64)
            self.assertEqual(inspector.area_reason,'POLYGON_BUDGET_EXCEEDED');self.assertIsNone(inspector.polygons)


if __name__=='__main__':unittest.main()
