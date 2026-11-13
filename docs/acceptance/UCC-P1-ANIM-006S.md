# UCC-P1-ANIM-006S — body-aware bounded candidate search

## Problem and implemented scope

The prior automatic fitter bakes, renders and caches an arm-only candidate before
its final body-area guard can reject a contact trade. This slice requires an
independently reproduced original body-area baseline up front and tests those
constraints on disposable candidate poses before creating a fitting policy.
It retains the independent saved-scene guard as the final acceptance condition.

The owned bandaging clip remains a real limitation of the bounded translation
solver. A rejected search is not a corrected or production-ready animation.

## Implementation and boundaries

- `propose_native_area_contact_fit` requires eight exact SHA-256 bindings and
  fixed staged filenames. The additional input is the original-only stable body
  report. Missing, stale, paired, redirected or unavailable source evidence cannot
  start an accepted search. The prior seven-hash operation remains supported.
- Source surface reproduction gains a trusted internal mesh observer. Within
  the same actual skin/topology loop it reproduces the entire bound original
  body report, stable polygon topology, anatomy, original saved-Action receipt,
  complete timing and all 300 observations. No JSON option can skip that work.
- Candidate poses retain existing anatomical-chain, rest/roll, IK, joint,
  source/master strain, corrective-skin and actual pose checks. Only after the
  hand/opposite-arm test clears does the additional actual-mesh check compare
  stable contacted faces and each hand's pair count against that source frame.
- Source-measured body maxima inside the changed interval join critical frames.
  A failed complete-interval frame joins later screening. Screening success never
  substitutes for complete changed-interval verification.
- The search retains the fixed coarse directions and adds bounded 5/2.5/1.25 mm
  refinements, scaled down for a smaller anatomical bound. Ranking considers
  checked progress rather than directly equating counts of unrelated constraints.
  All existing 30 mm/2% span, motion, rotation, joint and skin limits remain.
- Exact previously measured frame/chain/offset queries can be reused for screening
  within this one private process. Final acceptance always evaluates every changed
  frame again, with the cache disabled and all quality/body checks active.
  Reuse does not reset the 1,024 actual-pose budget. Trial count stays below 500.
- Unavailable evidence, exhausted pose/trial budgets and an unsuccessful bounded
  grid return explicit rejection. No partial policy or saved fit is produced.
  A bounded private diagnostic records counts, rejected observations and
  constraint costs; those costs are not penetration depth or triangle-pair counts.
- The application first runs the two-process original area review, binds its
  current project/master/source, report and immutable cache, then validates the
  new proposal receipt. Only then can baking, independent measurement/rendering,
  fitted caching and the existing two-process final area guard run. A successful
  complete workflow therefore needs nine Blender jobs. Original playback and
  cancellation remain available throughout.
- Individual default worker timeout is 900 seconds to allow the denser bounded
  search; explicit caller timeouts remain honored. No geometry/motion safety
  threshold or evaluation/trial budget is relaxed.

## Actual local execution and limits

The actual owned clip's initial single-refinement search freshly reproduces its
complete original body baseline and rejects before baking. The project-bound
application executes source measurement `dbcff886-3749-4f3e-981d-47234239c570`,
source reproduction `e4c733e8-839b-4be8-aa78-4b32a56199bd` and proposal
`4187196d-22a1-457f-a094-4c5d931888ca`. Its 312 actual pose tests / 172 trials
include 41 body-area rejection observations. No fitting policy or saved fit is
created; source/master/project and bound inputs remain unchanged.

A separate private per-frame experiment tests all 18 coarse offsets on all 26
originally flagged frames: 468 actual evaluated poses. Frames 16–23 have no safe
coarse-grid offset under the unchanged arm/body constraints. This is a finite
grid observation, not proof that every continuous or multi-joint solution is
impossible. A finer search reaches the original 1,024-pose budget and correctly
rejects. Cached screening and failed-frame learning are tested separately; their
final real execution reaches the unchanged 1,024-pose limit and correctly rejects
with no partial policy. This run has 264 trials, 82 fresh body-area rejection
observations and zero query-cache hits; query reuse is supported but does not
provide a measured speedup on this specific search.

Two additional real original-source/MPFB negatives reject a no-crossing clip and
an independently rehashed false body-area baseline before producing any policy.
Original inputs remain unchanged. These original test sources do not establish
compatibility with an owned animation pack. Synthetic unit cases are contract
tests only. The final Python 3.12 suite runs 636 tests: 623 pass and 13 Windows
symlink cases skip. All 15 earlier preflight/guardrail tests, compilation and
whitespace checks pass. Unit tests cover complete-interval verification, learned
failure frames, cache-disabled final checks, budget propagation, finer refinement
bounds, rehashed baseline/scope faults, cancellation and closed eight-hash intake.

The actual desktop action passes source jobs
`5c810a7c-2799-4d4c-b69c-4b73197fe155` and
`44979332-0bbc-4272-a5fc-936e2a525e73`, then proposal
`04f8db72-e09c-4ebd-9d77-5009dca769f2` stops at the original pose budget.
It finishes in approximately 705 seconds, shows the plain evaluation-limit
explanation and full details, and retains the exact original GPU cache and frame.
No fit, render or comparison is produced. Source/master/project bytes remain
unchanged. The private desktop screenshot was inspected. Remote final-head gates
remain required; no unexecuted check is represented as passed.

The existing source-FK animation and older manual comparison remain inspectable.
The search does not change hand orientation or solve both arms. It does not
approve contact intent, penetration depth, grasp, foot planting or engine export.

## CI, permissions and next task

The existing native-fit suite retains every earlier assertion and adds both real
eight-hash proposal negatives using its already verified original source review.
The preceding full native-fit suite passed at about 61 minutes; its two new
full-sequence original-source negatives receive bounded headroom at 75 minutes.
No assertion is removed. All five workflows and all three Linux suites remain required. Only aggregate
original-source diagnostic summaries may leave CI; all purchased files, raw
geometry/poses, scenes, caches and images remain private.

No dependency, workstation installation, model, license-right or asset-upload
changes. Main remains unchanged; no automatic merge.

An additional private experiment tests 342 bounded translation/hand-orientation
configurations (350 actual pose evaluations) on source frames 8, 16 and 22.
Four configurations pass those three poses using 10–15 degrees of target-hand
local rotation. That is feasibility evidence only: no saved animation, complete
trajectory or independent angular/scene verification is claimed for that new
degree of freedom. A new explicit policy and independent implementation remain
necessary before exposing it in UCC.

All four experimental configurations were then measured over all 44 changed
frames (176 additional actual poses) with smooth hand-angle fades. None passed
the complete interval: the best still fails frame 20. Thus the three sampled
poses are explicitly not accepted as a working animation trajectory. The next
implementation must solve that remaining constraint and verify the complete
saved sequence independently.

Next: use the measured feasibility results to extend contact-preserving target
correction beyond a fixed wrist translation, with an explicit bounded orientation
or additional anatomical-chain policy and the same independent verification.
