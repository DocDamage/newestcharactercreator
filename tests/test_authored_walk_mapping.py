"""Pure numerical controls using the repository's NONSHIPPING rig fixture."""

from hashlib import sha256
import json
import unittest

from fixtures.authored_idle_mapping import encoded, evidence, pose_signature, rebind_snapshot
from ucc.animations.authored_idle_mapping import build_original_idle_profile
from ucc.animations.authored_walk_mapping import build_original_walk_profile
from ucc.core.errors import ValidationError


def _measured_walk():
    _, arguments = evidence()
    frame = json.loads(arguments['frame_json'])
    snapshot = json.loads(arguments['snapshot_json'])
    # Place distinguishable bilateral landmarks on the existing invented rig.
    locations = {'head': (0., 0., 1.5)}
    for side, sign in (('L', 1), ('R', -1)):
        locations.update({
            'upperleg01.'+side: (.13*sign, 0., .9),
            'foot.'+side: (.14*sign, -.05, .08),
            'wrist.'+side: (.63*sign, 0., 1.32),
            'finger2-1.'+side: (.69*sign, -.025, 1.32),
            'finger5-1.'+side: (.67*sign, .025, 1.32),
        })
    measured = {bone['name']: bone for bone in frame['anatomy']['bones']}
    for bone in snapshot['bones']:
        name = bone['name']
        if name not in locations:
            continue
        x, y, z = locations[name]
        bone['head'] = [x, y, z]
        bone['tail'] = [x, y+.05, z]
        for index, value in zip((3, 7, 11), (x, y, z), strict=True):
            bone['matrix'][index] = value
        measured[name].update(head_world=bone['head'], tail_world=bone['tail'],
                              rest_local=bone['matrix'], rest_world=bone['matrix'])
    for sample in snapshot['frames']:
        sample['armature_world'][11] = -.045
        for bone, pose in zip(snapshot['bones'], sample['poses'], strict=True):
            for index in (3, 7, 11):
                pose[index] = bone['matrix'][index]
        sample['pose_sha256'] = pose_signature(sample)
    return frame, snapshot


def _build(frame, snapshot, cancel_check=lambda: None):
    return build_original_walk_profile(frame, snapshot, source_sha256=snapshot['source_sha256'],
        snapshot_sha256=sha256(encoded(snapshot)).hexdigest(),
        target_master_sha256=frame['target']['master_sha256'], cancel_check=cancel_check)


class OriginalWalkMappingTests(unittest.TestCase):
    def test_full_walk_uses_the_existing_exact_51_pair_layout(self):
        original, arguments = evidence()
        idle = build_original_idle_profile(original, **arguments)
        frame, snapshot = _measured_walk()
        profile = _build(frame, snapshot)
        self.assertEqual(profile, {**idle, 'snapshot_sha256': sha256(encoded(snapshot)).hexdigest()})
        self.assertEqual(len(profile['pairs']), 51)
        self.assertEqual(profile['pairs'][0]['source'], '@ARMATURE')
        self.assertEqual(profile['root_motion_policy'], 'ARMATURE_ORIGIN_DISPLACEMENT_V1')

    def test_hash_valid_wrong_axis_or_end_frame_root_drift_fails(self):
        for channel, delta in ((3, .045), (7, .045), (11, .001)):
            with self.subTest(channel=channel):
                frame, snapshot = _measured_walk()
                sample = snapshot['frames'][-1]
                sample['armature_world'][channel] += delta
                sample['pose_sha256'] = pose_signature(sample)
                with self.assertRaisesRegex(ValidationError, 'prescribed armature-object world offset'):
                    _build(frame, snapshot)

    def test_wrong_static_bind_fails_independently_of_animated_world_offset(self):
        frame, snapshot = _measured_walk()
        snapshot['armature_rest_world'][11] = -.045
        with self.assertRaisesRegex(ValidationError, 'static armature bind'):
            _build(frame, snapshot)

    def test_omitted_helper_rotation_and_mapped_local_translation_fail(self):
        for name in ('finger2-0.L', 'finger1-3.R'):
            frame, snapshot = _measured_walk()
            index = next(index for index, bone in enumerate(snapshot['bones']) if bone['name'] == name)
            sample = snapshot['frames'][-1]
            pose = sample['poses'][index]
            if name == 'finger2-0.L':
                pose[0], pose[1], pose[4], pose[5] = 0., -1., 1., 0.
                message = 'silently drop'
            else:
                pose[3] += .00002
                message = 'unsupported animated local translation'
            sample['pose_sha256'] = pose_signature(sample)
            with self.subTest(name=name), self.assertRaisesRegex(ValidationError, message):
                _build(frame, snapshot)

    def test_clock_master_and_malformed_anatomy_reject(self):
        frame, snapshot = _measured_walk()
        snapshot['fps'] = 24.
        with self.assertRaisesRegex(ValidationError, '300 source samples at 30 Hz'):
            _build(frame, snapshot)
        snapshot['fps'] = 30.
        with self.assertRaisesRegex(ValidationError, 'selected exact master'):
            build_original_walk_profile(frame, snapshot, source_sha256=snapshot['source_sha256'],
                snapshot_sha256=sha256(encoded(snapshot)).hexdigest(),
                target_master_sha256='9'*64, cancel_check=lambda: None)
        frame['anatomy']['bones'].pop()
        with self.assertRaisesRegex(ValidationError, 'complete measured neutral rest'):
            _build(frame, snapshot)

    def test_authenticated_shape_still_requires_consistent_measured_rest(self):
        frame, snapshot = _measured_walk()
        bone = next(b for b in frame['anatomy']['bones'] if b['name'] == 'head')
        # Lists are distinct so the other measurements cannot move with the bad input.
        bone['rest_local'] = bone['rest_local'].copy()
        bone['rest_local'][3] += .01
        with self.assertRaisesRegex(ValidationError, 'world and local bone rest disagree'):
            _build(frame, snapshot)

    def test_idle_still_rejects_walking_armature_offset(self):
        request, arguments = evidence()
        snapshot = json.loads(arguments['snapshot_json'])
        for sample in snapshot['frames']:
            sample['armature_world'][11] = -.045
        with self.assertRaisesRegex(ValidationError, 'moved its neutral armature-object root'):
            build_original_idle_profile(request, **rebind_snapshot(arguments, snapshot))

    def test_cancel_remains_live_during_snapshot_validation(self):
        frame, snapshot = _measured_walk()
        calls = 0

        class CancelWalk(Exception):
            pass

        def cancel():
            nonlocal calls
            calls += 1
            if calls == 15:
                raise CancelWalk

        with self.assertRaises(CancelWalk):
            _build(frame, snapshot, cancel)
