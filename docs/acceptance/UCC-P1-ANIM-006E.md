# UCC-P1-ANIM-006E — private native FBX source intake

Based on merged PR #38, main `9ae588af96fae06b76e1d2048d7b4fb7f11f8657`.
The authorized project `animations` folder contains FBX and Unreal assets rather
than BVH/rest sidecars. Native intake measures those files directly; the owner
does not need to author technical metadata or convert the files manually.

## Implemented contract

- Additive protocol-v1 `inspect_fbx_animation`: no target master or arbitrary
  input paths, one exact source SHA option and fixed staged `source.fbx`.
  Regular non-symlink source, at most 256 MiB; worker rechecks SHA before/after.
  Existing BVH operations and limits remain unchanged.
- Native Blender FBX import uses fixed options, disabled auto-execution, no bone
  reorientation/forced connections/leaf deletion/custom properties/image search.
  Explicit image loading is intercepted and rejected before external reads.
  Image-bearing sources, including embedded images, currently reject.
- An **unanimated import** captures the imported armature bind/world matrix. A
  separate animated import must yield identical bone rest matrices. Frame 1
  may already carry root/hip motion and is not substituted for the bind pose.
- Require one armature and one bound Action, no NLA/drivers/constraints. Multiple
  takes/armatures reject rather than silently choosing. Preserve all bones in
  parent order, multiple roots and the armature object's animated world matrix.
- Evaluate every integral frame: 2–2,400 frames, at most 256 bones and 100,000
  bone/frame states. Fractional endpoints, excessive clips, static motion and
  nonfinite/singular/reflected/sheared transforms reject. No crop or resampling.
- Private `source_snapshot.json`, at most 64 MiB, stores actual 4×4 row-major
  bone-rest matrices/endpoints, armature bind/world matrix, every frame's object
  matrix and bone poses, Action range/fps/import settings and source SHA.
  Per-frame hashes cover object then ordered bone matrices, quantized to 1e-6
  and encoded as little-endian signed int64 values.
- Pure app validator independently checks all values, affine/handedness/axis
  checks, rest head/tail/orientation consistency, names/parent order, exact frame
  coverage and recomputed pose digests. Strict fields/types and rejection of
  duplicate/nonfinite/deep/oversized JSON. Summary counts/timing must match.
- Two independent Blender jobs must agree on the entire snapshot and report.
  Original/staged SHA checks, final first-artifact recheck, cancellation and
  existing worker timeouts apply. No original/master/project mutation/promotion.
- Reviewed local-preview rights are required; UE-only/unreviewed sources reject.
  Policy accompanies the local result. No AI/distribution/engine rights inferred.

Convention: `BLENDER_FBX_ARMATURE_POSE_MATRICES_V1`. These measure Blender's native
interpretation, not independent exporter certification. No BVH axes are generated
from the bone matrices. Retargeting/visual/engine approval flags remain false.

## Desktop and CLI

Select an FBX in Animation library, enter provider/license/source, confirm local
rights, and use **Inspect selected file**. Choose installed Blender once if
needed. Cancelable background work reports complete bone/root/frame counts and
the private snapshot. BVH/glTF inspection remains unchanged. FBX catalog indexing,
target retargeting and in-UCC animation playback are not claimed by this intake.

```powershell
$env:PYTHONPATH='src'
py -3.12 -m ucc.cli inspect-fbx 'selected-animation.fbx' `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --jobs 'private-project/.ucc-jobs' --policy-file 'reviewed-local-policy.json'
```

## Actual verification

- Baseline 389 tests OK, 12 Windows symlink skips. New suite **402 tests OK, 12
  skips**, including **29 actual Qt tests**. All 15 preflight/guardrail tests pass.
- Actual owner FBX: **76 bones, three roots, complete 300 frames at 30 fps**,
  identical independent snapshots, original bytes preserved. All **30 clips** in
  the pack with an included local-use README passed complete source intake.
  This is not 30 retargeted/accepted animations. That README allows personal and
  commercial projects and prohibits standalone raw redistribution; AI remains
  disabled. Owner files/snapshots/paths remain outside Git and cloud CI.
- Owner-authorized setup downloaded official MPFB **2.0.18**, GPL-3.0-or-later,
  45,956,992 bytes, verified against Blender registry SHA-256
  `c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad`.
  Project-local profile/data/download provenance live outside Git. No new app
  dependency is added or extension redistributed.
- Actual Windows Blender **5.3.0** generation/refit/reopen and existing
  deformation/timeline/36-joint audit/private-render checks passed: **19,158
  vertices, 163 rig bones, 26,756 measured edges**, 25 measured frames and 15
  images. This does not prove owner FBX retargeting. The coordinator now records
  `runtime_platform`; legacy Linux status strings remain for compatibility.
- A private owner project/launcher opens the generated immutable master with an
  actual selected FBX. Qt smoke loaded the project and static preview. Its first
  screenshot exposed absent Windows offscreen fonts; the private launcher loads
  installed Segoe UI explicitly and was visually rechecked. No font redistributed.
  A separate actual Qt FBX inspection completed both workers and all 300 source
  frames; the owner project's metadata SHA stayed unchanged.
- Real-Blender CI authors an original non-shipping three-bone/two-root FBX with
  **300 frames and 0.897 world-unit root travel**. Both workers must preserve it;
  ambiguous takes and actual image resources reject without changing originals. It is not a humanoid or
  purchased-pack fixture. Only the existing JSON transaction summary is uploaded.

Public asset-free gate, with a new output directory:

```powershell
py -3.12 ci/verify_fbx_source.py `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --output 'private-new-native-fbx-contract'
```

All five workflows must pass final PR head; exact evidence belongs in the PR.
No purchased files, snapshots, screenshots or masters are committed/uploaded.
Reverting requires no project migration.

**Next task:** explicit source-to-MPFB full-body mapping/rest-pose correction from
these native bind/object/pose transforms, preserving root motion and helper-bone
hierarchy compensation, then private rendering of an actual licensed clip.
