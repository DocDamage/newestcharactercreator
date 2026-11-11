"""Strict macro job contract tests (no Blender dependency or geometry claims)."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ucc.core.errors import ValidationError
from ucc.jobs.phenotype import (
    from_saved_parameters, validate_macro_parameters, verify_evaluated_shape,
)
from ucc.jobs.protocol import JobRequest


DEFAULT = {"height": .5, "muscle": .5, "weight": .5}


class PhenotypeTests(unittest.TestCase):
    def test_normalized_saved_snapshot(self):
        self.assertEqual(
            from_saved_parameters(tuple(sorted(DEFAULT.items()))), DEFAULT
        )
        self.assertEqual(
            JobRequest.new("create_human", options={"macro_parameters": DEFAULT}).options,
            {"macro_parameters": DEFAULT},
        )
        self.assertEqual(
            JobRequest.new("inspect_character", input_project="candidate.blend",
                           options={"macro_parameters": DEFAULT}).operation,
            "inspect_character",
        )

    def test_strict_morph_parameter_rejections(self):
        bad_cases = [
            {"height": .1},
            {**DEFAULT, "age": .5},
            {**DEFAULT, "weight": True},
            {**DEFAULT, "height": -0.1},
            {**DEFAULT, "muscle": float("inf")},
            {"height": "0.5", "muscle": .5, "weight": .5},
            [],
            None,
        ]
        for bad in bad_cases:
            with self.subTest(value=bad), self.assertRaises(ValidationError):
                validate_macro_parameters(bad)
        with self.assertRaises(ValidationError):
            JobRequest.new("create_human", options={"macro_parameters": {"height": .1}})
        with self.assertRaises(ValidationError):
            JobRequest.new("create_human", options={"execute_python": "no"})
        with self.assertRaises(ValidationError):
            JobRequest.new("inspect_character", input_project="candidate.blend",
                           options={"read_file": "../../secret"})

    def test_morph_read_back_survives_independent_reopen(self):
        evidence = {
            "macro_parameters_observed": DEFAULT,
            "macro_evaluated_vertices": 18000,
            "macro_evaluated_sha256": "a" * 64,
            "macro_active_shape_keys": 3,
            "macro_shape_evaluated": True,
            "visual_deformation_verified": False,
        }
        report = verify_evaluated_shape(DEFAULT, evidence, dict(evidence))
        self.assertTrue(report["morph_save_reopen_verified"])
        self.assertFalse(report["visual_deformation_verified"])

        with self.assertRaisesRegex(ValidationError, "changed during Blender reopen"):
            verify_evaluated_shape(
                DEFAULT, evidence,
                {**evidence, "macro_evaluated_sha256": "b" * 64}
            )
        with self.assertRaisesRegex(ValidationError, "does not match"):
            verify_evaluated_shape(
                DEFAULT, evidence,
                {**evidence, "macro_parameters_observed": {**DEFAULT, "muscle": .1}}
            )


if __name__ == "__main__":
    unittest.main()
