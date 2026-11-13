# UCC-P1-ANIM-006P — measured bounded contact candidate workflow

## Problem and implemented scope

The owner should not need to author correction trajectories. A new local action
tries a bounded target-arm correction using the complete measured original
hand/opposite-arm surface report. It retains source FK and the original playable
cache, then returns an original/fitted pair only after the existing saved-Action,
independent geometry, rendered-view and full playback gates pass.

This is a bounded candidate search for the currently audited humanoid family,
not universal collision repair or approval of grasp intent.

## Boundaries

- `propose_native_contact_fit` takes seven exact SHA-256 inputs and fixed staged
  filenames. It first reopens the original source-FK scene and reproduces every
  original surface/topology row. Rehashed false contact annotations reject.
- `BOUNDED_CONTACT_OFFSET_SEARCH_V1` derives one hand's nearest mapped arm
  ancestors through the actual complete hierarchy. It uses measured contact
  onset/end/maxima and smooth half-second fades, clipped to unchanged endpoints.
  Trial vectors use a fixed coarse grid and bounded refinement, without asset
  filenames, owner-specific vectors or motion-pack assumptions.
- Every candidate retains the existing 30 mm/2% span, velocity, acceleration,
  15-degree IK, actual helper-translation/scale, joint swing/twist, neutral/master
  strain and corrective-skin bounds. The complete changed interval must have zero
  checked crossings. Search is capped at 1,024 actual pose evaluations; exceeding
  the budget or exhausting candidates rejects rather than returning a partial fit.
- No measured crossings, unavailable/partial inspection, two contacting hands,
  contact at the first/final source frame, excessive contact interval, cyclic or
  missing hierarchy and unreachable/ambiguous IK produce explicit rejection states.
- Candidate observations remain unsaved search results. They cannot bypass the
  three-process saved-fit pipeline or its independent analytic application solver.
  The resulting fitted cache independently reproduces all corrected/raw frames,
  topology and declared target motion again before playback.
- Application intake revalidates the source FK, actual original cached vertices,
  surface-verification receipt, license, current revision/master, policy and all
  staged/original hashes. Cancellation, changed files, false flags, incomplete
  intervals and invalid receipts never return a partial comparison.
- The GPU viewer offers **Try bounded hand/arm fit** only for an original checked
  cache with flagged frames. The control is disabled during other work and for a
  displayed comparison. Existing cancellation and source/project invalidation
  remain active. Failed fitting retains original motion.

## Local execution

Actual Blender 5.3.0/MPFB 2.0.18 measurements use the owner's private existing
300-frame, 59-role held-finger clip. The complete source has 26 crossing frames,
6 through 31. No purchased source or derived geometry is committed or uploaded.

The production candidate worker freshly reproduces all 300 source contact rows,
tests 20 trials/83 actual poses, and checks all 44 changed frames (2–45). It selects
a 28.284 mm offset `(0.020, 0, -0.020)` from its generic grid; the earlier manually
declared trajectory is not supplied to the search. Original inputs remain unchanged.

The final complete application workflow passes five real Blender jobs:

- Proposal: `6f8ed63f-d33b-4f93-b876-9865617e53fd`.
- Saved Action: `7adb520c-fbde-464a-89cd-1c064ed87670`.
- Canonical saved measurement: `426bdcdc-a2be-4f88-8e59-ce43b237a29d`.
- Independent reproduction/rendering: `522b18ce-2e83-4530-926f-73c144b5b2d9`.
- Fitted skin cache: `3f15e2b4-466c-4ff8-9f20-6836b2071cb4`.

All 300 corrected/raw skin, pose and topology observations pass, along with all
15 independently decoded/skin-bound views. Fitted scene SHA-256 is
`3684c7ac098b21b7496b68a462fd51aa8ce07e133f5fa08873bd31338c7ebf65`.
Added angular speed/acceleration measure 43.814 degrees/s and 642.000 degrees/s²,
within unchanged limits. The entire workflow takes approximately 630 seconds.
Source animation, authoritative master, source review and project bytes remain
unchanged. The final run includes the explicit algorithm-version receipt, complete source
intake and independent saved-scene/cache verification.

Actual RTX 3060 comparison shows different original/generated fitted buffers at
the same frame and camera. All 300 fitted frames render in approximately 10.015
seconds. A watched policy-copy change clears both caches. Grasp/visual/engine
approvals remain false. Qt tests separately verify that the real action dispatches
this guarded API, freezes its fitting control and preserves cancellation wiring.

The final local suite runs 583 tests: 570 pass and 13 Windows symlink cases
skip. Plain-language rejection dialogs are tested through actual Qt widgets,
with complete raw details retained behind their details control. All 15
earlier preflight/guardrail cases, compilation and whitespace checks pass.

Two real Blender negatives use a separately generated original 300-frame source
and actual MPFB human: no-crossing input rejects, and independently rehashed false
contact annotations reject before proposal. Original inputs remain unchanged.
The Linux native-fitting suite includes these cases through
`ci/verify_native_fit.py --contact-candidate-check`. They are explicitly negative
tests and do not claim positive animation-pack compatibility. All five final-head
workflows pass on `69baee4fcea50dfac60664847c85093be8d5fc67`, including both
complete Linux suites. The initial core runner exposed an optional-Qt test guard
error; the final head fixes that guard while preserving mandatory Qt execution.
The independently downloaded five-JSON regression/native-fit artifacts have
SHA-256 `eaac8a6d0d246cdca4a70564dd333b70c1a1151e27706d463eef218761c8c5eb`
and `9199d83b5cc70bf75c4f5f7598fb04f74f7d145eca212a3132c97f83a26bd994`.
PR #50 is ready for review and remains unmerged.

## Remaining limits and next task

Only hand/opposite-upper-limb triangle crossings are checked. Containment,
hand/torso and other body contacts, source intent, grasp/props and visual quality
remain unverified by the accepted contact contract. An exploratory private
central-body probe finds crossings in 193 original and 172 fitted frames, with
no frame gaining triangle pairs after fitting; that new region policy still
needs independent contract verification. The owned source holds its fingers fixed. Bound corrective
Blender skin is not engine portable. No joint or strain cap is relaxed.

Next: measure hand/torso interactions so fitting cannot silently trade the checked
arm crossings for currently unmeasured body intersections. Keep the current
original/fitted comparison and every independent verification guard.

No dependency, download, license-right or asset-upload changes.
