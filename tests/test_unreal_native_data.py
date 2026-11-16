"""Closed V2 structure faults using generated nonshipping observations."""
import base64
import unittest
from fixtures.unreal_bind_evidence import fixture_data,packed
from ucc.core.errors import ValidationError
from ucc.export.unreal_native_data import decode_native


class UnrealNativeDataTests(unittest.TestCase):
    def setUp(self):self.raw=fixture_data()[2]

    def test_generated_native_buffers_and_raw_weights_agree(self):
        result=decode_native(self.raw)
        self.assertEqual(len(result['positions']),6)
        self.assertTrue(result['raw_weight_evidence']['native_raw_api_positive_weights_exact'])

    def test_unverified_claim_flags_are_closed(self):
        self.raw['source_parity_verified']=True
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_expected_source_injection_is_not_a_native_field(self):
        self.raw['readback']['expected_source_positions']=[]
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_nonfinite_native_component_rejected(self):
        self.raw['readback']['positions']=packed([(float('nan'),0,0)]*6,'fff','float32x3_le')
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_noncanonical_or_invalid_base64_rejected(self):
        self.raw['readback']['positions']['base64']='!'*96
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_boolean_count_rejected(self):
        self.raw['readback']['positions']['count']=True
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_native8bit_weights_rejected(self):
        self.raw['readback']['native_weight_storage_bytes']=1
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_full_uv_precision_required(self):
        self.raw['readback']['native_uv_storage_full_precision']=False
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_raw_weight_byte_disagrees_with_api(self):
        value=self.raw['readback']['native_weight_data'];raw=bytearray(base64.b64decode(value['base64']));raw[2]^=1
        value['base64']=base64.b64encode(raw).decode()
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_stride_and_section_coverage_are_validated(self):
        self.raw['readback']['native_constant_influences_stride']+=1
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_bone_cycle_rejected(self):
        self.raw['readback']['bones'][0]['parent']=0
        with self.assertRaises(ValidationError):decode_native(self.raw)

    def test_aggregate_morph_domain_rejected_before_buffer_allocation(self):
        self.raw['readback']['morphs'][0]['deltas']['count']=2000001
        with self.assertRaises(ValidationError):decode_native(self.raw)


if __name__=='__main__':unittest.main()
