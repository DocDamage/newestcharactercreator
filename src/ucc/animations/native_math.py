"""Independent small matrix checks for native retarget evidence (no bpy/Qt)."""
import math
from ucc.core.errors import ValidationError
from ucc.animations.fbx_snapshot import _matrix


def product(a,b):
    n=len(a)
    return [[sum(a[i][k]*b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]


def transposed(a): return [list(v) for v in zip(*a)]


def rows(values): return [values[i:i+4] for i in range(0,16,4)]


def scale(matrix):
    values=[sum(matrix[i][j]**2 for i in range(3))**.5 for j in range(3)]
    if min(values)<1e-7 or max(values)/min(values)>1.0001:
        raise ValidationError("Unsupported native source scale")
    return sum(values)/3


def inverse(matrix):
    a,b,c=matrix[0][:3],matrix[1][:3],matrix[2][:3]
    cof=[[b[1]*c[2]-b[2]*c[1],a[2]*c[1]-a[1]*c[2],a[1]*b[2]-a[2]*b[1]],
         [b[2]*c[0]-b[0]*c[2],a[0]*c[2]-a[2]*c[0],a[2]*b[0]-a[0]*b[2]],
         [b[0]*c[1]-b[1]*c[0],a[1]*c[0]-a[0]*c[1],a[0]*b[1]-a[1]*b[0]]]
    det=sum(matrix[0][i]*cof[i][0] for i in range(3))
    if not math.isfinite(det) or abs(det)<1e-12:raise ValidationError("Singular native parent transform")
    result=[[v/det for v in row]+[0.] for row in cof]+[[0.,0.,0.,1.]]
    for i in range(3):result[i][3]=-sum(result[i][j]*matrix[j][3] for j in range(3))
    return result


def rotation(value, *, target_noise=False):
    if target_noise:
        if (type(value) is not list or len(value)!=16 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in value) or
                max(abs(value[12+i]-(1 if i==3 else 0)) for i in range(4))>1e-6):
            raise ValidationError("Invalid affine target pose evidence")
    else:_matrix(value)
    cols=[[value[r*4+c] for r in range(3)] for c in range(3)]
    scales=[sum(v*v for v in c)**.5 for c in cols]
    if min(scales)<1e-7 or max(scales)>1e4 or max(scales)/min(scales)>1.0001: raise ValidationError("Native rotation has nonuniform/degenerate scale")
    cols=[[v/scales[i] for v in c] for i,c in enumerate(cols)]
    original=transposed(cols)
    if target_noise:
        x=cols[0]
        dot=sum(a*b for a,b in zip(x,cols[1]))
        y=[cols[1][i]-dot*x[i] for i in range(3)]
        length=sum(v*v for v in y)**.5
        if length<1e-7: raise ValidationError("Target numeric rotation axes are degenerate")
        y=[v/length for v in y]
        z=[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
        result=transposed([x,y,z])
        correction=max(abs(original[i][j]-result[i][j]) for i in range(3) for j in range(3))
        if correction>5e-4: raise ValidationError("Target numeric rotation correction exceeds measured noise bound")
    else: result,correction=original,0.
    check_rotation(result)
    return result,correction


def check_rotation(a):
    if (type(a) is not list or len(a)!=3 or any(type(r) is not list or len(r)!=3 for r in a) or
            any(type(x) not in (int,float) or not math.isfinite(x) for r in a for x in r)):
        raise ValidationError("Invalid native rotation evidence")
    check=product(transposed(a),a)
    det=a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])-a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])+a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0])
    if abs(det-1)>1e-5 or max(abs(check[i][j]-(i==j)) for i in range(3) for j in range(3))>1e-5:
        raise ValidationError("Native rotation evidence is reflected/scaled/sheared")


def global_pose(source_bind,source_pose,axes,reference):
    return product(product(product(product(axes,source_pose),transposed(source_bind)),transposed(axes)),reference)


def point(matrix,vector):
    return [sum(matrix[i][j]*vector[j] for j in range(3))+matrix[i][3] for i in range(3)]


def unit(vector):
    if len(vector)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):
        raise ValidationError("Invalid anatomical evidence vector")
    length=sum(v*v for v in vector)**.5
    if not 1e-7<length<1e6: raise ValidationError("Degenerate anatomical evidence vector")
    return [v/length for v in vector]


def anatomy(direction,secondary):
    y,z=unit(direction),unit(secondary)
    dot=sum(a*b for a,b in zip(y,z))
    if abs(dot)>.985: raise ValidationError("Parallel anatomical evidence axes")
    z=unit([z[i]-dot*y[i] for i in range(3)])
    x=[y[1]*z[2]-y[2]*z[1],y[2]*z[0]-y[0]*z[2],y[0]*z[1]-y[1]*z[0]]
    return transposed([x,y,z])


def body(left,right,head):
    delta=[head[i]-(left[i]+right[i])/2 for i in range(3)]
    height=sum(v*v for v in delta)**.5
    if not .1<height<10: raise ValidationError("Invalid anatomical body height")
    z=unit(delta);across=[left[i]-right[i] for i in range(3)]
    dot=sum(a*b for a,b in zip(z,across))
    x=unit([across[i]-dot*z[i] for i in range(3)])
    y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]]
    return transposed([x,unit(y),z]),height
