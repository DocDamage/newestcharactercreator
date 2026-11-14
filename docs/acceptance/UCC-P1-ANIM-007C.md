# UCC-P1-ANIM-007C — measured catalog clips and project registration

Status: first local API slice accepted; full project action registration remains incomplete. Local branch `feat/anim-007-registered-clips` builds on frozen draft PR #65 at `b873ed0013ff90cdfc24134eb7c70ccf073d876e`. This follow-up is not pushed or remotely accepted. PR #65 has passed Core, Qt, preflight and Windows; its independently audited Windows package contains all 89 exact-head bridge modules and its extracted executable passes all three self-tests. PR #65 Linux acceptance remains pending. PRs #61–65 remain draft and unmerged.

## Implemented metadata boundary

`ucc.jobs.fbx_catalog.measure_catalog_fbx` measures one already-indexed FBX asset with its unchanged reviewed local-preview policy. The existing importer requires one actual Action and evaluates the complete source timeline through two independent Blender processes. The coordinator checks their exact source identity, private snapshot, policy and source preservation before publishing.

The existing `AnimationCatalog` and stable `asset-id#clip-0000` convention are reused. A new aggregate `animation_fbx_intakes` table binds source and snapshot hashes, complete range/FPS/count observations, sampled skeleton identity and clip metadata. No project schema or project animation IDs change in this slice. Source poses remain in private job files; the database receipt contains bounded metadata only.

One SQLite transaction installs the clip, aggregate receipt and `METADATA_EXTRACTED` source state together. Cancellation and publication failures roll them back together. Compatible repeated measurement is idempotent; different measured identities cannot overwrite a clip. Original asset content and licensing remain immutable. Unreviewed/UE-only policies, source changes, escaped snapshots, disagreement and incompatible prior clips produce errors.

The measured track count describes changing sampled bone/object transforms, not the original FBX FCurves. Static bones are not declared animated merely because their armature object moves. Metadata extraction keeps target preview, retargeting and engine approval false.

The programmatic sequence is to index a selected source using `AnimationCatalog.index_file` with an explicitly reviewed local-preview policy, then call `measure_catalog_fbx` with that database, asset ID, installed Blender, bundled worker and private jobs directory. Existing metadata-only indexing remains available; it does not manufacture FBX clips. Existing unreviewed entries cannot silently acquire new permissions under the same ID.

## Executed local evidence

Private evidence is outside Git under `evidence/anim007c`.

| Gate | Observed result |
| --- | --- |
| Focused catalog/intake boundaries | 38 tests; 37 passed, one existing Windows symlink skip |
| Full required-Qt regression on final LF source | 943 tests in 113.788 seconds; 929 passed, 14 existing Windows symlink skips |
| Earlier preflight and guardrails | 3 and 12 tests passed |
| Real original-only FBX intake | Two fresh normal Blender workers, each measuring all 300 frames, 71 bones and three roots at 30 FPS |
| Independent saved-result/catalog audit | Both complete snapshots and source hashes agree; actual imported range 2–301 retained; real Action identity, 72 sampled transform tracks, stable clip ID and database receipt verified after reopening |
| Failure boundaries | Changed source/policy, malformed report/snapshot, disagreement, escaped snapshot, cancellation, coherent conflicting Action and injected SQLite failure reject without partial clip publication |
| Source preservation/privacy | Original authored FBX unchanged; no purchased inputs, geometry or poses stored in the catalog or uploaded |

The original source is reused from the accepted original-only regional gate. This is an actual Blender source integration, not evidence of seven usable product actions. Four Python source/test files are frozen in `source-under-test-02.json`; an explicit AST/compiled-code comparison records LF normalization of the pre-existing catalog file. Final regression and genuine intake use those final bytes.

## Remaining acceptance

There is no new desktop control in this slice and no Action is attached to an editable master. Still required: desktop wiring, resolving registered catalog clip IDs in a character project, independently proving neutral-master provenance, history/save/reopen and stale-input behavior, supported edits with external clip references, seven appropriate usable actions, root/loop/foot quality, human visual/grasp review, and real engine imports. Arbitrary animated masters remain rejected by the existing edit guards. PR #65 remote Linux/artifact acceptance must finish before publishing this follow-up. No dependencies, software installation or asset permissions changed.
