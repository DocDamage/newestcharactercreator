# UCC-P1-ANIM-006B — numerical joint and local mesh guards

Incremental slice after merged PR #35 (`be31dc40117fbc0dcba79d3d019a229f9f165ecd`).
**Problem:** a small local skin tear can pass the existing whole-model diagonal
displacement limit. Quaternion jumps alone also do not describe accumulated
twist, and target constraints/drivers can invalidate rest-local FK assumptions.

## Measurable contract

| Gate | Implementation and verification |
| --- | --- |
| Per-joint motion | Measure swing and absolute twist about each actual target bone's local Y axis on every source frame. Record maxima and their frames; preserve quaternion hemisphere continuity. Reject non-unit/nonfinite input, ambiguous 180° swing, twist >90°, swing >150°, or adjacent rotation >80°. Known compound quaternion and sign-equivalence tests; real Blender measurements |
| Local skin strain | Read actual evaluated edge connectivity on every frame, fingerprint topology and measure edge length ratios against frame 1. Reject topology changes, >4× stretch or <0.05× length. Explicitly count baseline edges ≤1e-9 local units excluded from ratios; require ≥16 measurable edges. Unit test demonstrates a 0.004-unit local tear that the model-wide bound misses |
| Target rest assumptions | Read-only rejection of active mapped-bone/ancestor constraints, rig drivers, non-neutral ancestor poses, incompatible inherited rotation, reflected/nonuniform/sheared rig or mesh world transforms. Never mute a user's constraint or reset a saved pose |
| Evidence | Require motion-quality schema version 1, all-frame edge ratios, topology SHA/counts, all mapped joints' angle/frame records and explicit environment check. Reject missing, forged, extreme, reordered or inconsistent proofs. Two workers compare topology, joint maxima and every skin/strain frame |
| Independent reopen | A third genuine Blender process reopens the private Action, reproduces all skin hashes and edge ratios, and agrees on joint angles within 0.001° (frames exact). Fault injection rejects 5× strain in a measured skin snapshot, an actual Blender 100° longitudinal quaternion, and nonuniform mesh scale; restores the evaluated skin hash |
| Desktop/packaging | Existing result log shows local edge range, excluded degenerates and per-bone swing/twist maximum frames. New bridge modules are required by the frozen/source bundle self-test; no new inactive UI controls |
| Integrity | Original BVH/master/project and private review `.blend` bytes remain unchanged on positive/negative paths. A frame-2 compound rotation fault after frame-1 key insertion must remove its partial Action, restore neutral poses and create no review copy. Source rights, SHA verification, revision conflicts, cancellation and rollback stay enforced |
| CI | All five existing workflows must pass on the final PR head: core/worker, Qt, preflight, real Blender 5.3/MPFB, Windows frozen executable |

Pure worker mathematics live in `blender_bridge/motion_quality.py`; Blender target
state checks live in `pose_environment.py`. The application validates reports in
`src/ucc/jobs/motion_quality_evidence.py`, without importing Blender. Changes are
reversible and do not migrate or promote project data. Old stored diagnostic JSON
without quality schema 1 is insufficient for the new quality gate: rerun the
diagnostic, rather than silently inferring missing measurements. Other legacy
single-bone/chain diagnostics retain their existing evidence contracts.

## Local execution

- Baseline on merged `main`: Python 3.12.10, **350 tests OK, 11 Windows symlink
  skips**, including real Qt. Existing PySide6 6.11.2 is exposed process-locally
  after the 3.12 site-packages directory; nothing installed.
- New local suite: **360 tests OK, 11 symlink skips**, including the added desktop
  result-format assertion. All **15** preflight/guardrail tests also pass.
  Final-head CI evidence belongs in the PR.
- Actual Windows Blender **5.3.0** (explicit executable, not the `blender.cmd`
  pointing at 4.5): ten-bone **synthetic** contract passes two workers, all 25
  independently reopened skin/quality frames, crossed-parent rejection, quality
  fault injection and restored geometry. Measured **560 edges**, none excluded,
  local length ratios **0.9999943894–1.0000051458**. Original bytes unchanged.
  A genuine Blender step-failure test also verifies cleanup of an Action created
  before the failure, neutral-pose restoration and absence of a review artifact.
- This fixture is non-shipping and isolated under `tests/fixtures`. It proves
  numerical/worker behavior, not MPFB anatomy, Fab compatibility or natural motion.
- Local MPFB remains unavailable from the prior verified environment audit.
  The existing CI uses its established ephemeral official Blender/MPFB setup and
  actual 36-bone body tree. Only JSON diagnostic summaries may be uploaded.

Reproduce using a new private output directory:

```powershell
py -3.12 tests/run_branching_blender_contract.py `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --humanoid-names --output "$env:TEMP/ucc-quality-contract-new-run"
```

No dependency/license changes, local software/model installation, user-asset scan,
purchase/download or user-file cloud upload. Game-engine imports are not changed
or verified by this slice.

## Important limits and next task

These are **generic numerical catastrophe guards**, not physiological limits or
anatomical quality approval. A knee or wrist may look wrong well inside these
bounds. Baseline-degenerate edges are excluded and reported; this is not a mesh
repair, self-intersection detector, face-area/volume test or proof against every
form of deformation. Measurements are relative to the first evaluated frame.
The fixture motion is original test input derived from target coordinates.

Per-joint **target** rest frames are used; independent **source** joint rest/roll
data is still unsupported. Do not infer it from BVH OFFSETs or relabel these
diagnostics as production retargeting. All retargeting, visual-quality, independent
source-roll and engine-import approval flags remain false.

**Single next task:** explicit SHA-bound per-joint source rest-frame intake and
validation, followed by privately rendered visual inspection. No licensed user
asset is needed to implement that intake contract.
