# UCC-P1-ANIM-006O — fitted skin playback and original comparison

## Scope

A verified fitted Action previously had targeted rendered views but could not
play in UCC. This slice exports a distinct fitted full-surface cache and adds
an original/fitted comparison using the existing GPU viewer. The source FK
result, saved character and animation remain unchanged. Fitting is still a
manually declared bounded target correction, not automatic contact repair.

## Implemented behavior

- `cache_native_fit` accepts nine exact SHA-256 bindings and fixed staged names.
  A fresh Blender process reproduces the complete canonical saved-Action report,
  including corrected/raw skin, all mapped poses, rest/roll, exact weights,
  topology, modifiers and surface checks before exporting any playable result.
  Unavailable or nonzero checked hand/opposite-arm crossings reject.
- Every source frame exports actual float32 vertices and pose-specific uint32
  triangle indices, with bounded zlib chunks. Packed and full uncompressed
  workloads each remain at most 256 MiB. Geometry-count changes, failed hashes,
  incomplete sequences and existing output files reject; no frame cropping.
- The closed `FITTED_VERIFIED_SKIN_CACHE_V1` manifest binds the fitted scene,
  policy and canonical report separately from original-source cache contracts.
  The application checks every decompressed skin hash, triangle hash, root
  trajectory, world matrix and timing before retaining immutable bytes.
- `prepare_fitted_playback` rechecks local-preview rights, project/revision,
  source/master/policy/evidence hashes, staged inputs and cancellation throughout.
  `prepare_fitted_comparison` uses both guarded original and fitted coordinators;
  a failed preparation never returns a partial pair.
- The viewer's Original motion / Fitted motion selector shares the source frame,
  playback clock, orbit, pan and zoom. Switching updates the actual GPU buffers
  and surface report. Intersection focus resets when switching. Incompatible
  timing, root trajectories, world transforms or character counts reject.
- Comparison publication requires the current original preview and local rights.
  Watched source, master, project, source evidence, fitted scene/report and policy
  changes clear both caches. Dirty/reselected projects retain no stale playback.

## Executed local evidence

- Python 3.12.10, Blender 5.3.0, MPFB 2.0.18, PySide6 6.11.2 and RTX 3060.
- 563 tests: 550 pass, 13 Windows symlink-privilege cases skip. All 15 earlier
  preflight/guardrail cases, compilation and whitespace checks pass. Additional
  focused Qt publication, schema and closed-protocol checks pass after the final
  background-job publication wiring. Optional schema absence is tested explicitly;
  application/worker protocol checks continue to execute without that library.
- Actual owner fitted-cache job `07ccd716-e487-418a-9918-dd3cf1a6b7ef` passes
  fresh saved-scene remeasurement and all 300 application geometry/topology checks.
  Its immutable packed geometry is 76,406,374 bytes. Source/master/project bytes
  remain unchanged. This run took approximately 159 seconds.
- Actual desktop comparison shows different original/fitted GPU geometry at the
  same source frame 8 and camera. The original has 26 flagged frames; the fitted
  result has zero under the specific hand/opposite-arm triangle policy.
- GPU observation records all 300 fitted frames rendered in 10.0 seconds at
  30 fps. The external clock poll sampled fewer updates, so it is not used as
  evidence of rendered coverage; successful actual GPU draw identities are tracked.
  Changing a watched private policy copy clears both caches and stops playback.
  Actual original inputs remain unchanged throughout.
- A private copy of the actual cache was altered at frame 8 by reversing one
  valid-range triangle. Skin bytes remain unchanged; compressed-frame, binary
  and manifest hashes were recomputed. The application still rejects its
  topology against the independently measured saved scene. Original cache bytes
  remain unchanged.
- The separately generated original-source/real-MPFB fitted scene also passes
  fresh cache export and all 300 application vertex/topology checks in job
  `a832c2bb-9adb-4973-a8ef-eb42a460d771` (75,125,402 packed bytes, 156 seconds).
  All bound original and staged input bytes remain unchanged.
- A project-local owner launcher loads the already verified private comparison
  without asking the owner to edit policies. It checks the reviewed local license,
  saved revision and original/canonical input hashes before publication. Its real
  Qt/OpenGL smoke check passes. It is an owner-specific convenience outside the
  repository, not a general asset discovery or automatic fitting feature.

The Linux native-fitting integration additionally exercises the new production
cache coordinator on its original non-shipping, articulated 300-frame source and
real MPFB character. Remote exact-head results remain pending until recorded on
the pull request. This original source is not evidence of external pack compatibility.

## Limits and next task

The owner trajectory remains manually declared. Zero checked triangle crossings
does not prove volumetric clearance, whole-body collision, finger articulation,
grasp intent, prop contact or visual acceptance. Bound corrective Blender skin
is not an engine-portable correction. Contact, visual and engine approvals remain
false. No new dependencies, asset downloads, license rights or private uploads.

Next: derive a bounded candidate fitting trajectory from the measured source
contact interval, retain every existing full-sequence and fresh-process guard,
and expose one understandable local fitting action with explicit rejection states.
The current comparison remains usable while that producer is developed.

## Remote gate progress

Core, Qt, preflight and Windows packaging pass on head
`9a4691137354e5582655dbbf904542d8029824fb`. The Linux native-fit matrix job
passes all seven scene/report negatives and all 300 fitted cache buffers. Its
five-file JSON-only artifact `14007689529` was independently downloaded and
verified at SHA-256 `02279781f730b4c5a74bb159832f3ca3877881af28b3dc6f9b657b4346cb4460`.
The legacy matrix job initially failed at the official Blender download (HTTP
403), before executing tests. Its isolated retry has downloaded successfully
and is running the unchanged regression. PR #49 remains draft until that
final gate and its JSON artifact are verified.
