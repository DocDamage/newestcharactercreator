# UCC-P1-ANIM-006I — verified cached skin playback inside UCC

In development, stacked on PR #42. Keep main stable; never merge automatically.

The vertical slice is an interactive, full-surface 3D animation player for the
existing verified native body result. Blender evaluates the real saved Action;
UCC displays its precomputed skin, not live retargeting or engine-ready animation.
No new dependency, installation, asset download or cloud upload is needed.

## Acceptance

- A closed SHA-bound worker operation reopens the saved corrected animation,
  reproduces its complete prior evidence, then exports every visible evaluated
  vertex and each frame's actual triangles. Blender can change a quad's diagonal
  with pose, so a constant triangle buffer must not be assumed.
- A bounded private binary cache preserves actual float32 local coordinates,
  per-frame topology, frame rate, world transform and hip trajectory. Every frame
  must independently match its measured skin SHA; incomplete, redirected,
  malformed, nonfinite, oversized and corrupted caches reject before GPU upload.
- Source/master/map/snapshot/review/timeline identities, local-preview licensing,
  saved-project revision, cancellation and original-byte checks remain required.
  Partial or stale output is never published. Existing GLB viewing is preserved.
- UCC provides play/pause, source-frame scrubbing, looping, orbit and zoom, using
  monotonic elapsed time rather than assuming timer callbacks match source fps.
  Clear cached motion on project/source/map/character changes. Missing GPU support
  produces an actionable error without replacing the existing static viewer.
- Run unit/negative/coordinator/Qt checks, actual Blender full-clip cache tests,
  actual owner GPU playback and cancellation/immutability tests. All five CI
  workflows must pass on final PR head. Original CI clips are not Fab proof.

## Limits

Materials/textures, fingers/face/toes, contact correction, arbitrary skeletons,
live retargeting and engine exports are outside this slice. Cached playback
does not approve visual quality. Preserve the current knee-angle rejection.

## Executed local evidence

- Windows Blender 5.3.0 / official MPFB 2.0.18 reopened the actual licensed
  walking review and exported all 300 frames, 13,380 visible vertices and 26,756
  actual triangles per frame. All skin hashes match the independently measured
  timeline. The complete packed surface is about 72 MiB; preparation takes
  roughly 80 seconds here, including full saved-scene verification.
- The actual Windows Qt desktop completed preparation through its existing
  cancellable background worker. The owner RTX 3060 displayed **all 300 distinct
  frames in 10.031 seconds at 30 fps**, then scrubbed frames 1/75/150/225/300.
  Full-surface images were captured privately. A monitored input timestamp change
  cleared cached motion; original source timestamps were restored and all
  original file bytes stayed unchanged.
- A separate real OpenGL 3.3 framebuffer test drew all 300 actual skin frames,
  with no GL errors and five distinct substantial foreground images. This is
  execution evidence on the owner's hardware, not a cross-hardware FPS promise
  or full visual/contact approval. No PyOpenGL or new runtime was installed.
- An actual Blender cache worker was cancelled after it began writing partial
  skin data. No manifest/success was published; source/master/project and all
  private staged originals remained byte-identical.
- Unit/negative/coordinator/Qt tests cover wrong identities/approvals, incomplete
  saved reopening, bounded decompression, concatenated streams, malformed JSON,
  nonfinite/forged coordinates, invalid indices, frame gaps/overlaps, source-fps
  timing, adaptive triangles, immutable in-memory bytes, stale revisions,
  cancellation, original/staged mutation, transport controls and GPU error text.
  Synthetic fixtures are small, original and never presented as Blender proof.
  Current suite: **471 tests run**, success with 13 Windows symlink-privilege
  skips, including 36 desktop widget cases plus three motion transport cases.
  All 15 preflight/guardrail cases, compilation and whitespace checks pass.
- The combined Windows regression and all five exact-head CI results will be
  recorded after completion. The original corrective CI case now also exports
  and independently validates every cache frame. Its JSON reports geometry/fps
  counts only; binary surfaces, transforms, scenes and images stay private.

## Operator workflow

Complete **Test selected FBX on saved character...**, then select **Load verified
motion in UCC...**. Preparation is cancellable from Character → Cancel current
Blender operation. The animation dock has Play/Pause, source-frame scrub and
Loop; drag to orbit, right-drag to pan, wheel to zoom, Reset view to recenter.
The View menu can reopen a hidden motion dock. Static GLB viewing remains
available separately. Changing source/map/license/project/character clears the
private motion; bound originals are monitored for replacement or changes.
