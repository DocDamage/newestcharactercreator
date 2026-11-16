# Unreal acceptance — finite static bind baseline

Updated November 16, 2026. The complete locked blueprint remains active.
This record admits a private static character profile; it does not close the
Unreal product, animation, rendering, player or release requirements.

## Accepted actual baseline: UCC-P1-UNREAL-006

Installed Unreal `5.9.0-60351404+++UE5+Release-5.9` imported the original-authored
MPFB character through the dedicated skeletal FBX profile. A second process
loaded a separate byte-identical project copy and captured native data without
explicit import, build, repair or save. Both actual processes exited zero under
NullDrv. No source reference vectors were supplied to Unreal.

- Original source: 13,380 visible vertices, 26,756 triangles, 163 bones and twelve
  canonical morphs. Native mesh: 14,517 vertices after required splits.
- All thirteen independent field gates pass: complete correspondence, exact
  oriented triangle/UV multiset, bone identities/order/parents, full original
  bind and inverse-bind witnesses, every positive influence, raw 16-bit storage,
  bounded weight error, all morph positions, corner normals, material values and
  direct graph, bounds/Nanite settings, and exact saved/reopened readback.
- All four saved asset files remain byte-identical. The independent audit
  rehashed 6,350 protected file bindings and four explicit private per-use
  permissions. Fourteen in-memory actual-observation tamper cases reject.
  These are host observation faults; no live engine asset fault was injected.

Spatial caps remain two micrometres for correspondence/bone heads, one
micrometre for morph positions, fifty micrometres for full-bind world witnesses,
and 0.5 degrees for normals. Weight admission uses the cap declared before
native residuals: `(n+2)/65535 + 32*2^-24`, with at most eight positive influences.
Its source-derived operator bound is conditional on the pinned precise-FP
profile. Stock V8 Editor receipt/source policy and the actual observer response
file support that profile; stock per-translation-unit instruction verification
and arbitrary fast-math guarantees are not claimed.

Two verifier assumptions were corrected from installed source, with original
failures retained: Blender emits a mesh-only bind pose alongside the full
skeleton pose, and Unreal's modern imported sphere uses the farthest point from
the box centre while extended bounds use the box diagonal. No original/native
data, source transforms, bone bases or numerical caps were adjusted to pass.
Distinct-radius and swapped-radius rejection tests cover the bounds correction.

Private evidence identifiers: `unreal-native-bind006`, root request `5a0ad9fe…`,
independent final report `4d6081d8…`, primary admission
`primary-finite-admission.json`. The prior failed attempts, unmodified native
buffers and source references remain local. None is a shipping asset or CI input.

## Production workflow: UCC-P1-UNREAL-007 — in progress

The next complete workflow is saved character → explicit Unreal source/rights
review → installed editor/toolchain preflight → portable scene/rig/morph/material
project → source/native fresh admission → sealed new-folder publication → final
delivered-project read-only verification → truthful desktop completion.

The request binds the exact project/revision, source closure and per-use rights,
editor, engine build and selected compiler toolchain. One parent deadline and
cancellation flag must cover source preparation, compilation, import, reopen and
final verification. Publication must remain atomic without replacement and
support ownership-checked rollback after late failures.

Delivery will enumerate the derived content, portable project/configuration,
same-hash derived FBX and portable metadata. Verification plugins, private source
references/native observations, original Blender or purchased sources, caches
and absolute private staging paths must be excluded. The accepted diagnostic
project is evidence, not a ready-made deliverable: its imported asset metadata
and verification configuration include private paths. Production must create
portable provenance before native admission and verify the actual delivered bytes.

First-party observer sources will compile privately with supported existing
tools; the scalar SDK fixture and vendor SDK sources/binaries are not bundled.
Missing or unsupported tools must fail actionably without installation or a
fallback to a compiler explicitly banned by Unreal.

Open acceptance gates: generalized production source/engine/transaction,
ordinary desktop and current frozen-app positive/failure flows, live engine
faults, final-head CI/artifacts, and integration. Shader compilation, GPU
deformation/rendering, animation clips, PIE/player, exact SDK pose-selection
route, visual/artist approval and distribution review remain separate work.
