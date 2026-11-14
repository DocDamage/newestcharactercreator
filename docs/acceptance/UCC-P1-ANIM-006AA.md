# UCC-P1-ANIM-006AA — explicit symmetric shoulder layers

Status: technical implementation and actual owner-launcher acceptance complete. Draft PR #61 targets main at documentation head `138047ae32617086e7817cf8f3e4d48ace225809`; only four Markdown files differ from tested implementation `3f3310449b3fba290ec0bbfe464e637adbbaaae9`. Both heads pass all five workflows and all four independently accepted Linux archives (21 JSON records per head). PRs #39–60 are merged; main is `2c03434c75034b8cfb810b0d38daeb00122f004e`. Further merges require owner approval. The actual owner launcher now selects the verified symmetric correction. Human visual/grasp, arbitrary-pack and engine quality remain unapproved.

## Working implementation

A new `BOUNDED_NATIVE_SYMMETRIC_CLAVICLE_LAYER_V4` policy adds independently declared left/right clavicle, upper-arm, forearm and hand controls over one verified V1/V2/V3 base fit. The public entry point is `fit_native_preview(..., base_preview=verified_base)`. Existing calls retain their previous behavior.

The layer binds nine input identities: original source, source snapshot, mapping, master, source review scene, original timeline, base policy, base saved scene and base canonical report. Every job additionally binds the layer policy and, where applicable, its new saved scene/report. All three base hashes are required together. Source-only diagnostics reject them.

Both core and Blender independently check the complete actual hierarchy, declared anatomical hands, all mapped descendants, helper coverage, separate shoulder branches, fixed endpoints, full frame/FPS coverage and meaningful controls. The new layer cannot overlap any active base displacement or hand rotation. Inactive frames retain the canonical base rather than recomputing it.

The core uses matrix/vector math and the independent bridge uses Blender quaternions and vectors. The clavicle correction is in target-world space; hand controls remain in the actual hand-local frame. Both solvers retain limb lengths and reject unreachable/straight-pole solutions. The intermediate relative solve has a derived 30-degree bound, while **final source-world joint corrections still cap at 15 degrees**. Endpoint/joint displacement remains bounded by 80 mm or five percent of anatomical span, whichever is smaller. Control speed/acceleration remains 0.3 m/s, 5 m/s², 90 degrees/s and 900 degrees/s². Complete observed poses receive a separate eight-joint angular audit.

Each Blender process first reopens and reproduces the complete original source and the base saved Action, including canonical corrected/raw skin, rest/roll, exact weights, modifiers and topology. A disposable nested directory supplies the existing verifier's fixed filenames. Originals are copied, never renamed or linked. The stage worker copies the canonical base Action and changes only declared active shoulder channels. Normal measurement, independent reopening, fifteen decoded renders, playback caches and all anatomical review protocols carry the additional base identities. Desktop watchers invalidate both visible variants if any base policy, scene or report changes.

The existing neutral/master edge, raw/corrected skin, helper, local joint, unkeyed scale/translation, source SHA, project revision, licensing, cancellation and rollback guards remain in force. Existing default candidate generation remains V2; there is no new unverified automatic fitting control.

## Executed local evidence

Private evidence lives outside Git under `evidence/anim006aa`. Purchased animation files, scene copies, policy trajectories, complete poses, meshes and render images are not committed or uploaded to CI.

| Gate | Observed result |
| --- | --- |
| Full core/worker/Qt regression | 803 tests in 121.626 seconds; 789 passed, 14 Windows symlink privilege skips |
| Independent Blender 5.3 numeric contract | 21 invented unit poses, 14 joints; maximum core/worker matrix difference `2.689851602011295e-7`; 14 negative cases rejected |
| Normal application three-worker fit on one licensed owned clip | All 300 frames; 624.797 seconds; independently validated saved poses, skin, timing and 15 rendered views; original files unchanged |
| Separate production worker stage | All 300 frames; 142.032 seconds; no master overwrite |
| Separate canonical saved measurement | All 300 frames; 217.422 seconds; no hand/opposite-arm surface flags; core independently checked all poses |
| Separate fresh reopening and rendered verification | All 300 frames plus 15 decoded views; 221 seconds; saved corrected/raw/topology observations reproduced |
| Canonical base retention | All 122 inactive frames exactly match base target matrices and corrected/raw/triangle hashes |
| Normal application playback cache | All 300 fitted frames independently reproduced and decoded; 76,347,486 packed bytes; 273.188 seconds |
| Actual coherently rehashed saved-scene faults | Left clavicle quaternion corruption, missing clavicle key, left rest-roll change and one-float32-ULP weight change all rejected; positive saved pose and source/base reproduction pass |
| Actual Qt invalidation | Changing each of the three bound base files clears both cached variants; prior permission rejection remains tested |

The invented numeric fixture is only a unit contract. It proves neither skin deformation nor owned pack compatibility. The four real saved-scene faults check one active pose and the complete Action/rest/weight schema after fresh base reproduction; they supplement the separate complete-sequence workers.

The first full regression exposed two stale schema expectations. They were updated for the additive contract; explicit partial-base and unknown-field rejection remains tested. A misplaced existing assertion in the new Qt test was restored to its original pre-publication test, and both tests passed again. Failed logs are retained privately.

The first new original-source CI attempt stopped at its test precondition: the existing near-straight-arm source did not provide two continuously bent elbow poles. A constant 12-degree fixture variant then rejected at the unchanged palm rest-geometry agreement check (maximum observed source-normal difference about `1.43e-6`, above the existing `1e-6` bound). The separate symmetric fixture now adds a smooth 12-degree bend within the clip, retaining the old first/end poses. The old fixtures and all production rest, reachability, pole, angular and skin guards remain unchanged. Attempt 03 using this variant has now passed the complete real-Blender/MPFB suite. Attempts 01/02 remain unaccepted historical failures.

## Later completed local acceptance

- The normal cache and two independent complete anatomical workers pass all three guards over 300 frames. Detected complete-trunk crossing frames fall from 193 to zero. There remain 46 fitted frames with uncertain enclosure observations; these are not confirmed clearance. The transaction took 2434.031 seconds and preserved originals.
- Actual RTX 3060 desktop playback drew all 300 fitted frames in 10.078 seconds. Six bound-input changes clear both variants, using byte-identical disposable copies. The accepted observer waits for Qt's final queued repaint without forcing missing-frame seeks; its earlier 299-frame observation remains unaccepted.
- Original-source/real-MPFB attempt 03 passes the complete 300-frame symmetric suite: 59 mapped joints, eight correction joints, three fit workers, 15 decoded views, exact retention of 271 inactive base frames, complete skin cache and all three anatomical guards. Four real coherently rehashed Action/key/rest/weight faults are rejected. No authored clip establishes purchased-pack compatibility.
- The exact-head Windows package SHA is `0e8fdf26e81274d49409c6221eb0b5175d0edd9b01ac47779a0d362a2b996228`. All 67 bridge sources match Git; the actual extracted executable passes its project/Qt/bridge self-test without installation.

Private records: `normal-api-symmetric-anatomy-summary-01.json`, `product-symmetric-gpu-summary-02.json`, `original-ci-symmetric-03/symmetric_fit_summary.json` and `pr61-windows-qa/local-executable-acceptance.json` under `evidence/anim006aa`.

## Exact-head CI acceptance

| Scope | Verified workflows | Independently accepted Linux diagnostics |
| --- | --- | --- |
| PR #61 implementation `3f3310449b3fba290ec0bbfe464e637adbbaaae9` | Core, Qt, preflight, Windows, [Linux run 43524782784](https://github.com/DocDamage/newestcharactercreator/actions/runs/43524782784), all passed | Four SHA-bound archives; 21 records: regression/native-fit/body-contact five each, symmetric six |
| Final main `2c03434c75034b8cfb810b0d38daeb00122f004e` | Core, Qt, preflight, Windows, [Linux run 43531607974](https://github.com/DocDamage/newestcharactercreator/actions/runs/43531607974), all passed | Three SHA-bound archives; all 15 records accepted |

Both archive sets bind the exact head, workflow ID, suite name and GitHub digest before domain inspection. Checks cover actual source generation/reopening, full sequences, skin/topology, saved-scene faults, complete anatomical guards and process-local exact-geometry reuse. The symmetric archive additionally verifies the independent 21-pose numeric contract with 14 negative cases and its full real-MPFB layer transaction. Green icons or incomplete archives were not accepted alone.

Official Blender download HTTP 403 failures stopped before tests: PR regression failed on attempts 1/2 and symmetric on attempt 1; main regression/body-contact failed on attempt 1. Only failed setup jobs were retried after each overall run became terminal. No healthy suite was cancelled or restarted, and official origins/checksums and every assertion were preserved. Final main's file tree exactly matches previously tested `68d3c3a35a61ea4a6bebe5e4471202bbfadd4d3f`.

The final-main Windows archive matches all 64 bridge sources; its actual extracted executable passes its local project/Qt/bridge self-test without installation. This does not establish frozen-animation or engine compatibility.

Private exact-head receipts: `pr61-artifact-verification.json`, `main-artifact-verification.json`, `pr61-all-five-workflows.json` and `main-all-five-workflows.json` under `evidence/anim006aa/continuation-2026-11-13`.

## Actual owner-launcher acceptance

The real `Review-Fitted-Animation.cmd` still calls its original PowerShell wrapper. Its runtime loader now selects the accepted symmetric policy, scene, complete cache and anatomical reports, with **Fitted motion** selected by default. The compatibility delimiter remains intact. Source SHA, project revision, license, full base/report identities and all three anatomical guards remain enforced.

The activation first verifies both exact-head CI/archive sets, Windows package/executable receipts and protected original hashes. A byte-exact backup preserves V2. The actual rollback restored its original bytes and removed the new smoke helper; exact symmetric reactivation then passed before GUI testing. Rollback refuses to overwrite subsequent edits. No master or animation source is rewritten.

The actual `.cmd → PowerShell → app` chain was executed twice:

- Normal accepted-input startup: exit 0, correct symmetric policy and default fitted selection, all ten required watched input paths present, actual OpenGL draw loaded, all three 300-frame guards passed. Startup plus validation took 74.094 seconds; loading remains expensive.
- Full GPU/watcher self-test: exit 0, all 300 fitted frames drawn in 10.078 seconds. Actual mutations to the layer policy, three base files, body/enclosure/full-trunk reports and independent receipt each clear both variants. All eight mutations used fresh byte-identical disposable copies; accepted evidence and originals were preserved.

Detected full-trunk crossing frames remain 193 original / zero fitted. The accepted fitted enclosure still has 46 uncertain frames; zero detected crossings is not confirmed clearance. Local screenshots were retained without uploading private renders to AI services. This is actual launcher verification, separate from the earlier private-prefix harness.

Private receipts under `evidence/anim006aa/continuation-2026-11-13`: `launcher-backup/manifest.json`, `launcher-rollback-reactivation-verification.json` and `actual-cmd-verification-01/acceptance.json`. All tested original/source/master/project/license and accepted-evidence hashes remain unchanged. No dependencies or software/models were installed.

PR #61 remains unmerged. Further merges require owner approval.

## Limits and next task

This is an explicit measured correction for declared shoulder branches, with one preserved legacy base. It does not implement overlapping layers, automatic full-body contact solving, inferred grasp intent, arbitrary rigs or engine export. Uncertain enclosure classifications remain uncertainty. Synthetic CI clips do not establish compatibility with an owned animation pack. The Blender corrective modifier remains Blender-specific. Human visual/contact quality and game-engine imports remain unapproved.

Next task: continue the blueprint with one verified humanoid customization/animation slice while preserving the accepted review path. No dependencies or software/model installs were added; the existing reviewed local-preview policy remains enforced.
