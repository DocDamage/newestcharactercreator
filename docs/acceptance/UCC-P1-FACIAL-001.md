# UCC-P1-FACIAL-001 — bounded expression preview

Status: implementation in progress on `feat/facial-001-expression-preview`, based on accepted PART-001 head `4e9d03e12fba52ab87b6fb6b5c4c1001b4ca8182`. Neutral preparation workers and core metadata contracts are implemented and tested locally. There is no facial expression product API, editable timeline or desktop control yet. No engine, visual expression quality, lip-sync or full eyelid closure approval is claimed. Existing PRs #61–63 remain draft and unmerged; further merges require owner approval.

## Intended behavior and current boundaries

Four saved strengths will control a private expression preview: left and right eyelid closure, mouth corners and mouth opening. Each uses three actual race-specific MPFB 2.0.18 targets already installed locally. Strengths remain between zero and 0.5. The editable master must retain all twelve keys at zero, while preview settings live separately in an explicitly prepared schema-v3 project. Existing projects retain their v1/v2 serialization until preparation. Settings edits and resets must preserve the master and part references; accepting preparation must create one undo step for the entire state transition.

The core preparation contract rejects unchanged master bytes, non-neutral initial intent, unrelated metadata edits and reuse of an old selected-hand manifest. This is a metadata guard, not proof that a new hand library was constructed. Actual preparation with a selected hand still requires validation of its old receipt, construction of a new expression-neutral original, a genuinely rebuilt hand library and selected variant, and one final atomic project promotion. None of those receipts may be relabeled to adopt a new hash. Prepared v3 body-generation/refit entry points currently fail explicitly before starting a worker; the expression-aware composition must replace those temporary guards before product acceptance.

The two new internal worker operations stage `expression_human.blend` and independently verify it. They operate only on staged copies and never change project metadata. Closed recipes and protocol options bind the exact source, base, rig and twelve target identities; arbitrary target paths, keys or additional fields are rejected. The stage uses MPFB's real target loader. A separate Blender process manually parses the pinned gzip data, converts MakeHuman coordinates and constructs float32 keys without using that loader. It reproduces the source and all expected keys, compares the complete report, then reopens and observes the saved result before changing any values or refitting. Both reference and saved scenes exercise each unit at 0, 0.25, 0.5, 0.25 and 0, with bounded support/displacement and exact neutral restoration. Original keys, rest rig, skin weights, topology, UVs, materials and unrelated state must remain unchanged.

## Executed local evidence

Private evidence is outside Git under `evidence/facial001`; actual meshes/scenes and private source data are not uploaded.

| Gate | Result |
| --- | --- |
| Initial core/full regression, `full-regression-01.log` | 875 tests in 111.413 seconds; 861 passed, 14 existing Windows symlink-privilege skips. Required Qt enabled. This predates the preparation workers. |
| Full preparation source regression, `full-regression-03.log` | 880 tests in 111.849 seconds; 866 passed, 14 existing Windows symlink-privilege skips. Required Qt enabled. Attempt02 exposed a missing required argument in the new schema test; that fixture was corrected and all 32 focused contract/schema checks pass. The normal source launcher also passes SELF_TEST_OK with all 82 bridge modules present. |
| Core/independent policy checks, `preparation-contracts-02.log` | 32 tests pass. Closed neutral recipes, pinned options, shipped worker schemas and legacy metadata behavior are covered. |
| Actual preparation workers, `preparation-workers-01/summary.json` | Four real sources: short/light/narrow, middle/neutral, tall/refitted/wide and an owner-derived registered shorter hand. 160 independent reference and saved samples pass in 86.812 seconds. All original input hashes remain unchanged. This is worker compatibility evidence; it does not register a new compatible hand receipt or publish schema v3. |
| Real rehashed saved-scene faults, `preparation-faults-01/summary.json` | All eight reject in 55.359 seconds: active expression value, expression coordinate, skin weight, rig roll, UV, material, saved pose and unrelated key. Actual scene and report identities were recalculated. Positive accepted inputs are unchanged. |

The full product acceptance still requires transactional preparation, expression-aware body/face and selected-hand preservation, saved three-keyframe/25-frame Action reproduction, complete cache verification, actual full Qt/GPU playback, history/reset/watchers/cancellation/conflict checks, original-only CI, independent exact-head archive inspection and the actual Windows executable audit. Do not treat these worker checks as completion of that acceptance.

## Rights and dependencies

No dependency, model or asset was installed or acquired for this work. The twelve targets byte-match the already verified MPFB 2.0.18 archive and bundled core-data provenance. Existing local-preview, per-asset license and NoAI restrictions remain in force; preparation does not grant AI input, source redistribution or engine export rights. No purchased/private meshes, poses, scenes, trajectories or renders were uploaded.

Next task: compose and verify the source-bound expression-neutral master and genuine selected-hand library rebuild before enabling any desktop controls.
