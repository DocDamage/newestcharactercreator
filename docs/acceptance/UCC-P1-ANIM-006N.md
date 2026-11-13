# UCC-P1-ANIM-006N — bounded target-arm fitting (in progress)

## Problem and scope

The actual owned held-finger clip contains hand/opposite-arm surface crossings
despite passing source FK, joint and skin-strain checks. A correction changes
target motion and must be declared independently of the original source conversion.
It cannot silently replace source FK or imply that grasp intent is known.

The staged application API validates complete SHA-bound arm-fitting trajectories,
bakes a separate private Action, measures its saved geometry, and requires a third
Blender process to reproduce that evidence and render targeted inspection views.
The existing source retargeter and player retain their previous behavior. Desktop
fitted playback and comparison are still outstanding; the full milestone is **not complete**.

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

The local suite runs 548 tests: 535 pass and 13 Windows symlink-privilege cases
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
outside the repository.

## Staged application implementation and real execution

- `fit_native_preview` checks local-preview rights, project identity/revision,
  original source-FK evidence and all bound inputs. Three closed worker operations
  stage the new Action, measure the completed saved scene, and independently
  reproduce every frame before returning a separate fitted result. Source,
  master, metadata, policy and staged copies are rehashed throughout. Cancellation,
  stale inputs, partial or unavailable surface checks never publish a fitted result.
- All 163 measured rest matrices/parents, exact float32 weights, source polygon
  winding, object matrices, bone deformation controls, neutral geometry and
  modifier settings must remain unchanged. Unkeyed helpers must remain identity;
  mapped scales remain exactly one and non-root translations exactly zero.
- A real saved-scene regression exposed float32 drift from restoring decomposed
  `matrix_basis` during neutral inspection. Inspection now restores the exact
  active rotation/location/scale channels; geometric hash checks remain strict.
- The actual application API accepted the owner's 300-frame clip using three
  distinct jobs: `93ee8176-b2bf-4403-87d6-fe955aca1cd6`,
  `24e05766-37da-4da2-94ed-95a195e64dac`, and
  `ad88401d-0e21-4397-845e-1565feda7c8c`. All corrected/raw skin and topology
  observations reproduce; 15 PNGs decode and bind to the canonical posed skin.
  The fitted scene SHA-256 is
  `b46fa59a03e2ce452d3f554b481401d9368dae3e0bab107c756f9e55a3151ecb`.
  Source/master/project bytes remain unchanged. This is a manually declared
  owner-specific correction, not automatic animation repair.
- Actual independently rehashed corruptions reject: one-ULP helper scale,
  one-ULP skin weight, changed bone deformation flag, rest roll, keyed wrist
  quaternion, polygon winding, and fabricated canonical skin hashes. These tests
  change private copies only. A valid strict-helper saved-scene regression passes.
- A separate real MPFB integration generated an original non-shipping 300-frame
  source with 59 roles, articulated fingers and root travel. The complete staged
  API passes, including 15 decoded renders and a measured 37.93-micrometre fitted
  hand displacement. Six real corruptions reject in that local run; the additional
  deformation-flag rejection was executed separately on the owner copy. Neither
  this small integration correction nor invented unit fixtures prove pack compatibility.
- The existing Linux workflow now runs both the unchanged full regression and
  this independent native-fitting suite, including all seven negative cases.
  All five workflows on the new PR head remain required before review acceptance;
  all five workflows pass on exact head `3b7015d87106dce338074f9020fc81ec45373422`.
  Both Linux matrix jobs pass; both five-file JSON-only artifacts were independently
  downloaded and SHA-256 checked. Native-fit artifact `14007975524` SHA-256
  `0c2d47eee59d7228a48a268d87b7e7a205464230e553dfbd5ff7c12fe17df0a9`;
  legacy regression artifact `14007612395` SHA-256
  `925aa0dc86c4657f8bc60ecd74916542c301cc650d2a8041d95d4a588f168083`.
  PR #48 is ready for review and remains unmerged. Only JSON summaries are uploaded.

## Remaining vertical slice

Export and independently verify fitted full-surface playback caches, then provide
a desktop original/fitted comparison with existing licensing, cancellation and
input-change invalidation. Keep source FK distinct, preserve hard deformation
bounds and never overwrite the master. All contact/visual/engine approvals remain false.

No new dependencies, downloaded assets or license rights. Paid source files,
poses, meshes, saved scenes, caches and rendered images remain private.
