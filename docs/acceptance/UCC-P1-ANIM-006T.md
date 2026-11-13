# UCC-P1-ANIM-006T — Explicit bounded target-hand orientation

Based on S; main remains unchanged. This is an additive target-fitting policy,
not a reinterpretation of source animation channels or source rest frames.

## Contract

`BOUNDED_NATIVE_ARM_HAND_IK_V2` retains the existing six SHA bindings, complete
source timeline, actual hierarchy, neutral master, skin stack and arm IK bounds.
Every frame additionally requires `hand_rotation_local_degrees`: an axis-angle
rotation vector expressed in the original **posed target hand's bone frame**.
Its norm is bounded to 15 degrees. Endpoints are zero; local correction speed
and acceleration are bounded to 90 degrees/s and 900 degrees/s². Source rest
calibration, anatomical planes and original FK evidence remain unchanged.

The independent core Rodrigues implementation and Blender quaternion
implementation rotate the hand and its mapped descendants around the fitted
wrist head. They preserve intrinsic finger articulation and wrist position.
Actual helper rest matrices, neutral helper channels, weights, topology and
source/master bytes must still reproduce. Hand-only frames with zero wrist
translation must be baked and checked too. V1 continues to preserve hand
orientation and rejects the additional V2 fields.

Both independent full-sequence angular audits now include the hand for V2.
The world-space correction audit remains necessary because smooth local
rotation vectors can become discontinuous when the posed hand axes move.
The application also checks the V2 worker's angular maxima against its
independent audit (0.1 degree/s and 2 degrees/s² numerical tolerance).
Rehashed measurement policy identifiers must match the bound policy bytes.
Candidate query keys include orientation; a translated pose cannot stand in
for a different wrist rotation. Final full-interval checks remain fresh.

## Acceptance and reversibility

- Existing V1 unit/integration behavior remains supported.
- Reject malformed, nonfinite, boolean, oversized, discontinuous, missing or
  extra rotation fields, changed endpoints and mismatched evidence versions.
- Verify local axes on a rolled hand, fixed pivot, rigid finger descendants,
  unrelated bones, zero-translation rotation and source input immutability.
- Run the existing saved-fit API against actual owned animation, including
  all 300 poses/skins/topologies, independent fresh saved-file reproduction,
  private decoded renders, cache and paired stable-body-area guard.
- Add an original-source/real-MPFB CI gate with a wider hand-rotation window
  than the translation window, verified full cache and rehashed saved hand
  Action corruption rejection. This is separate from owned-pack evidence.
- Preserve every prior CI assertion. The native-fit suite receives a bounded
  90-minute timeout for the additional five full-sequence/reopen jobs, following
  the preceding R suite's observed roughly 61-minute execution.

Worker code stays in the Blender adapter; no core bpy or Qt imports. No new UI
control, dependency, installation, download, license-right or asset-upload
change. Original scenes are never overwritten. Removing this additive policy
restores the prior behavior without changing any source or project revision.

## Execution status

Private finer feasibility measurements found two translation/orientation
configurations that pass all 44 changed poses (94 actual disposable tests in
the refinement run). This alone is not saved-animation or visual approval.
The first configuration passes the complete production saved-fit API: stage,
canonical measurement and independent reopening/render verification across
all 300 frames, with fifteen independently decoded private images. The actual
run took 363.203 seconds. Private quarter/front views at frames 20/16 were
inspected; this is not visual approval of the sequence.
The independent analytic 300-frame audit measures about 45.194 degrees/s and
656.388 degrees/s²; the fresh Blender measurement reports about 45.193 and
656.420 respectively. The subsequent cached-playback export passes. Two fresh
body-area workers independently reproduce all 600 original/fitted rows: no newly
involved checked areas and no per-hand pair increase. The final guard passes.
Original body flags are 193 frames; fitted flags are 164. Opposite-arm flags
drop from 26 to zero. Remaining body crossings are not cleared or approved.

The private saved-fit jobs are `40b45312-09c1-4470-a9f0-15014c2aac00`,
`adaf7774-1cee-461e-9a55-8fb86cb1d0d9` and
`bbce3aea-0c7f-4cb9-8d80-06b99b0bcd85`. Cache job
`134bf030-fb17-4017-9476-5871875a7b26` checks all 300 frames. The paired area
jobs are `74150d16-fd67-4c8a-b9b1-c41b2b8402a8` and
`2c17e61e-91fe-4296-bdf5-269b0a8236cd` (574.969 seconds including cache).
The scene SHA is
`4c3408e279752ff27c6db8cf9c5863c23763e5e8cd7b8af5b1cf66d77dc68101`;
the reproduced body report SHA is
`cb31a5d587ba60a068375069d84503fc5f40b5157fa2f599b1cf08d470de49b0`.

Actual Windows/PySide6 GPU comparison draws all 300 fitted frames in 10.016
seconds, preserving frame/camera/clock when switching views. A real watched
policy-copy edit clears both views; original source/master/project bytes remain
unchanged. The project-local comparison launcher now loads this explicitly
declared wrist policy and its checked body annotations, retaining prior launcher
and guide copies for rollback. Private scenes, images and caches remain outside
Git. Final exact-head remote gates remain required.

The full local suite runs 644 tests: 631 pass, 13 Windows symlink skips
(91.812 seconds). All fifteen earlier preflight/guardrail tests, compilation and
whitespace checks pass. Blender is 5.3.0, hash `02f0899d78e3`; Python is 3.12.10.
The original-source/real-MPFB CI helper also runs locally and passes its complete
300-frame saved/skin/cache/render checks plus real rehashed hand-Action rejection
in 606.672 seconds. Its independent angular maxima are 1.279 degrees/s and
6.406 degrees/s². This original CI source is distinct from the owned bandaging
clip. Both retain all original source/master/project bytes.

Automatic candidate search still uses S's translation-only policy. This
milestone provides the independently checkable orientation degree of freedom;
it does not claim that an automatic generic hand search has been implemented.
Grasp intent, visual acceptance, other animation packs and engine imports
remain unverified. All purchased scenes, images, raw geometry/poses and caches
stay private under the workspace's evidence/project folders.

Next: derive the bounded orientation trajectory in automatic candidate search
and retain the final saved-cache/body-area guard before desktop publication.
