# UCC-P1-ANIM-007C — measured catalog clips and project registration

Status: local metadata API, existing desktop Index workflow and fresh source-reference verification accepted; full project action registration remains incomplete. Local branch `feat/anim-007-registered-clips` builds on frozen draft PR #65 at `b873ed0013ff90cdfc24134eb7c70ccf073d876e`. This follow-up is not pushed or remotely accepted. PR #65 has passed Core, Qt, preflight and Windows; its independently audited Windows package contains all 89 exact-head bridge modules and its extracted executable passes all three self-tests. PR #65 Linux acceptance remains pending. PRs #61–65 remain draft and unmerged.

## Implemented metadata boundary

`ucc.jobs.fbx_catalog.measure_catalog_fbx` measures one already-indexed FBX asset with its unchanged reviewed local-preview policy. The existing importer requires one actual Action and evaluates the complete source timeline through two independent Blender processes. The coordinator checks their exact source identity, private snapshot, policy and source preservation before publishing.

The existing `AnimationCatalog` and stable `asset-id#clip-0000` convention are reused. A new aggregate `animation_fbx_intakes` table binds source and snapshot hashes, complete range/FPS/count observations, sampled skeleton identity and clip metadata. No project schema or project animation IDs change in this slice. Source poses remain in private job files; the database receipt contains bounded metadata only.

One SQLite transaction installs the clip, aggregate receipt and `METADATA_EXTRACTED` source state together. Cancellation and publication failures roll them back together. Compatible repeated measurement is idempotent; different measured identities cannot overwrite a clip. Original asset content and licensing remain immutable. Unreviewed/UE-only policies, source changes, escaped snapshots, disagreement and incompatible prior clips produce errors.

The measured track count describes changing sampled bone/object transforms, not the original FBX FCurves. Static bones are not declared animated merely because their armature object moves. Metadata extraction keeps target preview, retargeting and engine approval false.

The programmatic sequence is to index a selected source using `AnimationCatalog.index_file` with an explicitly reviewed local-preview policy, then call `measure_catalog_fbx` with that database, asset ID, installed Blender, bundled worker and private jobs directory. The existing desktop button is now **Index selected source**. With the explicit local Blender review selected, an FBX is indexed under that immutable policy and measured through the normal cancellable background worker. Without that review, indexing keeps the existing unreviewed metadata-only behavior and starts no Blender process. The button help explains both paths; successful measurement refreshes the complete catalog and describes source clips without applying them to the character. Existing unreviewed entries cannot silently acquire new permissions under the same ID.

## Verified source references

`ucc.jobs.catalog_clip.verify_catalog_fbx_clip` resolves one exact existing catalog clip ID against a caller-bound source SHA and complete reviewed policy. It checks bounded JSON/database fields, closed receipt schema, actual range/FPS/count relations, exact stored clip types and skeleton identity before starting workers. Unmeasured, unknown, stale, missing or malformed references are rejected. Policy equality includes NoAI and every export permission; this API cannot infer a review from the supplied project or relax the existing review.

A coherent stored receipt is still insufficient. The verifier repeats the normal complete two-worker Blender intake and compares it against the saved metadata/receipt without repairing either. A typed `VerifiedCatalogClip` binds the existing catalog ID, source SHA, exact policy, snapshot and receipt hashes, skeleton fingerprint and source timeline. Its target-preview and engine approvals remain false. Project admission must additionally prove the editable master's actual neutrality and preserve revision/history/source guards.

## Executed local evidence

Private evidence is outside Git under `evidence/anim007c`.

| Gate | Observed result |
| --- | --- |
| Focused catalog/intake boundaries | 38 tests; 37 passed, one existing Windows symlink skip |
| Initial API required-Qt regression | 943 tests in 113.788 seconds; 929 passed, 14 existing Windows symlink skips |
| Desktop wiring required-Qt regression | 951 tests in 115.024 seconds; 937 passed, 14 existing Windows symlink skips |
| Focused desktop/API smoke | 55 tests passed |
| Source-reference boundaries | 12 tests passed, including bounded/duplicate/nonfinite/type-mismatched metadata and coherent saved identity faults |
| Final required-Qt regression with references | 963 tests in 115.802 seconds; 949 passed, 14 existing Windows symlink skips |
| Actual fresh reference and coherent faults | Valid original source plus coherent Action/skeleton/FPS catalog rewrites: eight fresh Blender workers each inspect all 300 frames, total 2,400 source-frame observations in 29.359 seconds. The three rewrites reject with the precise identity failure; source and accepted baseline database remain byte-identical |
| Bound reference failures | Wrong caller source SHA, changed caller policy and missing receipt reject before any worker starts |
| Actual Qt Index button/background workflow | Original-only 300-frame/71-bone source measured by two fresh Blender workers in 6.781 seconds; both measured and unreviewed catalog entries displayed and database/project reopened |
| Actual cancellation and immutable policy | Cancel menu action after an observed live Blender PID stops the worker; no partial clip/receipt. Attempted upgrade of an old unreviewed ID rejects before any Blender job |
| Actual source launcher | Three-check SELF_TEST_OK; cancelled Blender PID independently confirmed exited |
| Earlier preflight and guardrails | 3 and 12 tests passed |
| Real original-only FBX intake | Two fresh normal Blender workers, each measuring all 300 frames, 71 bones and three roots at 30 FPS |
| Independent saved-result/catalog audit | Both complete snapshots and source hashes agree; actual imported range 2–301 retained; real Action identity, 72 sampled transform tracks, stable clip ID and database receipt verified after reopening |
| Failure boundaries | Changed source/policy, malformed report/snapshot, disagreement, escaped snapshot, cancellation, coherent conflicting Action and injected SQLite failure reject without partial clip publication |
| Source preservation/privacy | Original authored FBX unchanged; no purchased inputs, geometry or poses stored in the catalog or uploaded |

The original source is reused from the accepted original-only regional gate. This is an actual Blender source integration, not evidence of seven usable product actions. The first four API Python source/test files are frozen in `source-under-test-02.json`; an explicit AST/compiled-code comparison records LF normalization of the pre-existing catalog file. Desktop regression and genuine Qt intake/cancellation use the eight source/test files frozen in `source-under-test-04-desktop.json`. Final reference regression and actual coherent-fault checks use all eleven source/test files frozen in `source-under-test-05-reference.json`; the earlier eight files remain unchanged.

## Remaining acceptance

The existing Index control is wired; no Action is attached to an editable master. The new reference API validates source IDs; it does not attach them to a character. Still required: admitting those bound references into a character project, independently proving neutral-master provenance, history/save/reopen and stale-input behavior, supported edits with external clip references, seven appropriate usable actions, root/loop/foot quality, human visual/grasp review, and real engine imports. Arbitrary animated masters remain rejected by the existing edit guards. PR #65 remote Linux/artifact acceptance must finish before publishing this follow-up. No dependencies, software installation or asset permissions changed.
