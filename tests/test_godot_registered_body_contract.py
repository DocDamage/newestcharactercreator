"""Pure private execution selection boundaries, no kernel or engine invocation."""
from copy import deepcopy
from dataclasses import replace
import unittest
from fixtures.godot_registered_body_logic import execution_selection
from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_registered_body_runtime import RegisteredRuntimeExecutionSelection,FALSE_FLAGS


class RegisteredBodySelectionTests(unittest.TestCase):
    def test_roundtrip_closed_explicit_selection(self):
        selected=execution_selection();raw=canonical_bytes(selected.to_dict())
        self.assertEqual(RegisteredRuntimeExecutionSelection.from_bytes(raw),selected)
        self.assertEqual(len(selected.code),7)
        self.assertTrue(all(selected.to_dict()[name] is False for name in FALSE_FLAGS))

    def test_no_implicit_execution_or_capability_upgrade(self):
        for change in (dict(private_local_code_execution_confirmed=False),dict(private_local_code_execution_confirmed=1),
                dict(capability="UNSELECTED"),dict(purpose=" "),dict(provenance_sha256="x"*64)):
            with self.subTest(change=change),self.assertRaises(ValidationError):replace(execution_selection(),**change)

    def test_exact_seven_code_bytes_lengths_and_nonces(self):
        selected=execution_selection()
        for change in (dict(code=selected.code[:-1]),dict(code=selected.code[:1]*7),dict(code=list(selected.code)),dict(execution_id="../bad")):
            with self.subTest(change=change),self.assertRaises(ValidationError):replace(selected,**change)
        for value in (True,0,-1,256*1024+1):
            with self.assertRaises(ValidationError):replace(selected.code[0],bytes=value)

    def test_malformed_duplicate_nonfinite_and_noncanonical_json_rejected(self):
        valid=canonical_bytes(execution_selection().to_dict())
        for raw in (b'{"x":1,"x":2}',b'{"x":1e999}',b'{"x":NaN}',b'[]',b'\xff',valid+b" ",b'{'*2000,b' '*262145):
            with self.subTest(raw=raw[:20]),self.assertRaises(ValidationError):RegisteredRuntimeExecutionSelection.from_bytes(raw)

    def test_unknown_fields_and_all_delivery_readiness_upgrades_rejected(self):
        selected=execution_selection().to_dict()
        for key in FALSE_FLAGS|{'unexpected_field'}:
            raw=deepcopy(selected);raw[key]=True
            with self.subTest(key=key),self.assertRaises(ValidationError):RegisteredRuntimeExecutionSelection.from_bytes(canonical_bytes(raw))
