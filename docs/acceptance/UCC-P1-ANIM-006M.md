# UCC-P1-ANIM-006M — complete cached-skin surface inspection

## Actual gap

The licensed bandaging clip passes joint/strain checks but contains hand/arm
surface crossings. A private initial upper-arm/forearm check found 20 affected
frames. The implemented shoulder-inclusive upper-limb policy finds **26 frames,
source frames 6–31**. Its maximum is 81 triangle pairs at frame 8; frame 27 has
80. None of the five rendered sample frames (1/75/150/225/300) includes these
crossings. Numerical pose/deformation checks and sparse views are insufficient
to approve the complete animation's contact quality.

## Working inspection

Every newly prepared native skin cache measures each hand against the opposite
upper-limb branch, including its shoulder. Regions follow the actual rig's two
declared hand roots, their common ancestor, descendants and deform-weight groups;
no source filenames or bone-name aliases select body regions. Each evaluated
vertex uses its dominant normalized deform-weight region when that region has
at least half its total deform weight. Exact ties prefer hands over arms, then
left over right. Nondeform helper/mask groups do not enter the denominator.
Static validated armature/mask/corrective stacks preserve those memberships.

The worker tests actual pose-specific triangles with Blender's BVH intersection
test, not just overlapping bounding boxes. It records every source frame's skin
SHA, full triangle-index SHA, canonical pair digest/count and the unique affected
triangle indices. A separate fresh Blender job reopens the saved scene, repeats
the existing complete raw/corrected skin verification and reproduces the entire
surface/topology report before the application publishes it.
The verifier also returns the actual mesh world matrix; the reader binds the
rendering transform to that fresh result, preventing an otherwise well-formed,
rehashed manifest from moving/scaling the displayed mesh independently.

Manifest V2 binds `motion_contacts.json`; geometry retains the existing binary
format. Legacy V1 caches still load and explicitly have no surface inspection.
The new worker operation `verify_native_surface_review` requires seven exact
hashes and fixed staged filenames. Source, master, map, snapshot, saved scene,
timeline and review artifacts remain bound; cancellation/revision/license guards
cover both cache and surface-verification processes. No original is edited.

The Python reader closes report fields, versions, counts, disjoint rig regions,
complete coverage and annotation bounds. It also verifies each actual cached
triangle buffer against the freshly reproduced index hash. A rehashed in-range
topology substitution cannot retain an apparently valid skin-only cache.
Records become immutable in-memory tuples before GPU use.

Missing/ambiguous weighted branches or excessive review workload produce an
explicit `UNAVAILABLE` status. All skin frames/topology still verify; no partial
or truncated contact result is presented as a successful zero-intersection check.

## Desktop workflow

After **Load verified motion in UCC...**:

1. Read the hand/opposite-arm flagged-frame count.
2. **Next flagged frame** pauses and cycles through affected source frames.
3. **Max pairs** pauses at the largest pair count; this does not rank penetration
   depth or physical severity.
4. **Focus** frames the affected actual skin. Highlighting can be toggled while
   retaining that camera for comparison. Orange faces are the measured triangles.
5. Reset view restores the ordinary camera. Clearing/changing the selected
   character, source, mapping, license or hand scope clears motion/inspection.

## Executed evidence

- Actual owned 300-frame clip: two fresh surface-related processes agree on all
  300 skin/topology frames and 26 flagged frames. No source motion, character
  weights or geometry is corrected by inspection.
- Actual final Windows GPU playback presented all 300 source frames in 10.031 s
  at 30 fps. Navigation pauses/wraps, highlighting renders actual flagged faces,
  toggling preserves focus/geometry and clear disables review. The frame-27
  framebuffer contains 8,926 orange pixels; its cache/scene bytes remain unchanged.
- A real MPFB evaluated-mesh fault injection forces one temporary hand polygon
  through an opposite-arm triangle. Detection succeeds and the original skin and
  scene remain unchanged. Separate controlled triangles reject a bounding-box-only
  false positive. These are non-shipping fault tests, not realistic animation or
  external-pack compatibility proof.
- An actual fresh worker rejects rehashed fabricated intersection records.
  Original bound inputs stay unchanged. The original articulated 300-frame
  T-pose challenge passes complete V2 cache, surface reproduction, pose-specific
  topology checks and the detector/forgery fault contract.
- 510 tests run: 497 pass with 13 Windows symlink-privilege skips; all 15 preflight and
  guardrail tests, compilation and whitespace checks pass. Combined local Windows
  regression passes, including the real surface-fault/forgery contract. The final
  world-transform binding additionally passes a fresh complete 300-frame scene
  verification and negative unit checks. All five final-head CI gates pass at
  `32386fda0e86a64b9fee23f791c80ceee7ee1438`; [PR #47](https://github.com/DocDamage/newestcharactercreator/pull/47)
  is ready for review and unmerged. Its independently downloaded JSON-only
  artifact SHA-256 is `8a84116de29569807c169a15fe06a632e0a01e506caed2eb47507a97c2db05ca`.
  The Linux fault injects nine actual crossing pairs; local Windows injects five.
  Both detect the fault, reject rehashed fabricated annotations and preserve originals.

## Limits and next task

This detects triangle-surface crossings for one declared body-region pair. It
does not certify solid containment, collision-free whole-body motion, correct
grasp/contact intent, gap distance, clothing/prop fitting or engine import.
Touching/coincident surfaces can warrant a flag. Pair counts are not depth.
Missing source body/prop geometry is not invented. Existing joint/strain limits
remain unchanged; all visual/contact/engine approval flags stay false.

No new dependencies or license rights; no paid assets, poses, meshes, caches,
saved scenes or images are uploaded. Next: use these measured frames to test
minimal, explicitly bounded target-side contact correction without weakening
source-rest, quaternion, deformation or rollback verification.
