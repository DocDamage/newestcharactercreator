"""Arithmetic tests only; these scalar inputs are not model/engine evidence."""
import itertools
import math
import struct
import unittest
from ucc.core.errors import ValidationError
from ucc.export.f32_bounds import Bounds, add, subtract, multiply, divide, dot, affine, rounded_sum, gamma, MAX_FINITE, matrix_product


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class FloatBoundsTests(unittest.TestCase):
    def test_actual_binary32_operations_and_underflow_are_enclosed(self):
        values = [f32(v) for v in (0., 2**-149, -2**-149, .1, -.7, 2**24, -2**24)]
        for x, y in itertools.product(values, repeat=2):
            a, b = Bounds.exact(x), Bounds.exact(y)
            for op, exact in ((add, x+y), (subtract, x-y), (multiply, x*y)):
                self.assertTrue(op(a,b).contains(f32(exact)), (op.__name__,x,y))
            if y:
                if abs(x/y) > MAX_FINITE:
                    with self.assertRaises(ValidationError): divide(a,b)
                else:
                    self.assertTrue(divide(a,b).contains(f32(x/y)))

    def test_sum_and_dot_cover_all_orders_under_severe_cancellation(self):
        numbers = (2**24, 1., -2**24, -1.)
        bounds = rounded_sum(tuple(Bounds.exact(n) for n in numbers))
        product = dot(tuple(Bounds.exact(n) for n in numbers), (Bounds.exact(1),)*4)
        for order in itertools.permutations(numbers):
            total = 0.
            for n in order: total = f32(total+n)
            self.assertTrue(bounds.contains(total)); self.assertTrue(product.contains(total))
        self.assertGreater(bounds.upper-bounds.lower, 1.)

    def test_uncertain_inputs_propagate_through_affine_transform(self):
        matrix = (1.,2.,0.,.1, 0.,1.,0.,-.2, 0.,0.,-1.,.3, 0.,0.,0.,1.)
        point = (Bounds(-.01,.01), Bounds.exact(.4), Bounds.exact(-.5))
        result = affine(matrix,point)
        for x in (-.01,0.,.01):
            self.assertTrue(result[0].contains(f32(f32(x+f32(2*.4))+.1)))
        self.assertTrue(result[1].contains(f32(.4-.2)))
        self.assertTrue(result[2].contains(f32(.5+.3)))

    def test_division_zero_overflow_and_malformed_bounds_reject(self):
        for a,b in ((Bounds.exact(1),Bounds(-1,1)),(Bounds.exact(MAX_FINITE),Bounds.exact(2**-100))):
            with self.assertRaises(ValidationError): divide(a,b)
        for args in ((float('nan'),1),(2,1),(True,1)):
            with self.assertRaises(ValidationError): Bounds(*args)
        with self.assertRaises(ValidationError): multiply(Bounds.exact(MAX_FINITE),Bounds.exact(2))
        for count in (-1,True,4097):
            with self.assertRaises(ValidationError):gamma(count)
        self.assertEqual(gamma(0),0)

    def test_boundary_inputs_cannot_forge_an_arithmetic_pass(self):
        for bad in (True,float('nan'),float('inf'),'1',2**4096):
            with self.assertRaises(ValidationError):Bounds.exact(bad)
            with self.assertRaises(ValidationError):Bounds.exact(1).contains(bad)
        with self.assertRaises(ValidationError): rounded_sum(())
        with self.assertRaises(ValidationError): dot((Bounds.exact(1),),())
        with self.assertRaises(ValidationError): affine((0.,)*16,(Bounds.exact(1),)*3)
        b=Bounds(-1.,1.);self.assertGreaterEqual(b.maximum_distance(.25),1.25)

    def test_matrix_formation_encloses_cancellation_before_point_evaluation(self):
        c=f32(math.sqrt(.5))
        a=(c,-c,0.,0., c,c,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.)
        b=(c,c,0.,0., -c,c,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.)
        result=matrix_product(tuple(map(Bounds.exact,a)),tuple(map(Bounds.exact,b)))
        for r,c in itertools.product(range(4),repeat=2):
            products=[f32(a[r*4+k]*b[k*4+c]) for k in range(4)]
            for order in itertools.permutations(products):
                value=0.
                for p in order:value=f32(value+p)
                self.assertTrue(result[r*4+c].contains(value))
        self.assertLess(result[1].lower,0);self.assertGreater(result[1].upper,0)
        with self.assertRaises(ValidationError):matrix_product((),())

    def test_cancellation_cannot_hide_overflow_in_an_allowed_order(self):
        large=f32(MAX_FINITE*.75)
        terms=tuple(Bounds.exact(v) for v in (large,large,-large))
        with self.assertRaisesRegex(ValidationError,'overflow'):rounded_sum(terms)
        with self.assertRaisesRegex(ValidationError,'overflow'):dot(terms,(Bounds.exact(1),)*3)
