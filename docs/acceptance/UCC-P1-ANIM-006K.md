# UCC-P1-ANIM-006K — explicit hand and finger poses

## Scope

The measured Hips-object family can opt into 59 mapped roles: 21 existing body
roles plus 38 hand roles. Each side has three thumb phalanges, four metacarpals
and three phalanges on each remaining digit. Non-thumb source joint 1 is a
metacarpal; joints 2–4 are phalanges. The wrist ray ends at the actual middle
knuckle when hands are included.

**Include hand and finger poses (experimental)** defaults off. Changing it clears
reviewed selection and cached motion. Explicit maps define their own scope and
disable this automatic option. CLI: `preview-fbx --include-hands`; combining it
with `--mapping` rejects before source intake. Existing maps remain unchanged.

No new rest convention, palm-roll inference, dependency, schema, smoothing or
safety threshold is introduced. Every added role must pass existing hierarchy,
rest orientation, quaternion, weighted-skin probe, full-timeline deformation and
independent saved-copy checks. Incompatible hands fail without silent fallback.

## Executed owner evidence

- The licensed local bandaging FBX passes all 300 frames with 59 mapped roles,
  58 independent visible-skin probes and 18 omitted source bones. Two workers
  agree; required saved-copy verification plus an additional independent reopen
  reproduce corrected/raw skin and both neutral references. Fifteen body views
  and six hand close-ups were rendered privately. Original source/master/project
  and saved review bytes remain unchanged. No owned geometry/poses are committed.
- Actual Windows UCC played the complete 300-frame cache at 30 fps in 10.016
  seconds. Timed playback observed 298 distinct frames; five source-frame scrubs
  passed. The source clock can skip late display frames. Changing the hand scope
  cleared motion. Playback uses precomputed Blender skin, not live skeletal FK.
- **The owned clip holds its finger poses fixed.** Parent-relative measurements
  find less than 0.002 degrees on every hand role, consistent with numeric noise.
  This verifies held finger poses/inherited hand motion, not articulated finger
  animation-pack compatibility. Close-ups include arm/body occlusion; grasp and
  contact quality are not approved.
- Private palm-normal and under-specified T-pose-hand experiments tripped wrist
  or thumb twist guards. Neither convention ships; no limits were raised.

## Regression gates

The original non-shipping CI hand challenge retains measured MPFB A-pose hand
anatomy with independent source bone rolls. Every hand joint animates; the
300-frame clip starts in a posed torso/leg state, travels four meters and turns
more than 400 degrees. Separate existing body gates retain T-pose conversion.
Parent-relative metrics require every hand role to move more than one degree;
inherited wrist motion cannot satisfy this assertion. This source is not copied
paid motion and is not pack-compatibility evidence.

Tests cover exact anatomical role/tip ordering, unsupported topology,
nonboolean/conflicting scope, generator dispatch, original immutability, UI
invalidation, explicit-map ownership and inherited-motion negatives. Current
suite: 485 tests, successful with 13 Windows symlink-privilege skips. All 15
preflight/guardrail tests, compilation and whitespace checks pass. Full combined
Windows Blender regression and all five final-head CI gates passed on
`1a890a8d4a63b01021f6aaac5e149e2b1205e4f9`; [PR #45](https://github.com/DocDamage/newestcharactercreator/pull/45)
contains the verified artifact digest and run links. Main is unchanged.

## Remaining limits and next task

Arbitrary palm/rest-roll compatibility, finger IK, grasp fitting, collision
repair, face/toe mapping and engine-portable corrective skin remain unverified.
License/NoAI restrictions and export blocks remain enforced. Next: measure and
improve actual hand contact without weakening joint or mesh limits.
