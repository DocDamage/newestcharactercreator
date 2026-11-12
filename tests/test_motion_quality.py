"""Numerical diagnostic contracts; synthetic examples are not asset approval."""
from copy import deepcopy
import math
from types import SimpleNamespace as NS
import unittest

from blender_bridge.motion_quality import (
    EdgeStrain, JointMotion, MotionQualityError, swing_twist_degrees,
)
from blender_bridge.pose_environment import validate_pose_environment
from blender_bridge.rest_calibration import determinant
from ucc.jobs.reviewed_evidence import (
    ReviewedEvidenceError, compare_reviewed_evidence, validate_reviewed_evidence,
)
from ucc.desktop.animation_results import format_bvh_motion_evidence
from test_reviewed_evidence import reviewed, PAIRS


def axis_quaternion(axis, angle):
    vector = [0., 0., 0.]
    vector[axis] = math.sin(math.radians(angle)/2)
    return (math.cos(math.radians(angle)/2), *vector)


class MotionMathTests(unittest.TestCase):
    def test_known_compound_swing_twist_and_sign_equivalence(self):
        a, b = math.radians(30), math.radians(15)
        q = (math.cos(a)*math.cos(b), math.sin(a)*math.cos(b),
             math.cos(a)*math.sin(b), math.sin(a)*math.sin(b))
        for candidate in (q, tuple(-x for x in q)):
            swing, twist = swing_twist_degrees(candidate)
            self.assertAlmostEqual(swing, 60)
            self.assertAlmostEqual(twist, 30)

    def test_sign_continuity_and_complete_joint_frames(self):
        track = JointMotion("wrist.L")
        track.add((1., 0., 0., 0.), 1)
        q = axis_quaternion(1, 20)
        stored = track.add(tuple(-x for x in q), 2)
        self.assertGreater(stored[0], 0)
        self.assertAlmostEqual(track.report()["max_twist_degrees"], 20)
        self.assertAlmostEqual(track.report()["max_step_degrees"], 20)
        with self.assertRaises(MotionQualityError):
            track.add(q, 4)

    def test_accumulated_twist_and_sudden_step_reject_independently(self):
        track = JointMotion("head")
        for frame, angle in enumerate(range(0, 100, 10), 1):
            track.add(axis_quaternion(1, angle), frame)
        with self.assertRaisesRegex(MotionQualityError, "head, frame 11"):
            track.add(axis_quaternion(1, 100), 11)
        track = JointMotion("neck")
        track.add(axis_quaternion(1, -60), 1)
        with self.assertRaisesRegex(MotionQualityError, "step=120"):
            track.add(axis_quaternion(1, 60), 2)

    def test_nonunit_nonfinite_and_ambiguous_flip_rejected(self):
        for q in ((0., 0., 0., 0.), (2., 0., 0., 0.), (math.nan, 0., 0., 1.),
                  (True, 0., 0., 0.), (0., 1., 0., 0.)):
            with self.subTest(q=q), self.assertRaises(MotionQualityError):
                swing_twist_degrees(q)

    def test_local_stretch_rejects_small_motion_missed_by_whole_mesh_bound(self):
        points = [(0., 0., 0.), (.001, 0., 0.), (1., 1., 0.)]
        edges = [(0, 1), (1, 2)]
        strain = EdgeStrain(points, edges)
        self.assertEqual(strain.measure(points, list(reversed(edges)), 1)["max_edge_stretch_ratio"], 1)
        with self.assertRaisesRegex(MotionQualityError, "edge 0-1"):
            strain.measure([points[0], (.005, 0., 0.), points[2]], edges, 2)
        with self.assertRaisesRegex(MotionQualityError, "strain"):
            strain.measure([points[0], points[0], points[2]], edges, 2)

    def test_edge_topology_degenerate_and_malformed_evidence(self):
        points = [(0., 0., 0.), (1., 0., 0.), (1., 0., 0.)]
        strain = EdgeStrain(points, [(0, 1), (1, 2)])
        self.assertEqual(strain.report()["degenerate_baseline_edges_excluded"], 1)
        with self.assertRaisesRegex(MotionQualityError, "topology"):
            strain.measure(points, [(0, 1), (0, 2)], 2)
        for edges in ([], [(0, 0)], [(0, 9)], [(0, 1), (1, 0)], [(False, 1)]):
            with self.subTest(edges=edges), self.assertRaises(MotionQualityError):
                EdgeStrain(points, edges)


class Matrix:
    def __init__(self, diagonal=(1., 1., 1.)):
        self.rows = [[diagonal[i] if i == j else 0. for j in range(3)] for i in range(3)]
    def __getitem__(self, index):
        return self.rows[index]
    def to_3x3(self):
        return self
    def determinant(self):
        return determinant(self.rows)


class PoseEnvironmentTests(unittest.TestCase):
    def test_parent_poses_constraints_drivers_and_scaled_axes_cannot_pass(self):
        def bone(name, parent=None):
            return NS(name=name, parent=parent, constraints=[], bone=NS(use_inherit_rotation=True),
                      matrix_basis=[[float(i == j) for j in range(4)] for i in range(4)])
        for case in ("valid", "ancestor", "constraint", "driver", "scale", "mirror", "inherit"):
            parent = bone("parent")
            child = bone("mapped", parent)
            rig = NS(animation_data=None, matrix_world=Matrix(), pose=NS(bones={"mapped": child}))
            human = NS(matrix_world=Matrix())
            if case == "ancestor": parent.matrix_basis[0][3] = .1
            if case == "constraint": parent.constraints = [NS(mute=False, influence=1.)]
            if case == "driver": rig.animation_data = NS(drivers=[object()])
            if case == "scale": human.matrix_world = Matrix((1., 2., 1.))
            if case == "mirror": rig.matrix_world = Matrix((-1., 1., 1.))
            if case == "inherit": child.bone.use_inherit_rotation = False
            if case == "valid":
                validate_pose_environment(rig, human, ["mapped"])
            else:
                with self.subTest(case=case), self.assertRaises(MotionQualityError):
                    validate_pose_environment(rig, human, ["mapped"])


class QualityEvidenceTests(unittest.TestCase):
    def test_desktop_summary_reports_measured_frames_without_visual_approval(self):
        result = NS(evidence=reviewed(), revision=1, clip_name="synthetic-test.bvh",
                    clip_sha256="d" * 64, private_visual_review_blend="private/review_motion.blend")
        text = format_bvh_motion_evidence(result, calibrated=True, reviewed=True)
        self.assertIn("399", text)
        self.assertIn("frame 13", text)
        self.assertIn("not anatomical approval", text)
        self.assertIn("NOT been manually approved", text)

    def test_missing_unsafe_or_inconsistent_joint_and_strain_proofs_rejected(self):
        for case in ("schema", "edge", "count", "frame", "angle", "step", "pose"):
            data = reviewed()
            if case == "schema": del data["motion_quality_schema_version"]
            if case == "edge": data["full_timeline_frames"][5]["min_edge_length_ratio"] = .001
            if case == "count": data["mesh_edge_strain"]["measured_edge_count"] = 400
            if case == "frame": data["joint_motion_metrics"][0]["max_twist_frame"] = 26
            if case == "angle": data["joint_motion_metrics"][0]["max_twist_degrees"] = 100.
            if case == "step": data["joint_motion_metrics"][0]["max_step_degrees"] = 20.
            if case == "pose": data["target_pose_environment_checked"] = False
            with self.subTest(case=case), self.assertRaises(ReviewedEvidenceError):
                validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS)

    def test_workers_must_agree_on_local_strain_and_joint_maximum_frames(self):
        for case in ("strain", "joint", "topology"):
            a, b = reviewed(), deepcopy(reviewed())
            if case == "strain": b["full_timeline_frames"][5]["min_edge_length_ratio"] = .8
            if case == "joint": b["joint_motion_metrics"][0]["max_twist_frame"] = 14
            if case == "topology": b["mesh_edge_strain"]["evaluated_topology_sha256"] = "f" * 64
            with self.subTest(case=case), self.assertRaisesRegex(ReviewedEvidenceError, "disagree"):
                compare_reviewed_evidence(a, b, "Y_UP_TO_Z_UP", PAIRS)
