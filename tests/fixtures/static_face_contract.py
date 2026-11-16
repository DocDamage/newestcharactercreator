"""Non-shipping triangle fixture for static buffer boundaries; not a character."""
from ucc.preview.glb_mesh import PreviewMesh


def unit_triangle():
    return PreviewMesh((((0., 0., 0.), (1., 0., 0.), (.5, 2., 1.)),),
                       ((0., 0., 0.), (1., 2., 1.)), 1, 0, 0, ('Unit-test geometry only',))
