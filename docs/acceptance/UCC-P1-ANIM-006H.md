# UCC-P1-ANIM-006H — audited bound corrective skin preview

Stacked on PR #41 (`64a602ce591d2095007366fd6f744d92376fa401`). Main stays stable;
no automatic merge. The original/master-modifier path remains available and
retains its deformation limits. This task makes a real private body preview
usable for a walking clip previously rejected at a pelvis edge; it does not
certify general retargeting, contact quality or engine portability.

## Implemented contract

- Optional, closed `skin_deformation_policy` in the existing source/snapshot/
  master SHA-bound map: `MASTER_MODIFIERS_V1` (also the missing-field default) or
  `BOUND_CORRECTIVE_SMOOTH_V1`. Unknown values/types reject in app and worker.
  The measured automatic skeleton adapter writes the corrective policy explicitly
  into newly generated maps; existing explicit maps are not rewritten.
- Use Blender's real bound `CORRECTIVE_SMOOTH` after the original modifier stack.
  Fixed versioned settings: factor 0.5, five SIMPLE iterations, scale 1, BIND
  rest source, full-object correction, no smooth-only mode or boundary pinning.
  There are no adjustable guard thresholds, pose clamps or conditional fallbacks.
- Require one ordinary vertex-group armature, followed by at most four static
  vertex-group masks. MPFB's real **Hide helpers / body** mask remains enabled.
  Record each source modifier's settings and SHA-256 of mask-group membership;
  reject dynamic/smooth masks, unsupported stacks, envelopes and mismatched
  viewport/render state. Never remove the mask to force a preview to pass.
- Bind against actual neutral geometry. Source and derived topology/counts must
  agree; neutral-shape change is bounded to 0.000001 local unit. Original and
  bound neutral hashes, exact settings, binding state and source-stack metadata
  are recorded. The actual owner/CI base has 19,158 vertices, with **13,380
  evaluated visible vertices** after the unchanged helper mask.
- All 20 nonroot mapped-joint probes run through the bound correction and must
  move actual visible weighted skin and restore its exact neutral hash. All 300
  source frames retain their original source transforms and calibrated target
  bone poses. Joint, root, hierarchy, scale and discontinuity guards are unchanged.
- Evaluate the corrected skin against both the bound neutral mesh and the
  original master's neutral mesh every frame. Both retain the 0.05–4 edge-ratio
  limits, topology/coverage checks and existing displacement guards. Temporarily
  disable only the owned corrective modifier to measure the *same keyed pose*
  uncorrected; record raw SHA, corrected-vertex count and maximum change. Reject
  correction beyond 3% of character bounds or a policy with no real effect.
- Two fresh baking workers must agree on the complete matrix/skin/raw/corrected/
  original-master-relative timeline. Restore the owned modifier, original stack,
  mask weights and exact neutral geometry after each run; no original file save
  or project revision/promotion. Failed binding, mid-Action errors and cancellation
  remain safe. Existing user modifiers are neither replaced nor silently muted.
- Corrective results additionally require the new protocol-v1 operation
  `reopen_native_fbx_body` in a **third Blender process**. It takes six exact SHA
  identities, fixed staged filenames, no script/path/render overrides and bounded
  JSON/scene sizes. It opens the original master and saved copy without rebaking,
  validates source masks/weights/rest, actual bound modifier/settings, neutral
  geometry, Action channels/linear keys/fps and all-frame coverage. Every saved
  corrected/raw skin hash, actual target pose, original/bound edge strain and hip
  position must reproduce. All input files are rehashed after inspection.
- The app requires a closed, fully bound reopen report before publishing success.
  It rechecks original/staged bytes, revision, cancellation, first artifacts and
  the 15 private hip-following images after reopening. The desktop discloses
  private smoothing and saved-copy verification; all visual/retarget/engine
  approvals remain false. Legacy explicit profiles retain their prior behavior.

## Executed evidence

- Baseline PR #41: all five exact-head workflows passed. Current local suite:
  **451 tests run**, success with 12 Windows symlink-privilege skips, including
  34 actual Qt cases. All 15 preflight/guardrail tests, syntax and whitespace
  checks pass. New unit cases cover unsupported policies, static-mask hashes,
  malformed/forged proofs, settings/binding/neutral-shape failures, original-master
  strain, correction caps, third-process failure/tamper/cancel and late PNG changes.
- Actual Windows Blender 5.3.0 / official MPFB 2.0.18: the licensed local walking
  clip now passes 300 frames, 21 mapped body roles, 20 independent skin probes,
  two baking workers, application-required saved-copy reopening and 15 private
  rendered views. A separate fourth-process test remeasured all corrected/raw
  skin, bone poses, bound/master strain and hip positions from the saved Action.
  The numerical edge guard was not relaxed: maximum original-master stretch is
  approximately 2.34×, versus the prior 4.010742× failure at frame 82. Walking
  root travel is 5.314 m. Source/master/project/profile bytes stay unchanged.
- Actual breathing preview also passes the complete corrected/reopen path;
  kneeling still rejects at the existing 153.911-degree knee swing versus its
  150-degree generic guard. No angle clamp or input-motion edit was introduced.
- Actual Qt walking preview was executed; its result reports private smoothing,
  every saved corrected/raw frame reproduced, unchanged originals and remaining
  foot/visual/engine limitations. Sampled front/quarter/side views were inspected.
- A real saved-copy verification worker was cancelled after loading the review:
  no success was published, and source/master/project/all staged originals stayed
  byte-identical.
- The original non-shipping corrective CI fixture uses measured MPFB geometry,
  independent rolls and an analytically authored opposing bend, ground-origin
  tilt and complete turn/travel. Its 300 frames pass bound skin probes, both
  baking workers, application reopening, an additional independent reopen,
  original/bound strain, 15 private images and immutability. Actual Blender fault
  injection verifies failed binding, translation/scale rejection and factor
  mutation after partial Action creation; each restores the original stack and
  skin. Copied saved scenes with factor 0.6 or a shifted mesh object reject even
  after their scene/timeline hashes are deliberately updated. Original evidence
  is preserved; local-space skin hashes cannot hide wrong world transforms.
- The full combined local regression and five exact-head CI outcomes are recorded
  in the PR after execution. Existing JSON-only artifact paths remain unchanged;
  the new summary is nested as `native_corrective_skin_contract`. No owner assets,
  transforms, paths or rendered media are uploaded. Synthetic unit fixtures and
  original CI motion are never represented as real animation-pack compatibility.

## Limits and next task

This is a Blender-bound corrective preview. Game engines generally do not
execute Blender's modifier stack; equivalent corrective data must be baked or
implemented and verified in an engine before export can be approved. No engine
compatibility or export rights are granted by this task. Smoothing does not fix
unapplied finger/face/toe motion, hand contact, foot planting or unsupported knee
angles. Two actual clips passing numerical checks do not certify the entire pack
or 100 usable animations. Sampled images do not establish full visual quality.

Next: reliable animation playback **inside UCC** using actual verified skinned
motion, with source/master/revision/cache provenance and cancellation intact.
Continue separate contact/finger/engine work incrementally; never merge without
owner approval. No new application dependency or runtime installation is added.
