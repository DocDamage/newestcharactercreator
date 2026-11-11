"""Domain tests intentionally use metadata only; no fake Blender geometry."""
import json
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ucc.core.anatomy import slot_catalog, get_slot
from ucc.core.commands import CharacterSession
from ucc.core.errors import CompatibilityError, ValidationError
from ucc.core.models import CharacterProject, PartAsset, PartInstance


class CharacterProjectTests(unittest.TestCase):
    def test_new_roundtrip(self):
        source = CharacterProject.new("New humanoid")
        other = CharacterProject.from_dict(json.loads(json.dumps(source.to_dict())))
        self.assertEqual(source, other)
        self.assertEqual(source.geometry_state, "not_generated")
        self.assertFalse(source.master_blend)
        self.assertTrue(other.export_readiness())

    def test_reject_future_version_without_migration(self):
        value = CharacterProject.new("Test").to_dict()
        value["schema_version"] = 4
        with self.assertRaises(ValidationError):
            CharacterProject.from_dict(value)

    def test_reject_unknown_fields(self):
        value = CharacterProject.new("Test").to_dict()
        value["unexpected"] = "evil"
        with self.assertRaises(ValidationError):
            CharacterProject.from_dict(value)

    def test_reject_nan_and_bool_morph(self):
        for invalid in (float("nan"), float("inf"), True, -0.01, 1.01):
            with self.subTest(invalid=invalid):
                project = CharacterProject.new("Test")
                with self.assertRaises(ValidationError):
                    replace(project, parameters=(("height", invalid),))

    def test_no_false_geometry_ready(self):
        value = CharacterProject.new("Test")
        with self.assertRaises(ValidationError):
            replace(value, geometry_state="validated")
        with self.assertRaises(ValidationError):
            replace(value, master_blend="master/a.blend")

    def test_project_path_traversal(self):
        for source in ("../evil.blend", "C:/evil.blend", "/evil.blend", "a/../evil.blend", "\\srv\\evil.blend"):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                replace(CharacterProject.new("Test"), geometry_state="validated", master_blend=source)

    def test_duplicate_slot_or_id(self):
        p = CharacterProject.new("Test")
        a = PartInstance("x", "asset-a", "eye.L")
        b = PartInstance("y", "asset-b", "eye.L")
        with self.assertRaises(ValidationError):
            replace(p, parts=(a, b))
        with self.assertRaises(ValidationError):
            replace(p, parts=(a, replace(b, part_id="x", slot="eye.R")))

    def test_part_signature(self):
        slot = get_slot("humanoid.v1", "hand.L")
        asset = PartAsset("hand01", ("humanoid.v1",), "skinned_mesh", "hand.L", slot.socket,
                          "license1", "parts/hand01.glb", "humanoid.v1", "bind-pose-id", True)
        self.assertEqual(PartAsset.from_dict(asset.to_dict()), asset)
        with self.assertRaises(ValidationError):
            replace(asset, rig_profile=None)
        with self.assertRaises(ValidationError):
            replace(asset, mesh="../escape.glb")

    def test_slot_catalog_includes_requested_parts(self):
        names = {p.name for p in slot_catalog()}
        for part in ("head", "nose", "mouth", "torso", "eye.L", "ear.R", "hand.L",
                     "finger.thumb.R", "foot.L", "toe.big.R", "wing.L", "tail", "cape"):
            self.assertIn(part, names)
        with self.assertRaises(CompatibilityError):
            get_slot("dragon.v1", "tail")


class SessionTests(unittest.TestCase):
    @staticmethod
    def asset(kind="rigid_mesh", slot="eye.L", **kwargs):
        return PartAsset("eye-custom", ("humanoid.v1",), kind, slot,
                         get_slot("humanoid.v1", slot).socket, "license1",
                         "parts/eye.glb", source_verified=True, **kwargs)

    def test_set_morph_undo_redo_increments_revision(self):
        session = CharacterSession(CharacterProject.new("Test"))
        session.set_morph("height", .75)
        self.assertEqual(dict(session.project.parameters)["height"], .75)
        self.assertEqual(session.project.revision, 1)
        session.undo()
        self.assertEqual(dict(session.project.parameters)["height"], .5)
        self.assertEqual(session.project.revision, 2)
        session.redo()
        self.assertEqual(dict(session.project.parameters)["height"], .75)
        self.assertEqual(session.project.revision, 3)

    def test_reject_unverified_part(self):
        draft = replace(self.asset(), source_verified=False)
        session = CharacterSession(CharacterProject.new("Test"), {draft.asset_id: draft})
        with self.assertRaises(CompatibilityError):
            session.propose_part(draft.asset_id)

    def test_propose_only_not_geometry_validated(self):
        asset = self.asset()
        session = CharacterSession(CharacterProject.new("Test"), {asset.asset_id: asset})
        project = session.propose_part(asset.asset_id)
        self.assertEqual(project.parts[0].status, "proposed")
        self.assertEqual(project.parts[0].slot, "eye.L")
        self.assertTrue(project.export_readiness())
        session.remove_part("eye.L")
        self.assertEqual(session.project.parts, ())
        session.undo()
        self.assertEqual(len(session.project.parts), 1)

    def test_reject_socket_or_skeleton_mismatch(self):
        p = replace(CharacterProject.new("Test"), rig_profile="humanoid.v1")
        skinned = self.asset(kind="skinned_mesh", rig_profile="other.rig", bind_pose_fingerprint="a")
        session = CharacterSession(p, {skinned.asset_id: skinned})
        with self.assertRaises(CompatibilityError):
            session.propose_part(skinned.asset_id)
        bad_socket = replace(self.asset(), socket="wrong")
        with self.assertRaises(CompatibilityError):
            CharacterSession(p, {bad_socket.asset_id: bad_socket}).propose_part(bad_socket.asset_id)

    def test_no_op_does_not_change_revision(self):
        p = CharacterProject.new("Test")
        session = CharacterSession(p)
        session.set_morph("height", .5)
        self.assertEqual(p, session.project)
        self.assertFalse(session.can_undo)

    def test_history_limit(self):
        session = CharacterSession(CharacterProject.new("Test"), history_limit=2)
        session.set_morph("height", .6)
        session.set_morph("height", .7)
        session.set_morph("height", .8)
        session.undo()
        session.undo()
        with self.assertRaises(ValidationError):
            session.undo()
