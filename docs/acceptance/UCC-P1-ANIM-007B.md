# UCC-P1-ANIM-007B — explicit regional skin correction

Status: locally implemented and verified on `feat/anim-007-basic-actions`, based on `f77cf99ad157d850035e6a0cd0831d087c032139`. New remote CI, an original-only real-Blender V2 integration gate, and a new Windows package remain unrun. Frozen PR #64's separate acceptance applies to `7db913e373c1147ea78f06408cc44c00e5d2669b`. This task does not complete the seven-action product workflow.

## Problem and behavior

The existing V1 skin path rejects three actual authorized motions on the prepared character: run compresses an edge to `0.034903x` on frame 25; jump stretches an edge to `4.002123x` on frame 30; death stretches an edge to `4.012454x` on frame 92. The unchanged allowed interval is `0.05x` through `4x`. Increasing global smoothing produced other compressed joints.

The new, explicit `BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2` policy binds two corrective layers on a disposable character copy: global length-weighted smoothing with twenty iterations and factor `0.5`, followed by simple smoothing with twenty iterations and factor `0.75`. The second layer uses one temporary nondeform mask. Each mask weight is the sum of the original `spine05`, `pelvis.L`, `pelvis.R`, `upperleg01.L`, and `upperleg01.R` weights, capped at one. Original groups, bone weights, order, armature settings, and geometry remain unchanged.

The reserved mask name cannot overwrite an existing group or bone. A schema-2 proof binds the exact original group memberships and float32 weights, the derived mask formula and hash, and both ordered layers. Independent host checks use a closed settings contract. Fresh Blender reopening recomputes the mask formula from the original weights and verifies the persisted layers, Action, complete corrected/raw skin, and both actual neutral references without repairing the saved scene. Raw measurement disables both owned layers. Correction still caps at three percent of character bounds, and neutral shape must remain within `1e-6`. FK, hip, root-speed, continuity, topology, source, license, revision, and original-file guards remain in force.

V1's smoothing class and settings are unchanged. Automatic mapping and the normal API still default to V1; opting into V2 uses `skin_policy="BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2"` or an explicitly bound V2 mapping. The new policy requires the actual neutral-bind strain reference. Palm reference versions retain their separate V1/V2 compatibility contract. Existing fitting policies remain V1 only. The desktop stops a regional hand/arm fitting request before launching any job and retains the original motion.

## Executed local evidence

Private evidence is under `evidence/anim007b`, outside Git. Purchased source motions, poses, meshes, scenes, caches, and renders were not uploaded to CI or AI services. Unit weight memberships are invented and isolated under `tests/fixtures`.

| Gate | Observed result |
| --- | --- |
| Final full suite, `full-regression-03.log` | 932 tests in 112.784 seconds: 918 passed, fourteen existing Windows symlink-privilege skips; required Qt enabled |
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

## Remaining work and rights

The V2 policy is opt-in and proves these three complete local motions on this prepared character. It does not establish arbitrary-pack compatibility, foot-contact/root/loop quality, human visual acceptance, collision clearance, or engine reproduction of Blender corrective modifiers. Existing surface observations remain observations.

The first four motion receipts remain separately bound to their earlier policies. Registered action IDs, editing/history/save/reopen with registered clips, actual Godot/Unity/Unreal imports, and sprite output remain unfinished. The authoritative master stays neutral; no project animation IDs or new action selector were introduced by this task. The owner review launcher remains unchanged.

No software, model, asset, dependency, or license was added. Existing local-preview-only, NoAI, source-redistribution, and engine-export restrictions remain unchanged. Further merges require owner approval.

Next task: add original-only real-Blender coverage for the new policy and finish this branch's remote CI/package acceptance before integrating the registered-action workflow.
