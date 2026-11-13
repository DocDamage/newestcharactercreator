# UCC-P1-ANIM-006AA — explicit symmetric shoulder layers

Status: development; all five final-head workflows have not yet run for this change. Main remains unchanged. The existing owner launcher still selects its accepted V2 correction.

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

The first new original-source CI attempt stopped at its test precondition: the existing near-straight-arm source did not provide two continuously bent elbow poles. A constant 12-degree fixture variant then rejected at the unchanged palm rest-geometry agreement check (maximum observed source-normal difference about `1.43e-6`, above the existing `1e-6` bound). The separate symmetric fixture now adds a smooth 12-degree bend within the clip, retaining the old first/end poses. The old fixtures and all production rest, reachability, pole, angular and skin guards remain unchanged. This variant requires its own complete execution; neither stopped attempt is accepted.

## Pending acceptance

- Finish the independent complete body-area, enclosure and full-trunk comparison on the newly baked owned Action; its normal application playback cache already passes.
- Finish the new original-source/real-MPFB CI gate locally, then execute its separate Linux matrix job. It preserves the existing three integration suites and includes a full base/layer/cache/anatomical transaction and actual saved-scene faults.
- Verify actual RTX 3060 playback, source changes and report/receipt invalidation before changing the owner launcher.
- Open the feature PR and independently audit all five final-head workflows, including the Windows package and the new Linux diagnostics. Do not merge automatically.

## Limits and next task

This is an explicit measured correction for declared shoulder branches, with one preserved legacy base. It does not implement overlapping layers, automatic full-body contact solving, inferred grasp intent, arbitrary rigs or engine export. Uncertain enclosure classifications remain uncertainty. Synthetic CI clips do not establish compatibility with an owned animation pack. The Blender corrective modifier remains Blender-specific. Human visual/contact quality and game-engine imports remain unapproved.

Next task: complete the new saved Action's normal playback/anatomical acceptance and publish a private, reversible owner review only after those gates pass. No dependencies or software/model installs were added; the existing reviewed local-preview policy remains enforced.
