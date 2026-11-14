"""Bounded static buffers only; these tests do not establish actual GPU drawing."""
from dataclasses import replace
import struct
import unittest

from fixtures.static_face_contract import unit_triangle
from ucc.core.errors import ValidationError
from ucc.preview.static_surface import from_full_mesh


class StaticFaceSurfaceTests(unittest.TestCase):
    def test_preserves_all_triangles_and_converts_known_up_axis(self):
        mesh = unit_triangle()
        surface = from_full_mesh(mesh)
        vertices, indices = surface.frame(0)
        self.assertEqual(tuple(struct.iter_unpack('<3f', vertices)), ((0., 0., 0.), (1., 0., 0.), (.5, -1., 2.)))
        self.assertEqual(struct.unpack('<3I', indices), (0, 1, 2))
        self.assertEqual(surface.triangle_count, mesh.source_face_count)
        self.assertEqual(surface.focused().frame(0), (vertices, indices))
        self.assertIsNone(surface.surface_review)

    def test_sampled_oversized_or_nonfinite_geometry_cannot_be_full_preview(self):
        mesh = unit_triangle()
        for invalid in (replace(mesh, source_face_count=2), replace(mesh, source_face_count=100001),
                        replace(mesh, triangles=(((float('nan'), 0., 0.), (1., 0., 0.), (0., 2., 1.)),))):
            with self.assertRaises(ValidationError):
                from_full_mesh(invalid)

    def test_static_buffer_rejects_animation_indices_and_boolean(self):
        surface = from_full_mesh(unit_triangle())
        for index in (1, -1, False, 0.):
            with self.assertRaises(ValidationError):
                surface.frame(index)


if __name__ == '__main__':
    unittest.main()
