"""Nonshipping index-only fixture; never an engine/MPFB character or proof."""
from ucc.export.unity_topology import UnityQuadSource


def topology():
    return UnityQuadSource('a'*64,'b'*64,6,(0,1,2,3,4,5,0,1),((0,1,2,3),(3,2,4,5)),
                           tuple('UNIT_TEST_BONE_'+str(i) for i in range(163)),
                           tuple('UCC_EXPR_V1_UNIT_TEST_'+str(i) for i in range(12)))


def excessive_valence_arguments():
    # A ring of indices only; it has no vertex coordinates or shipping geometry.
    return {'source_vertices':67,'native_source':tuple(range(67)),
            'quads':tuple((0,1+i,34+i,1+(i+1)%33) for i in range(33))}
