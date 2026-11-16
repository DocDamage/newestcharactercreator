# Unity same-human numerical observations

This record covers the 178 private, original-authored diagnostic states. It is
not Unity product export acceptance or a claim about arbitrary animation.
Blender 5.3.0 build `02f0899d78e3`, MPFB 2.0.18 and Unity 6000.4.5f1 were already
installed. Unity observations use Direct3D 11, unlimited skin influences and
Linear color space. No installation, package acquisition or asset upload occurred.

## Inputs and reproducible records

Private records live under the existing local `evidence/export001` directory:

- `unity-source-operands491`: actual pre-armature positions, raw deform weights,
  channel matrices and object-space conversions for all 178 states. Re-enabling
  the armature reproduces capture 470's positions byte for byte. The editable
  master and its full nonmaterial state are unchanged.
- `unity-poses499/project`: actual native base vertices, twelve morph deltas,
  bind poses, all 163 bone matrices, root/renderer inverses and parent/local TRS
  factors. CPU and post-render GPU positions are observed independently.
- `unity-source-roundoff502.json`: all-source-vertex arithmetic audit, with
  scalar interval checks on selected endpoints/worst vertices in each state.
- `unity-native-roundoff501.json`: complete CPU/GPU observations against the
  declared native arithmetic envelope, including matrix formation.
- `unity-complete-precision503.json`: composed terms and the independent spatial
  cap, covering 5,168,052 vertex comparisons.
- `unity-position-fault505.json`: real GPU fault rejection; no synthetic model.

Scripts retain commands, process results, logs and failed attempts under their
numbered names. Read receipts and source hashes before reproducing; never run
these private probes against a different master under the same output name.

## Arithmetic contract

The generic first-party `ucc.export.f32_bounds` module has no Blender, Unity,
Qt or model-runtime imports. Its declared arithmetic uses finite binary32
round-to-nearest operations and gradual underflow. It rejects possible overflow,
including overflow hidden by later cancellation, and divisors whose bounds
contain zero. It does not certify an opaque engine implementation by itself.

For unit roundoff `u = 2^-24`, use `gamma(k) = k*u/(1-k*u)`. An n-term dot product
has at most n products and n-1 additions. Widen its real interval by
`gamma(2*n-1)` times the absolute sum of products, with a separate subnormal term.
This covers different addition orders and fused operations. Using the absolute
sum matters: cancellation can make the result small while intermediate error
remains significant. Binary64 interval endpoints are rounded outward.

The source check uses actual pre-armature inputs rather than reconstructing
shape-key evaluation from an assumed formula. The pinned Blender source uses a
weighted displacement accumulation followed by division by total influence.
Object/armature conversions are included. The profile checks linear skinning,
one bone segment, no envelopes, no multi-modifier blending and no armature mask.
See the [build-specific implementation](https://github.com/blender/blender/blob/02f0899d78e3/source/blender/blenkernel/intern/armature_deform.cc).
No Blender implementation source was copied into the product.

The native reference envelope covers base/morph input arithmetic, four affine
dot4 chains and complete influence accumulation. The latter contributes
`4*7 + (2*n-1)` roundings along the declared path. Absolute matrix products retain
cancellation sensitivity. Actual root/renderer inverse matrices are operands.
The native implementation's proprietary source and its generic subnormal
behavior are not proven; actual CPU/GPU results must satisfy the envelope.

World coefficients also require a formation term. For a hierarchy of d captured
local matrices, `gamma(7*(d-1))` times their absolute product bounds the declared
matrix-product chain. Add the independently observed coefficient difference
between the public world matrix and the product of the local factors. Propagate
this coefficient interval through bind/input/root factors before comparing
positions. This term uses transform operands, never position residuals.

The first native model omitted formation and failed near the symmetry axis by
up to 3.531e-10 m in individual components. Typed binary32 JSON decoding did not
resolve it. Failed 496/497 and inspection 498 remain recorded. The formation
model 501 passes all observed components; no fixed positional epsilon was raised.

## Composition and the quality cap

Normalize the original deform weights and retain every positive source bone.
The existing UNORM16 proposal bounds native weight storage; it does not assert
an undocumented packing order. Its old weight-only plus 1 µm deformation helper
is unchanged and remains insufficient as a complete engine criterion.

For each vertex, compose:

1. Actual weight differences acting on the original posed bone points. Center
   the points at one bone and retain the unit-sum remainder separately.
2. Input/bind transfer, including the prepared neutral bake.
3. Source/native operator transfer and root translation's unit-sum remainder.
4. Source evaluation roundoff derived from actual operands.
5. Native evaluation and hierarchy-formation roundoff.
6. Binary64 audit-expression rounding, independent of observed position error.

The resulting bound must contain the observed source/native difference. Also
require the observed difference to be at most **50 µm**, regardless of how broad
the arithmetic bound becomes. These are separate conditions. No measured maximum
residual is reused as an acceptance tolerance.

Audit 503 passes every CPU/GPU vertex comparison in all 178 states. The maximum
observed error upper bound is 3.599131 µm. The largest conservative bound is
784.848 µm; it does **not** promise that an untested pose meets the quality cap.
Observed states still need their direct 50 µm test. The minimum bound margin is
8.938 µm. Source arithmetic alone has a maximum observed residual of 0.204 µm
inside an operand-derived bound of at most 4.512 µm.

Actual GPU fault 504 changes one copied position by 100 µm in root space. Its
source difference is 100.076360 µm, inside that vertex's 487.098 µm numerical
bound. The unchanged 50 µm gate correctly rejects it in 505. Exactly one GPU
position record changes; native inputs, pose matrices and saved assets remain
unchanged. A loose numerical envelope cannot grant spatial-quality acceptance.

Post-render normal audit 507 repeats the earlier result: at most 0.190131° over
all 178 states, with every unmodified native position byte preserved. The prior
real constant-normal fault remains rejected. This is numerical/diagnostic
evidence, not artist approval or public-distribution permission.

## Remaining product work

The closed request/source contracts and the persisted runtime component now have
[fresh saved-project observations](UCC-P1-UNITY-001.md), without editor repair of
weights, axes, materials or source inputs. Automatic per-camera updates cover
rigid placement and two-camera/lifecycle cases. Root-space normal computation
fixes the world-space cancellation fault; the older 507 normal maximum describes
its earlier prototype. The standalone transaction, runtime cost, player builds
and broader rendering still need work before exposing a desktop export control.

The transaction must retain per-input Unity export permission, NoAI/source
privacy, revision/hash invalidation, cancellation, timeouts, collision rejection,
rollback and immutable originals. Recheck all delivered animation states rather
than generalizing these 178 diagnostics. Run actual fault/reopen tests, normal
desktop export and a current frozen package before claiming product acceptance.
