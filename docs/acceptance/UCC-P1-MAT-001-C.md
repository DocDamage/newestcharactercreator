# UCC-P1-MAT-001-C — Material-preserving body and face revisions

Status: backend transactions, fresh saved verification and static Godot imports
executed. Later [desktop routing/history acceptance](UCC-P1-MAT-001-D.md) supersedes
that next-step limitation below. The full application goal remains incomplete.
Depends on [material publication](UCC-P1-MAT-001.md), the existing body/face and
expression workers, compatible-hand recipes, and the source-corner UV gate.

## Plan and implementation

Extend the existing material graph transaction additively. Preserve the original
project and immutable masters, verify old physical intent separately from pending
desired dimensions, apply the requested body/face change in a private copy,
retain/reapply the chosen material, rebuild the original hand variant, and commit
master/appearance/part metadata together only after fresh inspection. Acceptance
requires actual changed geometry, the same explicit material spec, retained hand
instance/selection and facial strengths, fresh save/reopen, and final-master
engine import. Cancellation, stale/source changes and final-save failure must
leave the old graph or a concurrent user's change authoritative.

`ucc.jobs.skin_material_revision.revise_material_bound_master` admits only
`body_refit`, `body_generation` and `face_revision` on a prepared, material-bound
MPFB human without source-animation references. It reuses the existing private
material graph. The old physical projection comes from the registered hand
recipe; only that projection omits the old appearance binding before editing.
The original appearance and desired body/face metadata are never cleared.
The material spec is read from immutable admitted proofs, not inferred from an
arbitrary shader. Body and material expression receipts are installed before the
new hand/material binding and one outer metadata revision become authoritative.

Refit and face revision retain the exact shader and use a verified same-spec
material no-op. Regeneration creates the body through the existing MPFB path and
genuinely reapplies the chosen shader. A verified face no-op returns
`MaterialMasterNoOp` and does not rebuild/publish another master. The existing
explicit body-only guards remain until desktop callers and history are integrated.
No new control, dependency, provider or asset is introduced.

## Real evidence

Private root: `D:/dev/new Character Creator/evidence/export001`. All source
projects are admitted disposable copies of material publication 226. Originals
and every pre-existing private master are hash-checked unchanged.

| Case | Requested change | Final master SHA256 |
| --- | --- | --- |
| `mat246` | Height macro 0.50 → 0.58, refit | `4d58ed9d5f64c6b47a1007674d841cb3cdcb1395b26f337060391d2bd82e5121` |
| `mat247` | Height macro 0.50 → 0.62, regenerate | `809a5c9dd53d0d23e3c5a289ce1f59743b040bda93d0b3ed9c19fb61b9828bde` |
| `mat251` | Nose width 0.50 → 0.65 | `de5b073ca867d0a064544c502748c97ec5c21ad2aef925c715eceac4bc6df6d3` |

Each normal API commits exactly one outer metadata revision and is followed by a
separate real saved-expression/hand verification. The shader remains sRGB
`(0.58, 0.31, 0.19)`, roughness `0.62`, metallic 0, opaque, without textures.
The original hand variant, part instance ID and facial strengths remain intact.
Blender 5.3.0 build `02f0899d78e3`, MPFB 2.0.18 and the existing local profile
are used; no installation occurs.

`mat-export253/256/263` repeat normal material stage/fresh verification against
the final rebuilt-hand masters. All return same-spec no-ops with byte-identical
master files and no metadata changes. `mat-godot254/257/264` then perform actual
Godot 4.7.1 official `a13da4feb8d8aefc283c3763d33a2f170a18d541` import and
standard-material readback/render on RTX 3060 Mobile/Vulkan. Each retains 163
bones, 12 morphs, no added clips and no material override. Color/roughness stay
within the existing 1e-6 numeric limits. All three 512x512 views were visually
inspected for visibility and clipping; this is not artist approval or render parity.

Independent geometry audit 266 decodes the actual GLBs. Imported height changes
from 1.659431 m to 1.760623 m for refit and 1.818447 m for regeneration. The face
edit has exact UV and triangle-index correspondence and moves 448 exported
vertices by up to 0.000510 m. Coordinate multisets change for all three edits;
this is stronger than a changed file hash alone. All retain the same 53,512
source-corner UV hash `16cc1fc069f18710c12e3d0e8b75b98acf800332bbc4ca67675ba47dc0d5e835`
and per-source-face GLB UV error at most 2.981e-8.

Audit 265 incorrectly required identical GLB triangle arrays across every body
change; its failed source is preserved. Refit/regeneration triangle arrays differ,
while source-corner UVs and UV rows remain exact. Audit 266 compares coordinate
multisets without claiming vertex correspondence for those two cases. Only the
face case supports a paired displacement calculation. No product predicate,
geometry tolerance or source UV gate was changed to accommodate that audit.

`mat-noop262` repeats the saved face setting through the actual normal API and
returns a verified no-op. Project bytes, master bytes and backup history remain
unchanged. `mat252/cancel-receipt.json` observes an actual owned `refit_human`
Blender child alive, cancels it, and verifies no outer publication or original
file changes. The launch observer returns the real process, not a worker double.

`mat-fault260` changes actual saved shader roughness and coherently rebinds the
master hash, hand receipt, material manifest and appearance pointer. A fresh
Blender reconstruction rejects it. The private harness then failed to classify
the expected `original/hand selection` error text; its failed run is retained.
Audit 261 validates the completed structured result, staged master hash, source
body binding, forged receipt and unchanged positive project without rerunning
the already completed worker. That rejection is real; the original harness is
not labelled passed.

## Regression and limits

Final required-Qt suite 258: 1,289 total, 1,275 passed, 14 existing skips,
288.754 seconds. Lifecycle tests 255: 14 passed. Guardrails 259: 12 passed.
The focused 248 invocation named a nonexistent test module; corrected 250
passes 38 tests. Full 249 predates the last three lifecycle tests and is retained
as preliminary evidence. Pure graph imports load no Blender, Qt, NumPy or model
runtime. Synthetic tests prove transaction logic, not Blender integration.

Existing desktop actions and undo/redo adoption do not yet route these material-
aware results. Source-animation references, different hand selections, frozen
material execution, moving native material rendering, Unity/Unreal, texture/
tangent workflows and artistic approval remain unverified or unimplemented.
The owner checkout and launcher are unchanged; archive 198 predates this code.
No license, dependency, NoAI or distribution permission changes are made.

The single next task is to route the existing body/face desktop actions through
this verified API and add strict session history adoption for the atomic master,
appearance and rebuilt-hand change. Verify existing controls, stale/cancel/error
states and real undo/redo on a disposable material-bound project before exposing
new material UI or changing the owner launcher.
