"""Tiny seam metadata fixture; never an engine/model/MPFB acceptance asset."""
POLYGONS=((0,1,2,3),(1,4,5,2))
UVS=((0.,0.),(.4,0.),(.4,1.),(0.,1.),(.6,0.),(1.,0.),(1.,1.),(.6,1.))
IDS=(0,1,2,3,1,4,5,2)
IMPORTED_UVS=tuple((u,1.-v) for u,v in UVS)
TRIANGLES=(0,1,2,0,2,3,4,5,6,4,6,7)
