"""Transient memory, global face identity and cancellation boundary tests."""
import unittest

from blender_bridge.central_self import require_body_surface
from fixtures.central_self_contract import tree_contract,disjoint_triangles


class CentralSelfTests(unittest.TestCase):
    def test_complete_chunked_scope_remains_explicit_and_unapproved(self):
        points,faces=disjoint_triangles();tree=tree_contract({(i,i) for i in range(4)})
        result=require_body_surface(points,faces,tree,transient_limit=4)
        self.assertEqual(result['chunk_queries'],4);self.assertEqual(result['candidate_pairs'],4)
        self.assertEqual(result['nonadjacent_pairs'],0);self.assertFalse(result['adjacent_fold_quality_verified'])

    def test_nonzero_chunk_offset_still_detects_actual_global_pair(self):
        points,faces=disjoint_triangles();tree=tree_contract({(i,i) for i in range(4)}|{(2,3),(3,2)})
        with self.assertRaisesRegex(ValueError,'NONADJACENT_SELF_INTERSECTION'):
            require_body_surface(points,faces,tree,transient_limit=4)

    def test_shared_vertex_contact_is_not_mislabeled_as_nonadjacent(self):
        points,faces=disjoint_triangles();faces[1]=(3,4,0)
        tree=tree_contract({(i,i) for i in range(4)}|{(0,1),(1,0)})
        self.assertEqual(require_body_surface(points,faces,tree,transient_limit=4)['nonadjacent_pairs'],0)

    def test_budget_and_cancellation_never_produce_partial_zero_verdict(self):
        points,faces=disjoint_triangles();tree=tree_contract({(i,i) for i in range(4)})
        with self.assertRaisesRegex(ValueError,'SELF_WORK_BUDGET'):
            require_body_surface(points,faces,tree,transient_limit=4,candidate_limit=2)
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            require_body_surface(points,faces,tree,cancel_check=cancel)
