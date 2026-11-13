# UCC-P1-ANIM-006N — bounded target-arm fitting (in progress)

## Problem and scope

The actual owned held-finger clip contains hand/opposite-arm surface crossings
despite passing source FK, joint and skin-strain checks. A correction changes
target motion and must be declared independently of the original source conversion.
It cannot silently replace source FK or imply that grasp intent is known.

The current foundation validates complete SHA-bound arm-fitting trajectories and
independently computes each fitted global pose. It does not yet expose a repair
command or desktop control. The existing source retargeter and player retain
their previous behavior. The full fitting milestone is **not complete**.

## Implemented boundaries

- Closed `BOUNDED_NATIVE_ARM_IK_V1` policy binds source, source snapshot, mapping,
  authoritative master, original saved review and original timeline SHA-256.
  Regular policy files are bounded to 512 KiB; duplicate fields, malformed JSON,
  bool/nonfinite/huge numeric values, hash changes and cancellation reject.
- One declared anatomical hand follows its two nearest mapped arm ancestors in
  the complete measured target tree. Missing helpers, cycles, crossed branches,
  wrong sides and unrequested skin/reference policies reject.
- All source frames and the original FPS are mandatory. Endpoints remain unchanged.
  Corrections have fixed limits: 30 mm and 2% of measured head-to-foot span,
  0.3 m/s, 5 m/s² and 15 degrees per corrected segment. Complete-sequence auditing
  separately bounds the added rotation to 90 degrees/s and 900 degrees/s², catching
  pole flips even when the declared endpoint offsets are small and smooth. These fitting limits
  do not replace or relax existing joint, skin, root or rollback guards.
- Analytic two-bone IK preserves measured segment lengths, elbow pole and hand
  orientation; the mapped hand descendants translate together. Unrelated mapped
  bones retain their original poses. Unreachable endpoints, ambiguous poles and
  excessive elbow displacement reject instead of scaling/clamping the arm.
- Actual fitted poses can be compared against this independent pure-Python result.
  Source FK evidence remains the immutable reference; fitted poses are a separate
  result, not evidence that the original source conversion produced them.
- Private CPU rendering accepts five explicit ordered source frames while keeping
  the complete source frame count. Existing default sampled frames are unchanged.
  This permits inspection of measured problem frames rather than assuming the
  usual five samples include the affected interval.

## Executed progress

The local suite runs 528 tests: 515 pass and 13 Windows symlink-privilege cases
skip. All 15 preflight/guardrail tests, compilation and whitespace checks pass.

Actual Blender 5.3/MPFB trials use the owner's existing private 300-frame clip.
A smooth downward-only repair reduced crossing frames from 26 to six but failed
the unchanged 0.05 edge-ratio limit at frames 5/6; it was rejected. Forearm-only
twist trials do not remove the raw-skin deformation rejection.

A revised, multidirectional trajectory capped at approximately 25.5 mm passes
the measured joint/strain/local-translation checks and removes these measured
crossings in all 300 unsaved frames. The independent application solver matches
Blender's fitted global poses over the complete clip. Original inputs remain
unchanged. These are owner-specific feasibility observations, not arbitrary pack
compatibility or source-contact intent proof.

The first saved-copy comparison caught a frame-25 skin-hash mismatch between
construction-time observations and the reopened keyed Action. That result is
not accepted. Canonical measurement must occur after the Action is fully baked
and saved, followed by a separate fresh-process reproduction. Hash assertions
remain strict. Canonical observations are now measured from the completed saved
Action, followed by a separate fresh Blender process that reproduces all 300
corrected/raw skin hashes and fitted global poses. The unchanged edge limits
hold (minimum 0.0547199, maximum stretch 2.683328), all 163 actual rest matrices
and original inputs remain unchanged, and an actual wrist-pose alteration rejects
and restores the original measured skin. Crossing frames remain zero under the
defined hand/opposite-arm triangle policy. This does not certify whole-body
collision or contact intent.

Fifteen private CPU clay views cover frames 1/6/8/11/31. Their PNG bytes, hashes,
decoded foreground bounds and posed-skin bindings are independently checked.
Additional correction angular speed/acceleration measure 44.8738 degrees/s and
657.394 degrees/s², below their fixed bounds. Contact/grasp visual approval is
still false. The completed saved Action, private policy, reports and images stay
outside the repository; the application does not yet publish this fitted clip.

## Remaining vertical slice

Integrate fitting as a separate staged Blender operation with project/revision,
license, cancellation and input-immutability guards; require complete fresh saved
Action/raw skin/rest/topology verification before publication. Add original real
Blender integration/negative tests and a defined desktop comparison workflow.
Do not replace source FK, weaken deformation limits, overwrite the master or
publish a partial fit as successful. All contact/visual/engine approvals remain false.

No new dependencies, downloaded assets or license rights. Paid source files,
poses, meshes, saved scenes, caches and rendered images remain private.
