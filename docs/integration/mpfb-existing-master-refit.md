# Update an existing MPFB humanoid without rebuilding its rig

**Development change:** [PR #28](https://github.com/DocDamage/newestcharactercreator/pull/28), built on merged PRs #25–#27. The new **Apply saved body controls to existing master...** action uses the documented MPFB target/re-fit API on a **private copy** of the current `.blend` master. No original master is overwritten.

## How to use

1. Open a character that already has a saved MPFB humanoid master (use **Generate humanoid using saved body controls...** first if necessary).
2. Adjust normalized Height, Muscle, and Weight sliders. Save project metadata with Ctrl+S.
3. Choose **Apply saved body controls to existing master...** and confirm the exact saved values.
4. Select your installed Blender executable with the official MPFB extension enabled, if not already chosen this session.
5. UCC stages an independent working copy in `.ucc-jobs/<uuid>/candidate.blend`. Blender checks that it contains exactly one substantial MPFB human, its existing rig, the original bone weight groups and working armature modifiers.
6. MPFB's `HumanObjectProperties.set_value` sets the saved macro values; `TargetService.reapply_macro_details` updates real shape keys; `HumanService.refit` repositions the **existing** armature rather than generating a new rig.
7. UCC measures the evaluated body vertices before and after, verifies the bone/vertex group names and original per-vertex bone-weight fingerprint survive refitting, then saves a **new** uncompressed `refitted_human.blend`.
8. A second Blender subprocess opens the newly saved file, independently verifies the same MPFB macro values, evaluated body coordinates, bone groups, skin weights and final rig rest-pose fingerprint.
9. Only when every gate passes is that file staged to `master/versions/<sha256>.blend`, the saved project revision atomically advanced and the previous master preserved.

If the new values already match the existing saved Blender master, the worker rejects the no-op and no new version is committed. The existing **Preview saved master in UCC...** action can display the new **static geometry** (no real-time slider/animation preview yet).

## Limits and safety

- The values are MPFB's normalized 0–1 phenotype controls, **not** meters, pounds, kilograms or certified anatomical measurements.
- Refitting requires a single recognized MPFB humanoid, one substantial rig, genuine bone weights and matching modifier links. Modified or complicated scenes with uncertain rig provenance fail closed.
- Projects with **attached part or animation references are blocked** for this initial implementation. This does not certify that external clothes, Fab animations or equipment survive refitting.
- All changes are performed on a private, staged copy in an isolated Blender process launched with `--disable-autoexec`. No cloud API, checkpoint download, Fab search, full-disk scan or user script execution is initiated.
- Old masters and project backups are retained. Worker failures leave their private diagnostic logs but **do not** advance the project pointer. Cancellation, symlinks, source digest mismatch, concurrent project edits or lost weights are hard failures.
- Shape-key evaluation plus preserved bone weights/rest-pose relationships are **structural evidence only**. They do not demonstrate proper walking animation deformation, real IK, skin penetration, motion retargeting, engine exports or visual quality.
- Generated or refitted geometry remains `generated_unverified` and cannot become `validated` merely because the worker succeeded.

## Test gates

- Python-only contract/unit tests are synthetic, and do **not** count as Blender proof.
- The [experimental Linux real-Blender workflow](https://github.com/DocDamage/newestcharactercreator/actions/workflows/mpfb-cloud-smoke.yml) now performs: actual MPFB generation with saved macros → independent saved-master reopen → static GLB preview → **update saved macro values** → real `reapply_macro_details + refit` on existing master → independent reopened body/rig verification → new GLB preview with changed triangle positions.
- The integration requires the original master SHA to remain unchanged, a new immutable SHA-addressed master, matching actual body coordinates across the refit/reopen, the same per-vertex bone weights and bone names, and a new source GLB mesh with changed positions.
- Real Windows 11 Blender/MPFB compatibility and skinning under animated poses are still **separate acceptance gates**. A Linux pass cannot substitute for them.

**Next task:** a real deforming-bone pose smoke and source-to-target rig/skin visual review, followed by game-engine reimport checks, rather than calling an intact skeleton an animated character.
