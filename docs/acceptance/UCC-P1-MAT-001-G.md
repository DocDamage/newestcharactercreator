# UCC-P1-MAT-001-G — material-aware facial playback

Status: implementation and actual desktop/Blender/GPU acceptance verified;
final regression and evidence freeze are recorded below and in the private audit.
The overall creator goal remains incomplete.

Depends on the accepted expression geometry cache and material graph/renderer.
Keep the existing 25-frame geometry and saved-Action verification intact. Add a
separate versioned stream of evaluated loop-corner normals, matched to each
frame's exact triangle order and verified against original-source interpolation
and the reopened saved Action. Carry the physically checked owned material into
the existing playback renderer. No static-normal reuse across deformations.

Touched areas: a pure versioned job contract; isolated normal stage/reopen workers;
bounded immutable material cache; job orchestration; existing expression action,
watchers and renderer. Reversibility: route uncolored characters through the old
path, preserve original masters/metadata and retain private outputs only. No schema
migration, new UI control, dependency, installation, cloud or asset substitution.

Acceptance: all 25 source/saved/cache frames and exact neutral endpoints; unchanged
old geometry hashes; frame-specific smooth normals; actual saved color/roughness
and GPU readback across all frames; changed-expression images and functioning
playback; mutation/fault rejection; cancellation, total deadline and stale-source
checks; unchanged originals/history; full regression and private evidence audit.

Implementation retains the V1 geometry/saved-Action contract unchanged. Two new
closed operations stage and independently verify `UCC_EXPRESSION_MATERIAL_NORMALS_V1`.
Each of 25 frames contains all 80,268 evaluated loop-corner normals in the exact
frame's triangle order. The normal manifest binds the complete original geometry
inputs, color/roughness and each frame's vertex/triangle hashes. The verifier
reproduces original-source interpolation and separately reopens the saved Action;
cached, reference and saved normals must match exactly. It also retains all prior
geometry/support/displacement/neutral-state checks.

The immutable material cache retains the original geometry object, expands only
its drawing vertices to corners, and gives the existing renderer matching normal
buffers for each frame. Decoding bounds the compressed stream at 32 MB and the
expanded position/normal buffers at 64 MB. Head focus changes only camera metadata.
The saved material and frame-specific normals enter the existing local dielectric
PBR shader; uncolored/reference motion paths retain their previous behavior.
The material coordinator shares one deadline and cancellation event across old
geometry admission and both new normal workers. Source/proof/adapter hashes are
checked before display; no metadata, master pointer or history is published.

Private evidence is under `D:/dev/new Character Creator/evidence/export001`:

- `material-expression341` and `342`: actual visible MainWindow, existing
  expression-preview button, normal Qt background workers, real Blender pipeline,
  normal completion handler, and actual GPU playback. Saved colors `#94603d` at
  roughness 0.65 and `#7d513c` at 0.72 remain intact. All 25 frames have exact GPU
  position/index/normal buffer readback and color/roughness uniforms within 1e-6,
  with GL error zero. Both play every frame in 1.157 / 1.172 seconds. Each has 18
  distinct normal buffers and exact neutral position/normal endpoints. Original
  metadata, master files, backup history and session history remain unchanged.
- `expression-corners351` / audit `353`: another fresh Blender process, without
  importing the product samplers, reads positions, triangles and loop normals
  from the same evaluated mesh at every saved frame. All 25 position/triangle/
  normal hashes match both color cases exactly. This checks corner correspondence
  as well as the original/saved comparisons inside the normal workers.
- `material-expression-faults347`: the actual verifier rejects a complete,
  coherently rehashed stream that reuses neutral normals for every frame. It also
  rejects material parameters that differ from the actual saved owned shader.
  A real owned normal-worker child, PID 24752, is observed alive, cancelled and
  stopped. These direct worker checks do not claim a UI cancellation test.
- `material-expression-cancel354`: a separate actual visible MainWindow run uses
  the existing expression button and Cancel action. It observes a live Blender
  child, stops it, adopts no result and retains metadata/backup history. The
  existing expression cancellation handler reports normal cancellation without
  an error dialog. This complements the direct normal-phase worker cancellation.
- `material-expression-watch349`: retained authentic artifacts are replayed on a
  private project copy. Actual file watchers revoke CPU/GPU playback when either
  a material proof or the verified normal stream changes. Both copy files are
  restored atomically and originals remain unchanged. No new Blender run is
  claimed for this replay; its unused inspection handle is not reconstructed.

Neutral, peak-expression, whole-character and application screenshots, plus both
invalidation screenshots, were decoded and visually inspected. A visible mouth/
eye change is observed; artist quality, full eye closure, lip sync and engine
quality remain unapproved. Lighting limitations from the prior static preview
gate still apply; no textures, shadows or Blender render matching are added.

Initial helpers 339/340 failed before worker submission because they used the
wrong widget attribute (`expression` instead of `expressions`). The corrected
341/342 runs use the actual existing button. No healthy job was restarted and
no product assertion was relaxed. All worker/cache/shader changes precede both
successful application runs. A later audit found that the frame label widened
the dock by six pixels between the first and last captures. The cache endpoints
were exact, but those screenshots used different viewport dimensions. Audit 358
failed that pixel comparison and is retained. Reserving the maximum label width
fixes the layout; current-source retained-artifact replay 360 checks all 25 GPU
frames again, with one fixed viewport, matching cameras and pixel-identical
neutral endpoint images. No new Blender worker is claimed for this layout replay.

Focused regression 338: 27 passed. New stream/schema tests 344: 6 passed.
Coordinator tests 345: 4 passed. Current combined tests 348: 10 passed.
Preliminary full suite 346: 1,332 tests, 1,318 passed, 14 existing skips,
265.547 seconds, return code 0. It precedes only the final optional-schema test
import guard; final current-suite results are retained in `full-required-Qt-350`.
Suite 350: 1,332 tests, 1,318 passed, 14 existing Windows
symlink-privilege skips, 197.902 seconds, return code 0. All Python sources predate
that run; it precedes the later frame-label layout fix. Current layout tests 359:
16 passed. Final current-suite results are retained in `full-required-Qt-361`.
Final suite 361: 1,333 tests, 1,319 passed, 14 existing Windows symlink-privilege
skips, 197.990 seconds, return code 0. All Python sources predate this run.
Optional-schema absence is separately tested without installing anything.
Guardrails 352: 12 passed. Pure core imports and diff checks are recorded in the
final evidence manifest. Synthetic fixtures are isolated and are not model proof.

Versions: Python 3.12.10, PySide6 6.11.2, Blender 5.3.0 `02f0899d78e3`, MPFB
2.0.18, RTX 3060 12 GB, OpenGL 3.3.0 NVIDIA 610.88. Exact requests, results, worker
commands/return codes, logs, hashes and renders remain private. Job/result schemas
gain the two additive operations; the character schema and old cache wire remain
unchanged. No dependencies, licenses, NoAI permissions, installations, cloud use,
frozen build or owner-launcher changes.

Reproduce in this source checkout: open a supported saved material-bound prepared
character, save expression strengths, click Preview saved expression strengths,
then use Play, the frame slider and Head focus. The operation is read-only.

The subsequent [desktop Godot export gate](UCC-P1-EXPORT-002.md) now covers the
two authored material cases. Its next task is current private Windows packaging.
The next task recorded at this gate was an explicit Godot export workflow in the normal desktop,
using the already verified source-derived rig/morph/material exporter, per-use
rights admission and reversible destination staging. No source-animation export
or general engine-quality claim should be inferred from a static export.
