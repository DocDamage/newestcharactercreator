# UCC-P1-ANIM-007B — explicit regional skin correction

Status: technically accepted at exact head `9b07f0b75d5ce0f60d6b3e3d2f39a7f975819382` / draft PR #65, stacked on PR #64. All five required workflows, all five Linux archives / 29 diagnostic JSON records, and the exact-head Windows package plus actual extracted executable are accepted. The PR remains draft and unmerged pending owner approval. This task does not complete the seven-action product workflow.

## Problem and behavior

The existing V1 skin path rejects three actual authorized motions on the prepared character: run compresses an edge to `0.034903x` on frame 25; jump stretches an edge to `4.002123x` on frame 30; death stretches an edge to `4.012454x` on frame 92. The unchanged allowed interval is `0.05x` through `4x`. Increasing global smoothing produced other compressed joints.

The new, explicit `BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2` policy binds two corrective layers on a disposable character copy: global length-weighted smoothing with twenty iterations and factor `0.5`, followed by simple smoothing with twenty iterations and factor `0.75`. The second layer uses one temporary nondeform mask. Each mask weight is the sum of the original `spine05`, `pelvis.L`, `pelvis.R`, `upperleg01.L`, and `upperleg01.R` weights, capped at one. Original groups, bone weights, order, armature settings, and geometry remain unchanged.

The reserved mask name cannot overwrite an existing group or bone. A schema-2 proof binds the exact original group memberships and float32 weights, the derived mask formula and hash, and both ordered layers. Independent host checks use a closed settings contract. Fresh Blender reopening recomputes the mask formula from the original weights and verifies the persisted layers, Action, complete corrected/raw skin, and both actual neutral references without repairing the saved scene. Raw measurement disables both owned layers. Correction still caps at three percent of character bounds, and neutral shape must remain within `1e-6`. FK, hip, root-speed, continuity, topology, source, license, revision, and original-file guards remain in force.

V1's smoothing class and settings are unchanged. Automatic mapping and the normal API still default to V1; opting into V2 uses `skin_policy="BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2"` or an explicitly bound V2 mapping. The new policy requires the actual neutral-bind strain reference. Palm reference versions retain their separate V1/V2 compatibility contract. Existing fitting policies remain V1 only. The desktop stops a regional hand/arm fitting request before launching any job and retains the original motion.

## Executed local evidence

Private evidence is under `evidence/anim007b`, outside Git. Purchased source motions, poses, meshes, scenes, caches, and renders were not uploaded to CI or AI services. Unit weight memberships are invented and isolated under `tests/fixtures`.

| Gate | Observed result |
| --- | --- |
| Latest full suite with CI follow-up, `ci-full-regression-02.log` | 935 tests in 121.515 seconds: 921 passed, fourteen existing Windows symlink-privilege skips; required Qt enabled |
| Focused contracts and desktop boundary | 42 skin/palm/hand/reference tests pass; all eight fitted-comparison Qt tests pass, including regional rejection before job submission and unchanged project/original playback |
| Normal API, `regional-target-01/summary.json` | Run 180 frames in 382.578 seconds, jump 120 in 262.344 seconds, death 210 in 431.891 seconds; all 21 normal workers pass in 1076.969 seconds, including paired source/body verification, saved-Action reopening, complete caches, and independent surface verification |
| Independent persisted reload | Both saved timelines per case, profiles, original source identities, palm proofs, decoded local renders, all 510 cached frames, and surface proofs pass; source palm normal errors are zero |
| Actual Windows GPU, `regional-target-01/actual-regional-gpu.json` | All 180 run frames in 6.016 seconds, 120 jump frames in 4.015 seconds, and 210 death frames in 7.000 seconds; exact per-frame vertex and triangle buffers, including 110/50/15 distinct triangle buffers; nonblank changing framebuffer hashes checked locally |
| Old V1 saved scenes, `legacy-v1-full-reopen-01/summary.json` | Fresh actual reopening reproduces all 300 idle and 180 walk frames, complete original/corrected skin, poses, strain, and V1 palm references; no originals resaved |
| Actual saved faults, `actual-regional-faults-01/summary.json` | Eight coherently rehashed scene/timeline copies reject in 28.953 seconds: missing/reordered/unbound layers, changed factor with matching metadata, one-ULP bone weight that preserves legacy weight rounding, one-ULP mask weight with an updated hash, missing mask, and Boolean schema version |
| Actual production constructor, `production-neutral-setup-01.json` | Real two-layer rest binding and mask checks pass; a setting mutation rejects; success and second-layer bind failure restore exact original float32 skin, all groups/weights, modifier stack, rig, and context |
| Preflight and launcher | Scanner three tests and guardrail twelve tests pass; actual source launcher passes project save/reopen, Qt widgets, and bundled bridge self-tests; source contains 89 bridge modules |
| Original protection | All 23 protected inputs remain unchanged, including the same prepared neutral master, registered hand, four saved expression strengths of `0.5`, source policies, source motions, and actual owner originals |

The selection scan is separate observation evidence, not a normal worker acceptance claim. Its fixed winning recipe covers all 510 frames with exact pre-mask original float32 skin checks and exact group restoration. Observed minimum/maximum edge ratios are run `0.058543/2.866345`, jump `0.064703/3.407674`, and death `0.065307/3.914709`. Maximum correction is respectively `1.7192%`, `2.2474%`, and `1.1792%`; neutral displacement is `2.4756e-7`. Earlier candidates remain failed historical evidence. No threshold was relaxed.

The final UI-only fitting guard was added after normal Blender QA completed. A final LF normalization preserves identical AST and compiled code for all 22 Python files in both host Python and pinned Blender. Original normal-worker evidence retains its earlier source manifest; final regression, persisted reload, and GPU checks use the normalized source. The final 22-file manifest, full 932-test suite, independent reload, and actual GPU checks include that additional guard and its Qt test. No Blender/API worker result is relabeled after a backend edit.

## Original-only CI follow-up

The separate `original-ci-regional-01/regional_skin_summary.json` gate passes in 2229.485 seconds. It creates three real MPFB body/face targets through normal application transactions, genuinely rebuilds the middle target's selected hand with prepared expression keys, and preserves four saved strengths of `0.5`. One shared original analytical armature supplies all 300 frames to each target: scaled four-meter hip travel, a complete 400-degree turn, intrinsic finger motion, and opposing torso/leg bend recovery. The existing source author and its challenge remain unchanged. No owned clip, pose, scene, render, or mesh was used as a fixture or uploaded.

All 900 frames pass paired body/hand workers, normal saved-Action reopening, complete caches and independent surface verification. A separate reader independently checks exact original binary weights, the derived mask formula, original geometry/keys/rest, actual ordered bound layers, all saved poses, corrected/raw skin, and both neutral strain references. It does not call the production reopening or mask solver. Minimum/maximum observed edge ratios are `0.605140/1.780563`, `0.585475/2.210249`, and `0.639321/2.578059`; maximum correction remains below `0.63%` on every target. These authored tests do not establish purchased-pack compatibility or collision clearance.

Eight actual coherently rehashed scene/timeline faults reject on the generated middle target, including original and mask one-ULP weight changes. Actual second-layer bind failure and a layer-setting mutation on the twentieth posed measurement both reject and restore exact original float32 skin, groups, rest, modifier stack, and Actions. Original generated inputs and installed targets remain unchanged. A separate domain auditor checks all three cases, 900 frames, 38 intrinsic hand joints per case, bounded metrics, and the complete ten-fault set.

A fifth independent Linux matrix suite, `regional-skin`, has a bounded 90-minute job budget. Its artifact allowlist adds only `ucc-regional-skin/regional_skin_summary.json`; generated assets and worker evidence remain on the runner. Existing suites, official archive/checksum checks, and assertions are retained. The full suite initially detected the missing entry in the older closed artifact privacy test; adding that exact summary filename restored the 935-test pass without introducing wildcards.

## Exact-head remote acceptance

All five workflows pass at `9b07f0b75d5ce0f60d6b3e3d2f39a7f975819382`: Linux 43648318052, Core 43648318060, Qt 43648318063, preflight 43648318083, Windows 43648318120. Independent archive verification accepts all 29 records: regional five, regression eight, body-contact five, symmetric-fit six and native-fit five. The original-only regional summary retains three targets / 900 normal and independent-reader frames, eight saved-scene faults and two transaction faults. Other existing suites retain their original assertions and negative cases.

The Windows artifact 14134044728 has SHA-256 `101b105d12f63c211b912cbabf08d8509ddbb49183ecbadc0487af90b5db00c0`. All 89 packaged bridge files match the exact Git head; the actual extracted executable passes project save/reopen, Qt widgets and bundled-bridge self-tests without installation. This does not cover the later unpublished 90-module source-reference follow-up.

The only change from historical `b873ed0` is the regression job fallback budget increase from 60 to 120 minutes; individual subprocess limits, checksums, tests and other suite budgets remain unchanged. All current-head jobs passed on attempt one. The observer finished normally; no healthy remote job was cancelled or restarted. Old-head partial records are not counted as current acceptance. Private final receipts are `pr65-budget-artifact-verification.json`, `pr65-budget-all-five-workflows.json`, `pr65-budget-Windows-acceptance-01.json` and `pr65-budget-final-acceptance-checkpoint.json` under `evidence/anim007b`.

## Remaining work and rights

The V2 policy is opt-in and proves these three complete local motions on this prepared character. It does not establish arbitrary-pack compatibility, foot-contact/root/loop quality, human visual acceptance, collision clearance, or engine reproduction of Blender corrective modifiers. Existing surface observations remain observations.

The first four motion receipts remain separately bound to their earlier policies. Registered action IDs, editing/history/save/reopen with registered clips, actual Godot/Unity/Unreal imports, and sprite output remain unfinished. The authoritative master stays neutral; no project animation IDs or new action selector were introduced by this task. The owner review launcher remains unchanged.

No software, model, asset, dependency, or license was added. Existing local-preview-only, NoAI, source-redistribution, and engine-export restrictions remain unchanged. Further merges require owner approval.

Next task: continue the registered-source editing and target-action workflow. This PR remains draft; further merges require owner approval.
