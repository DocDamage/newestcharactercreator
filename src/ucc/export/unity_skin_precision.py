"""Versioned bounded native-weight transfer; no Unity/Blender/runtime imports."""
from dataclasses import dataclass
from collections.abc import Mapping
import math
from ucc.core.errors import ValidationError

POLICY='UCC_UNITY_NATIVE_UNORM16_BOUNDED_V1'
QUANTIZATION_STEP=1/65535
FLOAT32_EPSILON=2**-23
UNIT_SUM_TOLERANCE=1e-6
ARITHMETIC_POSITION_BOUND_M=1e-6
MAX_DEFORMATION_ERROR_M=50e-6


def _row(value: tuple[tuple[str,float],...]) -> dict[str,float]:
    if (type(value) is not tuple or not 1<=len(value)<=8 or any(type(p) is not tuple or len(p)!=2 for p in value)):
        raise ValidationError('Unity skin needs one to eight explicit named influences')
    result={}
    for name,weight in value:
        if (type(name) is not str or not name or len(name)>128 or name in result or any(ord(c)<32 for c in name)
                or type(weight) not in (int,float) or not math.isfinite(weight) or not 0<weight<=1):
            raise ValidationError('Unity skin has duplicate, missing or invalid positive bone weights')
        result[name]=float(weight)
    if abs(math.fsum(result.values())-1)>UNIT_SUM_TOLERANCE:raise ValidationError('Unity source and native weights must each sum to one')
    return result


@dataclass(frozen=True,slots=True)
class NativeWeightEvidence:
    policy: str
    influences: int
    maximum_error: float
    absolute_error_sum: float
    absolute_error_bound: float


def validate_native_weights(source: tuple[tuple[str,float],...],actual: tuple[tuple[str,float],...]) -> NativeWeightEvidence:
    """Bound quantization plus unit-sum redistribution without guessing packing.

    A full UNORM16 step per source influence is the conservative total budget;
    float32 input/readback has a separate allowance. This does not assert an
    undocumented Unity packing order or grant geometric/animation acceptance.
    Every positive source bone must survive. Posed surfaces need their own gate.
    """
    expected=_row(source);observed=_row(actual)
    if set(expected)!=set(observed):raise ValidationError('Unity skin lost or reassigned an original positive influence')
    errors=[abs(observed[name]-weight) for name,weight in expected.items()]
    bound=len(expected)*QUANTIZATION_STEP+16*FLOAT32_EPSILON
    total=math.fsum(errors)
    if total>bound:raise ValidationError('Unity skin error exceeds the versioned native storage budget')
    return NativeWeightEvidence(POLICY,len(expected),max(errors),total,bound)


def deformation_error_bound(source: tuple[tuple[str,float],...],actual: tuple[tuple[str,float],...],
        transformed_points: Mapping[str,tuple[float,float,float]]) -> float:
    """Position bound from actual weight errors and original posed bone points.

    Centering at one bone's point cancels common root translation. Retain the
    actual unit-sum rounding term and a distinct arithmetic bound. Bone-matrix
    transfer and native evaluation errors are separate terms, not weight error;
    callers must account for those before admitting actual engine deformation.
    """
    validate_native_weights(source,actual);expected=_row(source);observed=_row(actual)
    if not isinstance(transformed_points,Mapping) or set(transformed_points)!=set(expected):raise ValidationError('Incomplete original posed bone-point coverage')
    for p in transformed_points.values():
        if type(p) is not tuple or len(p)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p):
            raise ValidationError('Nonfinite or malformed original posed skin point')
    anchor=transformed_points[sorted(expected)[0]]
    differences={name:observed[name]-weight for name,weight in expected.items()}
    bound=math.fsum(abs(differences[name])*math.dist(point,anchor) for name,point in transformed_points.items())
    bound+=abs(math.fsum(differences.values()))*math.dist(anchor,(0.,0.,0.))
    return bound+ARITHMETIC_POSITION_BOUND_M


def validate_deformation_error(observed_error_m: float,weight_bound_m: float) -> None:
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (observed_error_m,weight_bound_m)):
        raise ValidationError('Invalid Unity deformation error/bound')
    if observed_error_m>MAX_DEFORMATION_ERROR_M or observed_error_m>weight_bound_m:
        raise ValidationError('Unity deformation exceeds source-derived precision or spatial quality bounds')
