"""Synthetic mapping boundary checks; actual Blender tests supply skin evidence."""
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from ucc.animations.native_family import measured_body_profile
from ucc.animations.native_hands import hand_pairs, HAND_TARGETS
from ucc.core.errors import ValidationError
from blender_bridge.native_inputs import validate_profile


class NativeHandMappingTests(unittest.TestCase):
    def source(self):
        # Deliberately invented topology: no private source skeleton is bundled.
        source={"bones":[{"name":f"BoundaryOnly{i}","parent":None} for i in range(76)]}
        topology=json.dumps(sorted((b["name"],b["parent"]) for b in source["bones"]),separators=(",",":"))
        return source,sha256(topology.encode()).hexdigest()

    def test_optional_scope_preserves_body_map_and_adds_exact_anatomical_chains(self):
        source,fingerprint=self.source()
        with patch("ucc.animations.native_family.HIPS_OBJECT_TOPOLOGY",fingerprint):
            body=measured_body_profile(source,"a"*64,"b"*64,"c"*64)
            hands=measured_body_profile(source,"a"*64,"b"*64,"c"*64,include_hands=True)
        self.assertEqual(len(body["pairs"]),21)
        self.assertEqual(len(hands["pairs"]),59)
        self.assertEqual(len(HAND_TARGETS),38)
        validate_profile(hands,"a"*64,"b"*64,"c"*64)
        by_name={row["source"]:row for row in hands["pairs"]}
        for side,suffix in (("Left",".L"),("Right",".R")):
            wrist=by_name[side+"Hand"]
            self.assertEqual(wrist["source_tip"],side+"HandMiddle2")
            for digit,name in enumerate(("Index","Middle","Ring","Pinky"),1):
                self.assertEqual(by_name[side+"Hand"+name+"1"]["target"],f"metacarpal{digit}{suffix}")
                for joint in range(2,5):
                    row=by_name[f"{side}Hand{name}{joint}"]
                    self.assertEqual(row["target"],f"finger{digit+1}-{joint-1}{suffix}")
                    if joint==4:self.assertIsNone(row["target_tip"])
            self.assertIsNone(by_name[side+"HandThumb3"]["target_tip"])
        self.assertEqual({r["target"] for r in hands["pairs"][21:]},HAND_TARGETS)
        self.assertEqual(body["pairs"][10]["source_tip"],"LeftHandMiddle1")

    def test_unknown_topology_and_nonboolean_selection_never_get_a_hand_map(self):
        source,_=self.source()
        for value in (True,False,1,"yes",None):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                measured_body_profile(source,"a"*64,"b"*64,"c"*64,include_hands=value)

    def test_hand_pair_calls_do_not_share_mutable_lists(self):
        rows=hand_pairs();rows.clear()
        self.assertEqual(len(hand_pairs()),38)
