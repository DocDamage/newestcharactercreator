# UCC-P1-ANIM-006D — audited basis conversion and private rendered review

Based on merged PR #37, main `6e765d817134864db4019fd5cebb0c986395ce30`.
This additive opt-in applies supplied source bone frames in an explicit,
audited change of coordinates, then renders actual evaluated skin privately.
It preserves the existing XYZ BVH first-frame-relative motion convention.

## Defined mathematics

Convention identifier: `BVH_XYZ_FIRST_FRAME_DELTA_TO_BONE_V1`.
Matrices multiply column vectors; transpose is the inverse for validated SO(3).
For each mapped joint and every source frame:

```
R0, Rf = ordered XYZ BVH channel matrices at first/current frame
S      = supplied bone-rest axes -> native BVH zero-channel rest coordinates
B      = actual Blender target bone-rest axes -> target coordinates
C      = existing measured shared source -> target calibration
D      = R0.T * Rf
Db     = S.T * D * S
T      = B.T * C * S
Dt     = T * Db * T.T
```

`Db` is the existing channel delta expressed in the supplied bone basis. `Dt`
actually drives the keyed target quaternion. Every conversion must satisfy
`S * Db * S.T == D` and `Dt == B.T * C * D * C.T * B` within 1e-5 maximum element
residual. Thus **S cancels in target motion**. Directly substituting S for BVH
channel axes would change the motion incorrectly. This implementation does not
claim a new source-roll correction, full global FK/parent compensation, A/T-pose
alignment or support for arbitrary exporter channel conventions.

Per-joint ordered traces hash every frame number (little-endian uint32) and
row-major D/Db/Dt entries quantized to 1e-6 (little-endian signed int64). Traces
follow the SHA-bound mapping order; no redundant names are sent. Raw residuals
are measured before quantization. Two workers must agree on all traces,
residuals, source intake, skin hashes and existing quality evidence.

Descriptor v1 remains `BONE_REST_AXES_ONLY`; its intake evidence stays
`validation_only=true`, with channel interpretation/source roll approval false.
Separate `source_frame_conversion` evidence declares the coordinate operation,
its fixed convention and source-profile/mapping SHA bindings. It explicitly says
`target_motion_changed_by_source_roll=false`. No existing approval flag changes.

## Private rendering contract

- Audit requires an explicit SHA-bound source descriptor; rendering requires the
  audit. Existing no-descriptor/validation-only diagnostics remain supported.
- First worker renders **15 PNGs**: front/side/quarter views at five distinct
  first/quarter/middle/three-quarter/last frames. The second independently audits
  without rerendering. Every frame still receives numerical skin/quality checks.
- CPU Cycles, eight samples, 256×384 RGBA8 clay, transparent background, stable
  orthographic framing over sampled world bounds. Actual evaluated meshes are
  copied into an isolated render scene with camera/lights/materials; those
  datablocks are removed and source frame restored. Rig/rest/weight fingerprint
  must remain unchanged. GPU selection or extra Python packages are unnecessary.
- Private job `review_frames/index.html` and manifest bind original BVH, source
  descriptor, staged master, saved review Action SHA and conversion convention.
  Each image binds frame/view, actual evaluated-vertex SHA, file SHA/bytes and
  measured silhouette count/bounds. Five-frame coverage is not full-frame visual
  inspection or human approval.
- App independently verifies bounded regular local artifacts and decodes all PNG
  pixels with stdlib zlib/CRC/filter validation. Reject blank/low-contrast images,
  edge clipping, malformed/oversized/deep JSON, missing/repeated still views,
  wrong frame/skin/provenance, tampering and symlink redirects.
- Static HTML has no scripts or external resources. No automatic browser launch,
  source save, authoritative revision, asset upload or media CI artifact. Existing
  JSON-only Actions summaries remain the sole integration diagnostic upload.
- Existing cancellation, timeouts, SHA checks, stale revisions, rights enforcement
  and partial-Action rollback remain active. Render errors fail the diagnostic;
  incomplete private files never become authoritative project state.

## Verification and reproduction

Baseline: 375 tests OK (12 Windows symlink skips), Python 3.12.10 with existing
PySide6 6.11.2 through process-local package paths. No installation performed.
Local suite: **389 tests OK, 12 Windows symlink skips**, including 27 actual Qt
widget tests; **15 preflight/guardrail tests pass**. Actual Windows Blender
5.3.0 ten-bone run verified all 25 frames, two-worker audits, independent audited
Action reopen, 15 rendered images, original-byte preservation and existing
negative-path quality/hierarchy/partial-Action cleanup. Maximum roundtrip
residual was 5.56e-16 and target-equivalence residual 6.67e-16. Local logs and
private outputs are under `%TEMP%/ucc-anim006d-render-final`; final-head
five-workflow evidence belongs in the PR.

New tests exercise nonzero/noncommuting channel rotations, independent target
rest axes, source-roll invariance with different bone trace, improper matrices,
sequential frame coverage, bindings/false claims/residuals, worker disagreement,
all five PNG filters, CRC/truncation/decompression limits, clipping/blank pixels,
manifest/provenance corruption, UI consent/dispatch/errors, machine schema and
64-joint/240-frame wire capacity without increasing the existing 256 KiB cap.

```powershell
$env:PYTHONPATH='src'
py -3.12 tests/run_branching_blender_contract.py `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --humanoid-names --output "$env:TEMP/ucc-conversion-private-new-run"
```

Actual local Blender 5.3 uses the clearly labeled non-shipping ten-bone skinned
sphere fixture; it is not MPFB/Fab evidence. Genuine MPFB CI exercises the same
coordinator on the generated 36-joint body tree, renders privately, compares all
25 skin frames and independently reopens the audited Action for quality checks.
Original BVH, rest descriptor, master, project metadata and both private Actions
must retain their bytes. Only synthetic local framing has been manually viewed;
automated MPFB image checks do not establish human visual acceptance.

No dependency/license changes, installs, asset scans/downloads or engine imports.
Reverting this change requires no project migration.

**Next task:** inspect an authorized actual source rig/rest export and BVH clip,
using its local preview license, then review the private Action and rendered
joint deformation. Independently establish exporter conventions before adding
rest-pose/FK correction; do not infer compatibility from synthetic CI motion.
