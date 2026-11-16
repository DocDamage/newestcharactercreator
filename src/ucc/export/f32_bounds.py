"""Outward bounds for declared binary32 operations, independent of any engine.

These describe an arithmetic contract. An opaque runtime still has to be
measured against the bounds; importing this module does not certify its path.
"""
from dataclasses import dataclass
import math
from collections.abc import Sequence
from ucc.core.errors import ValidationError

UNIT_ROUNDOFF = 2.0**-24
HALF_MIN_SUBNORMAL = 2.0**-150
MAX_FINITE = float.fromhex('0x1.fffffep127')
POLICY = 'UCC_BINARY32_RN_OUTWARD_OPERATIONS_V1'


def _finite(value: float) -> bool:
    # Compare integer magnitude before converting it to a platform float.
    return type(value) in (int, float) and abs(value) <= MAX_FINITE and math.isfinite(value)


def _down(value: float) -> float:
    return math.nextafter(value, -math.inf)


def _up(value: float) -> float:
    return math.nextafter(value, math.inf)


def gamma(operations: int) -> float:
    """Conservative n*u/(1-n*u), with binary64 evaluation rounded outward."""
    if type(operations) is not int or not 0 <= operations <= 4096:
        raise ValidationError('Invalid binary32 operation count')
    if operations == 0:
        return 0.0
    scaled = operations * UNIT_ROUNDOFF
    return _up(scaled / (1.0 - scaled))


@dataclass(frozen=True, slots=True)
class Bounds:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if any(not _finite(v) for v in (self.lower, self.upper)) or self.lower > self.upper:
            raise ValidationError('Nonfinite, reversed or malformed arithmetic bounds')

    @classmethod
    def exact(cls, value: float) -> 'Bounds':
        if not _finite(value):
            raise ValidationError('Invalid finite binary32 arithmetic operand')
        return cls(float(value), float(value))

    def contains(self, value: float) -> bool:
        if not _finite(value):
            raise ValidationError('Invalid observed arithmetic result')
        return self.lower <= value <= self.upper

    def maximum_distance(self, value: float) -> float:
        if not _finite(value):
            raise ValidationError('Invalid arithmetic reference result')
        return _up(max(abs(self.lower - value), abs(self.upper - value)))


def _check(value: Bounds) -> None:
    if type(value) is not Bounds:
        raise ValidationError('Arithmetic operand must carry explicit bounds')


def _rounded(value: Bounds, operations: int = 1, magnitude: float | None = None) -> Bounds:
    """Widen for RN rounding, including gradual underflow; reject overflow."""
    _check(value)
    maximum = max(abs(value.lower), abs(value.upper))
    if magnitude is None:
        magnitude = maximum
    error = _up(gamma(operations) * magnitude + operations * HALF_MIN_SUBNORMAL / (1 - operations * UNIT_ROUNDOFF))
    if not math.isfinite(magnitude) or magnitude + error > MAX_FINITE:
        # A cancellation-small final value does not make every intermediate safe.
        raise ValidationError('Declared binary32 intermediate may overflow')
    lower, upper = _down(value.lower - error), _up(value.upper + error)
    if not math.isfinite(lower) or not math.isfinite(upper) or max(abs(lower), abs(upper)) > MAX_FINITE:
        raise ValidationError('Declared binary32 arithmetic may overflow')
    return Bounds(lower, upper)


def add(left: Bounds, right: Bounds) -> Bounds:
    _check(left); _check(right)
    return _rounded(Bounds(_down(left.lower + right.lower), _up(left.upper + right.upper)))


def subtract(left: Bounds, right: Bounds) -> Bounds:
    _check(left); _check(right)
    return _rounded(Bounds(_down(left.lower - right.upper), _up(left.upper - right.lower)))


def _product(left: Bounds, right: Bounds) -> Bounds:
    _check(left); _check(right)
    products = [a * b for a in (left.lower, left.upper) for b in (right.lower, right.upper)]
    return Bounds(_down(min(products)), _up(max(products)))


def multiply(left: Bounds, right: Bounds) -> Bounds:
    return _rounded(_product(left, right))


def divide(left: Bounds, right: Bounds) -> Bounds:
    _check(left); _check(right)
    if right.lower <= 0 <= right.upper:
        raise ValidationError('Arithmetic divisor may be zero')
    quotients = [a / b for a in (left.lower, left.upper) for b in (right.lower, right.upper)]
    return _rounded(Bounds(_down(min(quotients)), _up(max(quotients))))


def rounded_sum(values: Sequence[Bounds]) -> Bounds:
    """Any ordering of n-1 binary32 additions, including cancellation."""
    if not isinstance(values, Sequence) or not 1 <= len(values) <= 512:
        raise ValidationError('Arithmetic sum needs one to 512 bounded terms')
    for value in values:
        _check(value)
    if len(values) == 1:
        return values[0]
    lower = upper = magnitude = 0.0
    for value in values:
        lower = _down(lower + value.lower); upper = _up(upper + value.upper)
        magnitude = _up(magnitude + max(abs(value.lower), abs(value.upper)))
    return _rounded(Bounds(lower, upper), len(values) - 1, magnitude)


def dot(left: Sequence[Bounds], right: Sequence[Bounds]) -> Bounds:
    """Any ordering/grouping of products and sums, including fused operations.

    n products and n-1 additions give at most 2*n-1 roundings. The absolute
    sum of products prevents a cancellation-small result from hiding error.
    """
    if not isinstance(left, Sequence) or not isinstance(right, Sequence) or len(left) != len(right) or not 1 <= len(left) <= 64:
        raise ValidationError('Arithmetic dot operands need equal bounded dimensions')
    lower = upper = magnitude = 0.0
    for a, b in zip(left, right):
        product = _product(a, b)
        lower = _down(lower + product.lower); upper = _up(upper + product.upper)
        magnitude = _up(magnitude + max(abs(product.lower), abs(product.upper)))
    return _rounded(Bounds(lower, upper), 2 * len(left) - 1, magnitude)


def affine(matrix: tuple[float, ...], point: tuple[Bounds, Bounds, Bounds]) -> tuple[Bounds, Bounds, Bounds]:
    """Declared 3D affine transform with finite row-major binary32 coefficients."""
    if type(matrix) is not tuple or len(matrix) != 16 or type(point) is not tuple or len(point) != 3:
        raise ValidationError('Arithmetic affine transform needs a matrix and bounded 3D point')
    coefficients = tuple(Bounds.exact(v) for v in matrix)
    if matrix[12:] != (0, 0, 0, 1):
        raise ValidationError('Arithmetic matrix must be affine')
    values = point + (Bounds.exact(1),)
    return tuple(dot(coefficients[r * 4:r * 4 + 4], values) for r in range(3))


def matrix_product(left: tuple[Bounds, ...], right: tuple[Bounds, ...]) -> tuple[Bounds, ...]:
    """Bound matrix formation as well as later multiplication by a point.

    Cancellation in a computed world coefficient needs its own error term;
    treating the already rounded world matrix as exact loses that term.
    """
    if type(left) is not tuple or type(right) is not tuple or len(left) != 16 or len(right) != 16:
        raise ValidationError('Arithmetic matrix product needs two bounded 4x4 matrices')
    return tuple(dot(left[r * 4:r * 4 + 4], tuple(right[k * 4 + c] for k in range(4)))
                 for r in range(4) for c in range(4))
