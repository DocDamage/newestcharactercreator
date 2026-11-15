# UCC-P1-ANIM-007H — edit unprepared masters while retaining source references

Status: local implementation, full regression, actual API/desktop gates and the complete portable original-only CI entry point are accepted. This work extends `43529a43ea17fc4e702cd1f6c2fd7d633a129103` in a separate branch. Exact-head remote and Windows-package acceptance remain pending. Parent PR #67 remains draft and unmerged. Further merges require owner approval.

## Resulting behavior

A saved MPFB humanoid with source references can now use the existing Face, Apply Body and Generate controls before expression preparation. Supported attachments remain bounded to one visible registered compatible left hand, or no hand. Unknown attachments remain blocked. Preparing expressions on an attached-reference character remains unsupported.

The public reference-master coordinator delegates unprepared characters to a separate job module. It verifies exact source bindings, current catalog policy and fresh paired full-source observations, then stages existing body/face operations in a private project. A selected hand resets using its immutable original recipe; successful body/face changes build and verify a new compatible hand library while preserving the selected variant and instance ID. No expression controls are introduced. Prepared-reference workflows retain their existing route.

Two fresh Blender inspections bind physical saved-body measurements to saved macro intent. Face-only editing rejects unapplied body intent before face staging. Changed outputs receive another paired readback and a final neutral inspection. Dependency hashes, owner revision, source policy, private metadata and rebuilt-hand receipts are checked again before atomic owner publication. A real duplicate face no-op leaves owner metadata, objects and history unchanged.

Native Undo/Save/Redo/Save retains complete intent and source references. Live work locks project/history actions; cancellation preserves the owner, and concurrent saves win with an explicit reload. Generate retains a valid Blender executable already selected by the user. Missing or invalid selections still use the existing chooser; cancellation starts no job. Existing help text describes hand preservation and remaining quality checks accurately. No new controls or bridge protocol were added.

Raw no-hand masters do not acquire prepared-expression provenance. Their observed neutral state is not a new source-authenticity claim. Source references remain source-only, with immutable NoAI and licensing restrictions; this work does not register usable target motion.

## Executed local evidence

Private logs and machine-readable receipts remain outside Git under `evidence/anim007h`. Blender 5.3.0, MPFB 2.0.18, the existing project-local Blender profile and installed Python 3.12.10/PySide6 are used. No software or data was installed.

| Gate | Observed result |
| --- | --- |
| Current full required-Qt regression, source manifest 22 | 1,149 tests: 1,135 passed, fourteen existing Windows symlink skips; 158.142 seconds; all 623 frozen source files rehashed unchanged |
| Initial full required-Qt regression, source manifest 08 | 1,134 tests: 1,120 passed, fourteen existing Windows symlink skips; 141.177 seconds |
| Actual original-only raw-master API, `o10/positive-acceptance.json` | Six changed transactions and two verified no-ops across hand/no-hand face, refit and generation; 112 positive workers; six native saved-history cycles; 6,600 complete setup/positive source-frame observations |
| Independent API audit 12 | Exact worker requests/results, all saved source observations, paired physical measurements, hand receipts, immutable objects, source policy and 617 frozen source files accepted |
| Actual original-only rejection gate, `g13/guard-acceptance.json` | All thirteen guards passed in 480.719 seconds; 87 requests, including two observed live-worker events; originals and owner authority preserved |
| Independent guard audit 14 | All thirteen closed guard records, requests/results, expected owner states, 4,200 complete source-frame observations and original/copy policy distinctions accepted |
| Normal existing desktop controls, `u15/acceptance.json` | Face, Apply Body and Generate ran real background Blender jobs; 60 positive workers, native saved history, NoAI error dialog, live Cancel and concurrent-save reload passed; 39,142 continuous busy-lock samples |
| Actual desktop static preview and invalidation | Full 26,756-triangle saved-master GLB drew on the NVIDIA GeForce RTX 3060; actual metadata notification cleared CPU publication and destroyed GPU buffers |
| Independent desktop audit 17 | Exact workers, saved history, physical measurements, 2,400 complete source-frame observations, GLB/buffer sizes and local raster hashes accepted; images remained private |
| Follow-up cached-executable/unit gate 18 | 65 focused tests passed in 13.248 seconds; valid cached selection, choose-once and canceled selection covered for both prepared and plain states |
| Normal cached Generate, `u20/acceptance.json` | 19 actual workers; zero chooser calls; genuinely rebuilt hand; native saved history; 10,583 busy-lock samples; 112.516 seconds |
| Independent cached Generate audit 21 | All 19 workers, one paired physical-body readback, 600 complete source-frame observations, hand receipt, saved history, originals/NoAI and all 617 source files accepted |
| Scanner, guardrails and source launcher | 3 scanner tests and 12 guardrail tests passed; actual source launcher returned `SELF_TEST_OK` for project save/reopen, Qt widgets and bundled bridge |
| Fresh complete portable CI entry point 22 and independent audit 25 | Entire command returned 0: all eight transactions and thirteen guards passed; independent auditing accepted 112 positive workers, 87 guard requests, six native saved-history cycles, ten paired positive body readbacks, 10,800 complete setup/positive/guard source-frame observations and all 623 frozen source files |
| New CI retention/summary contracts | Closed exact field set, every transaction/worker count, all thirteen guards, numeric/boolean distinctions, privacy, portable CLI import and existing-output preservation passed |

The normal desktop gate took 1,734.453 seconds, including a long native executable-chooser wait during Generate. That wait is not Blender compute time. The subsequent cached-selection gate tests the corrected normal behavior separately. The six source changes after manifest 08 consist of boundary annotations/documentation, accurate UI text, cached executable selection and its tests; the coordinator function body is AST-identical to the accepted original implementation. Source manifest 19 binds the cached Generate gate. Older full-suite results are not relabelled as a full test of those later bytes.

The thirteen actual rejection cases cover hand/no-hand policy-binding changes before workers; saved Actions and five-micrometre poses failing the first neutral worker; pending physical body intent before face staging; a foreign neutral hash lacking the registered hand receipt; cancellation and external save during genuine private hand rebuilding after verified face mutation; a coherently rehashed real saved-pose/pointer change after final neutral verification; and a committed policy change held only in a copied catalog's SQLite WAL while its main-file hash/timestamp remain unchanged.

## CI and remaining acceptance

The existing seventh `reference-creator` job additionally invokes `ci/verify_plain_reference.py`. It builds fresh original MPFB hand/no-hand targets and an authored 300-frame, 71-bone FBX, then runs all eight transactions and thirteen guards. The six earlier suites and prepared-creator gate remain intact, as do official checksums, assertions and job budgets.

To reproduce with the existing configured Blender/MPFB profile, run `py -3.12 ci/verify_plain_reference.py --blender "<installed Blender 5.3 executable>" --outdir "<new evidence directory>"` from the checkout. The output directory must not already exist. A failed case leaves its worker logs and private evidence in place and does not write an accepted final summary.

Only the exact additional path `ucc-plain-reference/plain_reference_summary.json` is retained. Its validator rejects missing/unknown fields, incomplete worker or guard coverage and visual/engine approval claims. Scenes, source animation, full poses, meshes, caches, private paths and renders remain outside artifact retention. Complete fresh remote acceptance will require seven archives with forty JSON records, all five workflows, and the exact-head Windows package plus actual extracted executable health verification. Parent results do not substitute for this branch.

The freshly assembled portable entry point passes in full locally; this is separate from the earlier private API and guard harnesses. Exact-head remote acceptance remains pending. Its closed summary SHA-256 is `07b0cbc3f7f1f50fe7ecfe7230d92ec55edba7ce93b3d8dc1282e5f5771bf79c`. Human visual/grasp quality, purchased-pack compatibility, usable target actions, root/loop/foot quality, Godot/Unity/Unreal imports, sprite output and the wider blueprint remain unfinished. No dependencies, installs, asset rights, export permissions or NoAI restrictions changed.

Next: publish a draft from the locally accepted source, then independently accept all five exact-head workflows, seven Linux archives / forty JSON records and the actual Windows package without changing that head while healthy jobs run.
