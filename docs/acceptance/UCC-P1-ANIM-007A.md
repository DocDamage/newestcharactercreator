# UCC-P1-ANIM-007A — versioned source-palm precision

Status: local repair and validation pass on `feat/anim-007-basic-actions`, based on frozen FACIAL-001 head `7db913e373c1147ea78f06408cc44c00e5d2669b`. The modified source has not been pushed or accepted by remote CI or a new Windows package. PR #64's separate all-five-workflow / 24-record acceptance applies only to its frozen source. This task is one necessary step toward the complete seven-action creator; three real deformation failures and the registered-action workflow remain open.

## Problem and behavior

Two authorized local motions passed actual Blender body workers but the host rejected their source palm references. Blender's `mathutils` source-point rounding produced normal differences of `1.093143929e-6` and `1.445854132e-6`, exceeding the existing `1e-6` geometry limit. The target normals matched. A pinned Blender diagnostic reproduced the saved source normals from the rounded corners; declared snapshot coordinates matched the independent core calculation.

Existing V1 saved references keep their original source-corner arithmetic. Newly generated hand profiles explicitly declare `hand_reference_planes.schema_version = 2`. V2 measurement requires the validated source snapshot and transforms its declared rest heads/world matrix with Python floating-point arithmetic before `mathutils` rounding. Creation and saved-scene reopening use the same version dispatch. The proof version must match its profile. Only integer versions 1 and 2 are accepted.

The host `1e-6` and saved-reopening `1e-7` geometry limits are unchanged. No skin weights, original scenes, source motions, strain thresholds, animation quality flags or license permissions are changed. Existing explicit V1 mapping profiles are not silently upgraded or relabeled.

## Executed local evidence

Private evidence lives under `evidence/anim007a`. Source motions, complete poses, meshes, scenes, caches and renders remain outside Git and AI services. Added unit geometry is invented, isolated in `tests/fixtures`, and supplies boundary regression evidence only.

| Gate | Observed result |
| --- | --- |
| Focused palm and hand contracts | 14 tests pass: analytic rotation/origin/scale invariance, required V2 source context, profile/proof version matching, unknown/Boolean version rejection and a source-normal component perturbed by `2e-6` |
| Final full suite, `full-regression-02.log` | 919 tests in 114.718 seconds; 905 passed and fourteen existing Windows symlink-privilege skips; required Qt enabled |
| Legacy saved V1 compatibility, `legacy-v1-versioned-compatibility-03.json` | Actual pinned Blender reopens both accepted idle/walk references: two planes each, matching the exact frozen baseline; originals unchanged |
| Normal affected V2 API, `affected-target-02/summary.json` | Actual attack 90-frame and hurt 120-frame cases pass normal two-worker body/hand verification, fresh saved-Action reopening, complete caches and independent surface workers; total 332.875 seconds |
| Independent persisted reload, `affected-target-02/independent-v2-full-evidence-reload.json` | Both saved timelines, source/profile identities, version-2 proofs, reopening, private render decoding, all 210 cache frames and surface proofs pass; actual source normal errors are zero against the independent core |
| Actual Windows GPU, `affected-target-02/actual-v2-affected-gpu.json` | All 90 attack frames in 3.015 seconds and all 120 hurt frames in 4.015 seconds; exact per-frame vertex and triangle buffers, including 13 and 18 distinct triangle buffers; nonblank changing framebuffer hashes checked locally |
| Actual geometry-proof negatives, `affected-target-02/actual-v2-palm-negative-proof.json` | Ten in-memory metadata faults reject against actual source/rig geometry, including normal changes above the unchanged limit, mismatched versions, coherent version downgrades and Boolean/unknown versions. These are palm-proof negatives, not saved-Action/scene/cache corruption claims. |
| Original and state protection | Same prepared neutral master, registered hand, saved expression strengths and all 22 protected inputs remain unchanged; no authoritative master is animated or overwritten |

The first unversioned candidate remains unaccepted historical evidence. Its 917-test suite and affected motion workers passed, but an actual baseline comparison showed that it rejected previously accepted V1 references. Versioned dispatch repairs that compatibility failure. No passing result from the preliminary candidate is relabeled as final V2 acceptance.

## Remaining work and rights

Run, jump and death remain rejected by unchanged real deformation guards. The existing project animation-ID field and catalog should be reused, but nonempty IDs currently block several customization paths. Registered clip references must gain verified neutral-master/source bindings, preserved editing/history/save/reopen and stale-proof invalidation before the full seven-action workflow can be accepted. Existing file selection and private preview do not prove that workflow. Root/loop/foot-contact quality, human visual quality and actual Godot/Unity/Unreal imports remain unapproved.

No dependency, model, asset or software installation was added. Existing local-preview-only, NoAI, source-redistribution and engine-export restrictions remain in force. Further merges require owner approval.

Next task: repair and independently verify the remaining three deformation failures through the normal pipeline, preserving the accepted expression/hand behavior and this V1/V2 compatibility contract.
