"""Independent nonshipping exact-winding oracle; uses Blender-bundled NumPy."""


def solid_angle_values(points,triangles,queries):
    """Independent double-precision reference on arbitrary measured query points."""
    import numpy as np
    faces=np.asarray(points,dtype=np.float64)[np.asarray(triangles)];values=[]
    for point in queries:
        q=faces-np.asarray(point,dtype=np.float64);a,b,c=q[:,0],q[:,1],q[:,2]
        la,lb,lc=(np.linalg.norm(v,axis=1) for v in (a,b,c))
        numerator=np.einsum('ij,ij->i',a,np.cross(b,c))
        denominator=la*lb*lc+np.einsum('ij,ij->i',a,b)*lc+np.einsum('ij,ij->i',b,c)*la+np.einsum('ij,ij->i',c,a)*lb
        values.append(float(np.arctan2(numerator,denominator).sum()/(2*np.pi)))
    return values


def compare_solid_angles(points,triangles,observation):
    import numpy as np
    from mathutils import Vector
    faces=np.asarray([tuple(p) for p in points],dtype=np.float64)[np.asarray(triangles)]
    expected=set();noninteger=[]
    for face in observation['right']['selected_triangles']:
        a,b,c=(Vector(points[v]) for v in triangles[face]);normal=(b-a).cross(c-a).normalized()
        point=(a+b+c)/3+normal*observation['offset_world'];q=faces-np.asarray(tuple(point))
        a,b,c=q[:,0],q[:,1],q[:,2];la,lb,lc=(np.linalg.norm(v,axis=1) for v in (a,b,c))
        numerator=np.einsum('ij,ij->i',a,np.cross(b,c))
        denominator=la*lb*lc+np.einsum('ij,ij->i',a,b)*lc+np.einsum('ij,ij->i',b,c)*la+np.einsum('ij,ij->i',c,a)*lb
        winding=float(np.arctan2(numerator,denominator).sum()/(2*np.pi))
        if not np.isfinite(winding) or abs(winding-round(winding))>1e-5:noninteger.append(face)
        elif round(winding)!=0:expected.add(face)
    observed=set(observation['right']['nonzero_triangles']);unknown=set(observation['right']['ambiguous_triangles'])
    return {'expected_nonzero':len(expected),'observed_nonzero':len(observed),'ambiguous':len(unknown),'noninteger':len(noninteger),
        'false_zero':len(expected-observed-unknown),'false_nonzero':len(observed-expected),'numpy_version':np.__version__}
