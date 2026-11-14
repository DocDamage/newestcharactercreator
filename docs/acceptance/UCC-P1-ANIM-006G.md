# UCC-P1-ANIM-006G — measured hip trajectory and origin compensation

Stacked on PR #40 (`4048f6b2071f4423a276091a269281010f81b4bb`), whose five
workflows passed. Neither PR is merged automatically. This task corrects a
specific native root-origin error; it does not approve the rejected walking or
kneeling clips, solve foot contact, or claim arbitrary-rig compatibility.

## Evidence for the gap

An independent source joint-head trajectory calculation on the previously
measured actual owner breathing animation found a maximum hip-midpoint error of
0.013421855 m at frame 268. Existing rotation/skin checks did not test that
trajectory. Applying armature-object translation directly to a target bone root
is insufficient when the rotation origins differ. The real MPFB root is near
the pelvis and is not assumed to sit on the ground; both origins and all joint
positions must be measured.

## Implemented contract

- Optional, closed `root_motion_policy` in the source/snapshot/master SHA-bound
  map: `SOURCE_HIP_MIDPOINT_V1` or `ARMATURE_ORIGIN_DISPLACEMENT_V1`. Missing policy
  retains the previous origin-displacement behavior. No existing explicit map or
  private result is rewritten. Unknown/non-string policies reject independently
  in the app and Blender boundary. Common rotation convention stays unchanged.
- The narrowly recognized automatic skeleton adapter writes the new policy
  explicitly into each freshly bound map. No user origin/axis questionnaire.
- Every source frame's actual left/right hip **joint-head positions**, including
  animated armature-world motion, determine the hip midpoint. Its displacement
  from measured source bind is transformed by calibrated body axes and scale,
  then added to the actual target bind hip midpoint.
- If `H` is this expected target hip midpoint, `B` the target bind hip midpoint,
  `r` the measured target root bind head, and `D = R_pose * R_bind.T`, the target
  root head is `H - D * (B-r)`. This preserves the full source trajectory while
  compensating different pivot locations and nonzero target bind orientation.
  No first-frame substitution, angle clamp, source motion edit or scale removal.
- Supported target hip heads must attach to the mapped root through neutral
  helpers with ordinary inherited rotation/scale. Intervening mapped pelvis
  bones or nonstandard inheritance reject this policy explicitly. Legacy maps
  remain available for their previous behavior; no unsupported hierarchy is
  silently reinterpreted.
- Blender measures actual target hip heads at every frame, rejects residuals
  above 0.0001 m and records per-frame midpoints plus a bounded bind/name/count/
  maximum-error proof. The app independently recomputes original source joint
  positions, expected hip/root positions and each target hip's rigid relation
  to the root from the recorded actual matrices. Rehashing a wrong-pivot pose,
  changing hip positions, summaries or bind points cannot pass validation.
- Private views use explicit `FOLLOW_HIP_MIDPOINT_TRANSLATION` and per-image
  `camera_hip_offset_world`, independently checked against the measured hip path.
  Legacy maps retain `FOLLOW_ROOT_TRANSLATION` and their prior manifest fields.
  This avoids following compensation-induced root movement as camera motion.
- The desktop reports the all-frame hip error in millimetres. It continues to
  disclose unapplied finger/face/toe motion, static UCC viewport and unverified
  visual/contact/engine quality. Existing source/master/revision/cancellation,
  licensing, full-frame FK/skin, strain and joint guards remain unchanged.

## Verification gates

- Closed-form tests distinguish source hip, source ground and target root
  origins, nonzero bind orientation and scale. Synthetic evidence tests reject
  rehashed legacy pivots, forged hip positions, wrong midpoint summaries, bind
  mutations, missing/unrequested proofs and unknown policies. Neutral-helper and
  inheritance negative paths, legacy contracts, camera-following and real Qt
  result wording are covered. Synthetic fixtures are not asset acceptance.
- Existing original 300-frame, 4 m/400-degree native-body Blender gate stays in
  place. A second original non-shipping FBX uses a true ground-level source
  object origin, measured real MPFB joints, independently authored bone rolls,
  a 20-degree tilt, four-metre travel and a complete turn. The target's actual
  root remains near its pelvis. This deliberately separates the origins.
- The second gate requires the old displacement-only rule to exhibit at least
  0.1 m of counterfactual pivot error while the new actual hip trajectory stays
  within 0.0001 m for all 300 frames. Four-metre travel is checked on the hip
  trajectory for this policy; target root-head travel can legitimately differ
  because it compensates the pivot. Legacy four-metre root travel assertion is
  unchanged. Both gates require two target workers, 20 weighted skin probes,
  complete skin/pose hashes, 15 private images, independent saved-Action reopen,
  translation/scale fault cleanup and unchanged originals.
- The independent reopen also remeasures every actual saved hip midpoint.
  Combined integration uploads remain the five existing JSON summaries only;
  the new result is nested under `native_hip_anchor_contract`. No generated FBX,
  Blender scene, rendered image or owner content is uploaded.
- Final local unit/worker/Qt suite: 438 tests run, success with 12 Windows
  symlink-privilege skips; 33 actual Qt cases included. All 15 preflight/guardrail
  tests pass, with syntax and whitespace checks passing.
- Actual Windows Blender 5.3.0 / MPFB 2.0.18 owner breathing preview: 300 frames,
  21 body roles, 20 independent skin probes, two workers, all 15 hip-following
  images and third-process Action/skin/hip reopening passed. A separate original
  source joint-head computation measured maximum numerical hip error
  0.000000350 m, versus the previous 0.013421855 m. These are simulation-matrix
  residuals, not physical metrology or visual-quality approval. The actual Qt
  background preview and readable error display were executed and inspected.
- Original walking/kneeling sources still reject at the same strain/knee guards;
  originals remain unchanged. Rejected-pose investigation finds the mapped joint
  segment directions consistent with source motion; a private dual-quaternion
  comparison worsens the offending edge stretch (4.010742× to 4.069257×). No
  skinning-mode change is adopted or presented as a fix.
- Combined local integration and exact-head CI outcomes are recorded in the PR
  after execution. Owner sources, mappings, full transforms, images and
  diagnostics stay private. No new runtime installation is required.

## Limits and next task

Anatomical anchoring is a root-motion constraint, not mesh repair. A rigid pivot
correction cannot repair pelvis/spine/upper-leg edge strain, and generic knee
limits still reject deep motion. Keep those guards intact. The next task remains
an independent source/target joint and skin analysis of the rejected walking
and kneeling cases, followed by a separately verified helper/contact solution.
No new application/runtime dependency or license grant is introduced.
