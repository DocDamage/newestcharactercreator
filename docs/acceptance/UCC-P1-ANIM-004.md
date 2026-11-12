# UCC-P1-ANIM-004 — BVH ↔ MPFB rest-space rotation calibration

**Status:** Acceptance contract for the next incremental PR after merged #32. Do not interpret these gates as already passed. Intended targets: existing MPFB `humanoid.v1`, Blender 5.3, private reviewed BVH, Python 3.12+ UCC core, Windows 11/PySide6.

## Definition of done (hard gates)

| ID | Required acceptance | How to prove / reject |
| --- | --- | --- |
| AC-01 | **Reviewed, user-selected local source** | Existing `LicensePolicy.allow("local_preview")` succeeds explicitly, no UE-only source, source SHA-256 unchanged, no source upload or implicit scan. Malformed/oversized BVH rejects before Blender. |
| AC-02 | **Unambiguous chain** | Exactly 2–4 direct-parent, exact-name, genuinely weighted MPFB deform bones. Parent/child links match and per-joint source `CHANNELS` order is understood; wrong/missing maps fail rather than guess. |
| AC-03 | **Sufficient rest-space evidence** | Measure at least **two non-collinear source/target rest landmarks** (joint offsets and a terminal End Site/target leaf tail, or additional matched joints). Angle separation at least **10°** in both; missing End Site, aligned-only vectors or inconsistent orientation refuse calibration. One direction cannot determine bone roll. |
| AC-04 | **Explicit source coordinate transform** | User selects supported Y-up→Z-up or Z-up identity preset. No automatic axis guessing. The orientation from source rest coordinates to target rest coordinates is computed with a right-handed orthonormal basis; determinant within **1e-5** of +1; orthogonality error no greater than **1e-5**. |
| AC-05 | **Measured landmark residual** | Every source rest landmark mapped through the solved rotation aligns with its corresponding MPFB rest direction within **5°**, not merely the first reference. Reject mirror transforms, inverted bones, scale degeneracy and unreasonable or non-finite matrices. |
| AC-06 | **Correct pose-frame composition** | Use the BVH `CHANNELS` order to compose a source rotation quaternion/matrix; compute relative motion `Q_start⁻¹ × Q_frame`; conjugate into each target bone's measured rest-space axes `Q_target = C × Q_delta × C⁻¹`, where `C = M_target_rest⁻¹ × R_source_to_target`. No direct Euler copying. |
| AC-07 | **Numerical regression tests** | Pure Python matrix tests cover identity, known 90° axis conversion, known twist/bone-roll, compound rotations, inverse/roundtrip, non-collinear and degenerate directions. Set tight pure-math angular error ≤ **0.1°** for known synthetic transforms and orthogonality tolerance above. |
| AC-08 | **Actual per-bone Blender deformation** | On existing 163-bone MPFB human, at least two calibrated source-driven joints independently move **≥16 weighted evaluated mesh vertices**; actual Blender action keyed for all accepted frames; target rest bone names, skin weights and rest hash unchanged. |
| AC-09 | **Time-based, reproducible evidence** | Sample **five timeline frames**, at least **three distinct evaluated geometry hashes** and at least two measurably moving frames. Run **two separate Blender processes** on SHA-identical staged input and require matching joints, rest transforms, frame hashes and movement counts. |
| AC-10 | **No destructive side effects** | Preserve SHA-addressed source `.blend`, source BVH and `project.ucc.json`. Never save an Action to the master, never alter permanent rig/weights or advance project revision. Reject cancellation, concurrent metadata changes, changed source hashes and symlinks. |
| AC-11 | **Honest status labels** | A successful rest-frame gate is `calibrated_rotation_axes_verified`, **NOT** full-body retargeting or visual motion approval. Until genuine realistic clip review and engine import: `retargeting_verified=false`, `animation_visual_quality_verified=false`, `engine_import_verified=false`, `geometry_state=generated_unverified`. |
| AC-12 | **Complete CI on exact PR HEAD** | Preflight, Windows/Linux Python core, Windows/Linux offscreen PySide6, real Linux Blender 5.3+MPFB, and frozen Windows desktop startup all pass on the **same commit**. Do not merge failures or queued checks. No paid/user assets in CI artifacts (JSON only). |

## First calibrated vertical slice versus future acceptance

**Deliver now:** A verified two-bone direct-name MPFB `neck03 → head` calibration using a **self-authored, non-shipping 25-frame BVH**, with an intentionally non-identity source-to-target rest-space transformation; an actual head terminal End Site offset supplies the second rest direction. Include one negative mismatched-source source for a fail-closed integration case. Use the existing explicit local-BVH license workflow, source/rig SHA checks and two-process coordinator. Keep the old single-bone and uncalibrated 2–4-bone diagnostics intact.

**Not required for this slice:** General Mixamo/Fab/UE alias mapping, complex FBX import, arbitrary 100+ bone hierarchies, root translation, automatically scaled bodies, foot locking, inverse kinematics, real-time character animation viewport, generated/exported clip assets, engine import, or acceptance of a user-owned third-party clip without reviewed specific rights. Those require later incremental issues and real test media.

**Caveat:** BVH hierarchy offsets alone generally do **not** identify complete joint-local bone-roll orientation. When a pair of independent anatomical direction correspondences cannot establish a stable shared orientation, fail rather than invent a roll value. A successful two-bone orientation test cannot be promoted to arbitrary full-body retargeting quality.

## Code ownership and required evidence

- Blender-only work: `blender_bridge/rest_calibration.py` and a new isolated worker operation; retain old `blender_bridge/bvh_multichain.py` semantics.
- Source parsing: retain BVH End Site offsets without altering old metadata/backward contracts.
- Core: `src/ucc/jobs/protocol.py` and a bounded double-worker saved-master coordinator/evidence validation; no `bpy` in core.
- Desktop: explicit opt-in action or opt-in check in existing animation panel; user license and up-axis selection required.
- Tests: pure math, malformed BVH, source rights, renderer and worker contracts, real 2-bone Blender evaluated vertex movement, source/master immutability; reproduce exact evidence via the CI run URL.
- Report: source/target bone names, measured landmark residual degrees, source/target axis mapping, per-bone displacement, five frame hashes, worker IDs, source/master SHA-256, and **explicit unverified flags**.

## Exit decision

Accept only if every AC-01..AC-12 is passed with credible source and real Blender CI evidence. If any fail or remain unexecuted, keep the PR open and report the blocker. Never infer successful retargeting or Windows/engine compatibility from GitHub's Linux smoke.
