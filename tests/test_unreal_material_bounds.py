"""Generated scalar/material metadata cases, never rendered engine proof."""
import unittest
from fixtures.unreal_bind_evidence import fixture_data,graph
from ucc.core.errors import ValidationError
from ucc.export.unreal_native_data import decode_native
from ucc.export.unreal_material_bounds import verify_material,verify_bounds,verify_graph


class UnrealMaterialBoundsTests(unittest.TestCase):
    def setUp(self):
        self.source,_,raw,_=fixture_data();self.native=decode_native(raw);self.slot=self.source['source_material_name']

    def test_source_material_scalars_and_slot(self):
        self.assertTrue(verify_material(self.source,self.native,self.slot,self.slot)['source_material_scalars_float32_exact'])

    def test_slot_expectation_cannot_be_chosen_from_wrong_native_output(self):
        self.native['readback']['materials'][0]['slot_name']='Wrong'
        with self.assertRaises(ValidationError):verify_material(self.source,self.native,'Wrong',self.slot)

    def test_wrong_srgb_linear_conversion_rejected(self):
        self.native['readback']['materials'][0]['base_color_linear_rgba']=[.5,.5,.5,1]
        with self.assertRaises(ValidationError):verify_material(self.source,self.native,self.slot,self.slot)

    def test_point_tight_imported_and_box_diagonal_extended_spheres(self):
        bounds=self.native['readback']['bounds']
        self.assertNotEqual(bounds['sphere_radius_cm'],bounds['imported_sphere_radius_cm'])
        self.assertTrue(verify_bounds(self.source,self.native)['source_derived_centimeter_bounds_verified'])

    def test_imported_sphere_forged_as_diagonal_rejected(self):
        bounds=self.native['readback']['bounds'];bounds['imported_sphere_radius_cm']=bounds['sphere_radius_cm']
        with self.assertRaises(ValidationError):verify_bounds(self.source,self.native)

    def test_extended_sphere_forged_as_tight_rejected(self):
        bounds=self.native['readback']['bounds'];bounds['sphere_radius_cm']=bounds['imported_sphere_radius_cm']
        with self.assertRaises(ValidationError):verify_bounds(self.source,self.native)

    def test_extra_bounds_extension_or_nanite_rejected(self):
        self.native['readback']['bounds']['positive_extension_cm']=[1,0,0]
        with self.assertRaises(ValidationError):verify_bounds(self.source,self.native)

    def test_direct_graph_inputs_checked_beyond_parameter_presence(self):
        stage=graph();fresh=graph();self.assertTrue(verify_graph(stage,fresh)['direct_parameter_property_inputs_exact'])
        stage['property_inputs']['MP_BASE_COLOR']['parameter_name']='UnusedParameter'
        fresh['property_inputs']['MP_BASE_COLOR']['parameter_name']='UnusedParameter'
        with self.assertRaises(ValidationError):verify_graph(stage,fresh)


if __name__=='__main__':unittest.main()
