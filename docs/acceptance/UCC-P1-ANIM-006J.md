# UCC-P1-ANIM-006J — true-neutral skin strain reference

In development, stacked on PR #43. Main stays stable; no automatic merge.

## Measured problem

The native timeline currently treats frame 1 as an additional hard deformation
reference, even when that frame is already posed. Actual licensed bandaging
motion rejects at frame 201 with 4.270775× apparent stretch. Independent Blender
reopening measured the flagged edge as 9.610521 mm in the original neutral
master, 0.980314 mm on frame 1 and 4.186699 mm on frame 201: the edge recovers
from 10.20% to 43.56% of its neutral length. It did not stretch beyond the neutral
master. A posed first frame is not a rest frame.

## Implementation and acceptance

- Add a closed, SHA-bound map policy `mesh_strain_reference`:
  `FIRST_POSE_AND_NEUTRAL_V1` (including the missing-field legacy default) and
  `TRUE_NEUTRAL_BIND_V2`. Newly generated automatic maps declare V2 explicitly.
  Existing maps are not rewritten.
- V2 enforces the unchanged 0.05–4 edge limits against both actual bound-neutral
  skin and the original master, on every frame including frame 1. Main quality
  rows describe bound-neutral strain. First-pose-relative ratios remain complete
  measured observations, not an extra arbitrary rest-shape test.
- Keep source transforms, target poses, quaternion/root/joint limits, correction
  settings, original weights, topology, displacement/discontinuity guards and
  licensing/cancellation/revision protections unchanged. No smoothing recipe or
  private counterfactual is adopted by this change.
- The app requires the explicit policy, versioned quality evidence, complete raw
  observations and agreement with strict bound/master evidence. Fresh saved-Action
  reopening for bound-skin previews reproduces those observations and both neutral references. Legacy
  BVH/native paths retain their first-frame rules.
- Test compressed-first-pose recovery, truly unsafe neutral deformation,
  malformed/forged/cross-policy evidence, two-worker agreement, saved reopening,
  actual complete licensed clips, rendered inspection and in-UCC playback.
  Require all five exact-head CI workflows before PR acceptance.

## Baseline evidence and limits

PR #43 passed all five workflows on `a533d0f399f74857c3b24277eef48e1b453168e0`.
The full Windows Blender/MPFB regression and actual 300-frame GPU/UCC playback
passed. All 30 owned clips in the reviewed pack were additionally screened with
two source imports and one target worker: nine passed that numerical screen and
21 rejected. That screen did not provide two target workers, rendered review,
saved reopening, playback or visual acceptance for all 30 clips.

Private volume-preservation, stronger-smoothing and forearm-roll counterfactuals
did not resolve their tested failures and are not shipping changes. The new
reference policy does not excuse real neutral strain, knee/wrist limits,
contact problems, unapplied finger/face/toe motion or engine incompatibility.

## Executed local evidence

- The actual licensed bandaging clip passes all 300 frames, 21 mapped roles,
  20 visible-skin probes, two independent target workers, required saved-copy
  verification and 15 private rendered views. A separate Blender reopen also
  reproduces every first-pose observation and both true-neutral strain references.
  The formerly rejected frame 201 has the **exact same skin SHA** as the rejected
  capture: no source pose, correction setting, target pose or geometry repair was
  changed to obtain this result.
- Maximum actual bound/master-neutral stretch is 2.683328× and minimum length
  ratio is 0.054717, within unchanged 0.05–4 limits. Posed-origin stretch reaches
  17.284372×, now correctly recorded as an observation rather than a rest-shape
  verdict.
- Actual Windows UCC prepared the full verified cache and played the 300-frame
  clip in 10.016 seconds at its 30 fps source rate, with 299 distinct frames
  observed during the timed pass and five successful source-frame scrubs.
  The source-fps clock can skip a late display frame. License-field editing
  cleared motion. Original source/master/project/review bytes stayed unchanged.
- Actual V2 runs still reject the back-pain clip at 4.085776× true neutral
  stretch, kneeling at its 153.911-degree knee swing, and coughing at its
  92.274-degree wrist twist. No neutral or joint limit was raised.
- Current suite: **478 tests run**, success with 13 Windows symlink-privilege
  skips, including 37 desktop widget cases and three motion transport cases.
  All 15 preflight/guardrail tests, compilation and whitespace checks pass.
- The standalone actual MPFB/Blender original CI challenge passes all 300 frames,
  two workers, required saved reopening, an additional independent reopen,
  complete cache validation, 15 private images and rollback/tamper negatives.
  It starts at a nonneutral pose (first true-neutral minimum ratio 0.615559),
  retains the fixed 20-degree opposing bend, travels four meters and turns
  through more than 400 degrees. Rehashed observation forgery is rejected.
- Full combined regression and all five final-head CI workflows remain pending.
  The new original CI challenge
  begins in the previously tested opposing spine/leg bend and recovers, with
  full turn/travel. It is not a copy of an owned motion or pack compatibility
  proof. Rehashed forged observation data must reject during actual reopening.
