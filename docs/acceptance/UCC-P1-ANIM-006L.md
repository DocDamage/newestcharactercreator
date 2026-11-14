# UCC-P1-ANIM-006L — audited palm rest frames

## Problem and explicit contract

The held-finger owner bandaging clip passes the previous body-forward hand
reference, but its right thumb holds 83.655 degrees of twist. A private original
articulated T-pose fixture rejected at 91.495 degrees. Deriving a hand's roll
from the body-forward axis does not fully describe its anatomical palm plane.

New optional map axes `PALM_LEFT_V1` and `PALM_RIGHT_V1` use actual wrist,
index-knuckle and pinky-knuckle rest positions. The SHA-bound map declares those
knuckles in `hand_reference_planes` with schema version 1. No aliases, pose-zero
assumptions, hand rotations inferred from frame 1 or source file edits are used.
The existing measured source rest matrices, target bind roll, body/world axis
conversion and global quaternion transport remain authoritative.

The two knuckles must be distinct mapped non-body joints in different strict
wrist branches. Every palm-referenced joint must be strictly below that wrist.
Body/wrist references retain their existing convention. Rest rays must be
between 0.005 and 0.3 of body landmark height; their absolute unit dot product
must be below 0.99. Missing, nonfinite, collinear, wrong-side/branch, unused or
retyped declarations fail explicitly. No joint, skin, speed or correction limit
is increased.

Automatic hand mapping uses this declaration. Body-only automatic mapping and
existing explicit maps keep their previous policy. The declaration helper
returns a new profile and does not rewrite its input. JSON schema and both
independent parsers reject incomplete/cross-policy declarations.

## Independent verification

The Blender worker measures target rest corners and records both rest normals.
The Python application independently recomputes the source plane from the
SHA-bound snapshot, target normals from reported corners, wrist correspondence
and source branches before validating every target quaternion.

The policy requires the existing bound-corrective path so saved-copy reopening
is mandatory. A fresh Blender process recomputes all declared corners, branches
and normals from both the original master rig and saved review rig. Its closed
report must contain the exact independently verified plane count. Cache creation
repeats these checks. Two target workers must agree on the complete new evidence.
Legacy evidence cannot inject undeclared palm proofs or reopen-count fields.
The fresh check also compares every actual rig rest matrix, including helper
bone roll. The previous endpoint/weight fingerprint remains in place; it alone
does not describe a complete bone frame. A rehashed roll-only edit with unchanged
endpoints is now an additional actual Blender negative case.

Actual Blender negative tests use a same-finger-branch knuckle declaration and
a rehashed false target ray. The latter scales a ray in its own plane, preserving
its normal and every pose/skin frame, so actual rest-corner verification is
required to reject it. Existing partial Action, modifier/settings, transform,
posed-origin observation, cancellation, SHA, revision and rollback guards remain.

## Executed local evidence

- Actual licensed bandaging: 300 frames, 59 roles, 58 independent skin probes,
  two agreeing workers, required saved verification, extra independent reopening,
  15 private body renders and six private hand close-ups. Original bytes remain
  unchanged. Its 21 body-joint global poses are exactly unchanged on every frame.
- Maximum hand twist decreases from 83.655 to 39.907 degrees; the right thumb
  holds 38.598 degrees. Maximum original-master stretch drops from 3.041824 to
  2.683328. No original source pose, master or weights were repaired or replaced.
- Actual Windows UCC played the complete verified cache in 10.000 seconds at
  30 fps, observing 299 distinct timed frames and five successful scrubs. The
  source clock may skip late display frames. Hand-scope editing clears motion.
- This owned clip holds its finger poses fixed. It is not proof of articulated
  finger animation-pack compatibility. The original CI fixture independently
  animates all 38 hand roles in T-pose with real MPFB skin and independently assigned source
  bone rolls; generated test sources are not copied paid motion.
- 495 tests pass with 13 Windows symlink-privilege skips; all 15 preflight and
  guardrail tests, compilation and whitespace checks pass. The standalone actual
  Blender T-pose hand challenge passes all 300 frames, both reopened palm planes,
  complete cache and rehashed ray/same-branch rejection with originals restored.
  Full combined local
  regression and final-head CI remain pending.

## Limits and next task

The close-ups improve the thumb's held orientation but contain arm/body
occlusion. Hand contact, grasp fitting, collisions, live skeletal playback,
facial/toe mapping, arbitrary-rig palm compatibility and engine import remain
unapproved. No dependencies or license rights are added; paid sources, poses,
meshes, caches, scenes and images remain private. Next: measure source-versus-
target hand contact through actual clips before adding any contact correction.
