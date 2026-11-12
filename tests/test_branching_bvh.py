"""Non-shipping synthetic hierarchy contracts; not external asset compatibility."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace as NS
import unittest

from blender_bridge.bvh_motion import LocalBvhMotion
from blender_bridge.bvh_multichain import MultiBvhError, select_explicit_chain
from blender_bridge.bvh_calibration_probe import _landmarks, BvhCalibrationProbeError
from ucc.animations.review_mapping import parse_review_mapping
from ucc.core.errors import ValidationError
from blender_bridge.rest_calibration import calibrate_rest_frames, RestCalibrationError
from ucc.jobs.protocol import JobRequest
from ucc.jobs.reviewed_evidence import (
    ReviewedEvidenceError, validate_reviewed_evidence, compare_reviewed_evidence,
)
from test_reviewed_evidence import reviewed, PAIRS


def hierarchy():
    # Root, trunk and two sibling limbs, with ten directly mapped weighted bones.
    parents = [None, 0, 1, 2, 3, 2, 5, 0, 7, 8]
    names = [f"Source{i}" for i in range(len(parents))]
    bones = []
    for i, parent in enumerate(parents):
        head = (float(i), float(i % 2), float(i % 3))
        bones.append(NS(name=f"Target{i}", parent=bones[parent] if parent is not None else None,
                        use_deform=True, head_local=head,
                        tail_local=(head[0], head[1], head[2] + 1)))
    offsets = {n.casefold(): tuple(a-b for a, b in zip(
        bones[i].head_local, bones[p].head_local)) if p is not None else (0, 0, 0)
        for i, (n, p) in enumerate(zip(names, parents))}
    parent_map = {n.casefold(): names[p].casefold() if p is not None else None
                  for n, p in zip(names, parents)}
    leaves = {n.casefold(): (0, 0, 1) for i, n in enumerate(names) if i not in parents}
    motion = LocalBvhMotion(.04, 5,
        {n.casefold(): ((0, 0, 0), (4, 0, 0), (8, 0, 0), (4, 0, 0), (0, 0, 0))
         for n in names}, tuple(names), parent_map, offsets,
        {n.casefold(): ("Xrotation", "Yrotation", "Zrotation") for n in names}, leaves)
    human = NS(vertex_groups=[NS(index=i, name=b.name) for i, b in enumerate(bones)],
               data=NS(vertices=[NS(groups=[NS(group=i % len(bones), weight=1.)])
                                 for i in range(320)]))
    rig = NS(data=NS(bones=bones), pose=NS(bones=[NS(name=b.name) for b in bones]))
    mapping = [{"source": n, "target": b.name} for n, b in zip(names, bones)]
    return motion, human, rig, mapping


class BranchingBvhContracts(unittest.TestCase):
    def test_full_size_map_and_all_rest_landmarks_are_bounded_and_checked(self):
        text = "\n".join(f'{"S" * 125}{i:02} -> {"T" * 125}{i:02}' for i in range(64))
        self.assertEqual(len(parse_review_mapping(text)), 64)
        with self.assertRaises(ValidationError):
            parse_review_mapping(text + "\nExtra -> Extra")
        vectors = [(1, 0, 0), (0, 1, 0)] * 63
        calibration = calibrate_rest_frames(vectors, vectors, "Z_UP_IDENTITY")
        self.assertEqual(len(calibration.rest_residual_degrees), 126)
        with self.assertRaises(RestCalibrationError):
            calibrate_rest_frames(vectors + [(0, 0, 1)], vectors + [(0, 0, 1)], "Z_UP_IDENTITY")
        bad = list(vectors)
        bad[-1] = (0, 0, 1)
        with self.assertRaises(RestCalibrationError):
            calibrate_rest_frames(vectors, bad, "Z_UP_IDENTITY")

    def test_ten_bone_branches_preserve_actual_parents_and_all_leaf_landmarks(self):
        motion, human, rig, mapping = hierarchy()
        selected, _ = select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)
        self.assertEqual(selected[5]["parent"], "source2")
        self.assertEqual(selected[7]["target_parent"], "Target0")
        src, dst = _landmarks(motion, selected, rig)
        self.assertEqual(len(src), 12)  # nine links + three leaves
        self.assertEqual(src, dst)
        parsed = parse_review_mapping("\n".join(f'{p["source"]} -> {p["target"]}' for p in mapping))
        self.assertEqual(parsed, mapping)
        JobRequest.new("verify_reviewed_bvh_chain", input_project="master.blend",
                       options={"axis_profile": "Z_UP_IDENTITY", "reviewed_mapping": parsed})

    def test_static_mapped_joint_is_allowed_but_still_requires_real_weights(self):
        motion, human, rig, mapping = hierarchy()
        motion.rotations["source5"] = ((0., 0., 0.),) * 5
        select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)
        rig.data.bones[5].use_deform = False
        with self.assertRaisesRegex(MultiBvhError, "weighted"):
            select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)

    def test_no_forward_parents_cycles_disconnected_roots_or_crossed_branches(self):
        for change in ("forward", "cycle", "root", "crossed"):
            motion, human, rig, mapping = hierarchy()
            if change == "forward":
                mapping[1], mapping[2] = mapping[2], mapping[1]
            elif change == "cycle":
                motion.parents["source2"] = "source4"
            elif change == "root":
                motion.parents["source5"] = None
            else:
                rig.data.bones[5].parent = rig.data.bones[3]
            with self.subTest(change=change), self.assertRaises(MultiBvhError):
                select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)

    def test_every_leaf_needs_real_rest_orientation_and_lengths_must_agree(self):
        motion, human, rig, mapping = hierarchy()
        selected, _ = select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)
        del motion.end_site_offsets["source4"]
        with self.assertRaisesRegex(BvhCalibrationProbeError, "Every mapped leaf"):
            _landmarks(motion, selected, rig)
        motion.offsets["source5"] = (100, 100, 100)
        with self.assertRaisesRegex(MultiBvhError, "inconsistent scales"):
            select_explicit_chain(motion, human, rig, "Z_UP_IDENTITY", mapping)

    def test_all_branch_landmarks_and_parent_evidence_checked_in_both_workers(self):
        data = reviewed()
        data["mapped_bones"][2].update(parent=PAIRS[0]["source"].casefold(),
                                       target_parent=PAIRS[0]["target"])
        data.update(rest_landmark_count=4, rest_residual_degrees=[.02, .03, .01, .02])
        validate_reviewed_evidence(data, "Y_UP_TO_Z_UP", PAIRS)
        compare_reviewed_evidence(data, data, "Y_UP_TO_Z_UP", PAIRS)
        bad = deepcopy(data)
        bad["mapped_bones"][2].update(parent=PAIRS[1]["source"].casefold(),
                                      target_parent=PAIRS[1]["target"])
        bad.update(rest_landmark_count=3, rest_residual_degrees=[.02, .03, .01])
        with self.assertRaisesRegex(ReviewedEvidenceError, "disagree"):
            compare_reviewed_evidence(data, bad, "Y_UP_TO_Z_UP", PAIRS)
        for bad in (replace_values(data, rest_landmark_count=3),
                    replace_values(data, rest_residual_degrees=[.02, .03, .01])):
            with self.assertRaises(ReviewedEvidenceError):
                validate_reviewed_evidence(bad, "Y_UP_TO_Z_UP", PAIRS)


def replace_values(data, **values):
    return {**deepcopy(data), **values}


if __name__ == "__main__":
    unittest.main()
