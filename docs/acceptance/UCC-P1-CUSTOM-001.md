# UCC-P1-CUSTOM-001 — bounded persistent MPFB nose width

Status: technical acceptance complete at `c67f672db34640120705a3780cf1c143a3d69804` / draft PR #62. All five workflows pass; all four Linux archives and 22 diagnostic records are independently accepted. The exact-head Windows package's 72 bridge sources match Git and its extracted executable passes SELF_TEST_OK. The PR remains unmerged pending owner approval. This is one facial shape control, not part swapping, facial animation or completion of the creator blueprint. Human visual and engine approval remain unclaimed.

## Behavior and boundaries

The Character tab has a separate Face shape group. Nose width is normalized from 0 to 1, with neutral at 0.5. Moving it records intent. Save metadata, then use **Apply saved face shape to master** to run real installed MPFB targets and rig refit on private copies. No live geometry change is claimed. Generation and existing-body refit honor saved facial intent through a private composed transaction and publish one final immutable master to the user's project.

Only the exact MPFB 2.0.18 basemesh topology and default rig are supported. The worker checks the actual hierarchy/inheritance and canonical rig refit, neutral pose, transforms, modifier stack, registered MPFB object types and unanimated data. Attached parts, extra rigs, related mesh assets, linked/constrained sources, ambiguous or altered target keys and nested material node groups are rejected. Arbitrary bodies, detached parts, animation clips and game-engine compatibility remain unapproved.

Legacy schema-v1 projects load and serialize unchanged. A meaningful facial edit explicitly transitions to schema v2; a neutral edit on an untouched legacy project does not migrate it. Facial values reject Boolean, nonfinite, unknown and out-of-range input. Metadata history supports migration undo/redo, and the desktop adopts successfully saved master pointers into the same session history. Original masters remain immutable. Already-applied face settings undergo real independent verification and do not fabricate a new revision. A real target-value change smaller than the 1 μm diagnostic movement threshold still persists.

The closed recipe binds the original master and exact base mesh, default-rig definition and two bundled target digests. Core and Blender independently derive target strengths: `max(0, 0.5-value)` and `max(0, value-0.5)`, each at most 0.5. No user-supplied target path/name or substitute data is admitted. Discovery inspects only the single already-enabled MPFB extension through the selected Blender, without a drive scan, installation or download.

## Independent transaction

The stage worker checks all staged hashes, validates the original source and existing target coordinates/settings, loads the real bundled targets, refits through MPFB, and saves a separate scene/report. Unrelated shape keys/macros, exact float32 vertex-group weights, topology, UV coordinates, material/node state, object transforms, rig controls and unrelated mesh geometry are preserved. Movement outside declared target vertices is limited to numerical noise; total displacement is bounded by 0.08 world units or five percent of body span, whichever is smaller. These are implementation bounds, not physical calibration or visual approval.

A fresh verifier independently reconstructs the expected result from the bound original before opening the saved result. It does not refit or reapply target values to repair that saved result. Exact target strengths, canonical target coordinates, evaluated full/visible geometry, rest rig, skin and report observations must reproduce. Rehashing a corrupted scene and its report cannot bypass this reconstruction. Original and staged inputs, installed assets, project identity/revision and cancellation are checked before promotion. Crashes, worker errors, cancellation and stale results leave the original project authoritative.

Body-plus-face generation uses an isolated scratch project. Existing-body composition first validates the source through the facial workers, uses an explicitly private body-only metadata projection for the existing macro worker, restores facial intent, and independently checks the final face before one publication. The public legacy body-only APIs reject facial intent instead of discarding it.

## Executed local evidence

Private evidence is under `evidence/custom001`, outside Git. Test scenes derive from real, original MPFB-generated humans; purchased animation/assets and the owner's authoritative project are not used as mutation fixtures.

| Gate | Observed result |
| --- | --- |
| Final source regression, `full-regression-07.log` | 833 tests in 110.195 seconds: 819 passed, 14 Windows symlink-privilege skips. Required Qt was enabled. Earlier preflight 3/3, guardrail 12/12 and source launcher SELF_TEST_OK also passed. |
| Real stage/fresh reopen, `worker-suite-03` | Narrow, neutral, wide, intermediate and already-wide states passed. Seven coherently rehashed faults rejected: value, one-float32-ULP value, target coordinate, skin weight, rest bone, UV and material. |
| Public revision API, `api-suite-01` | Actual two-worker promotion, verified no-op, sub-1 μm intent edit, pre/post-stage cancellation, external-save conflict and actual subprocess timeout passed. |
| Reproducible repository gate, `formal-gate-01/custom_face_summary.json` | Three different body/face builds; existing-body refit retaining the wide setting; 80 transient head/neck/jaw/eye/arm poses with exact restoration; seven real rehashed faults; no-op/cancel/stale guards; installed assets unchanged. |
| Actual desktop, `desktop-suite-01/summary.json` | Real Qt save/apply, Blender asset inspection/stage/reopen, full OpenGL static face preview, pointer undo/save/redo/save, verified no-op, cooperative cancellation and real external-save conflict passed. |
| Full GPU geometry | All 26,756 triangles drawn, valid GL context, no GL error, nonblank and different neutral/widened framebuffers. Screenshots stayed private and were not uploaded for AI inspection. |
| Static watchers, `static-watchers-01/summary.json` | Both actual project-file and master-file mutations on disposable copies clear the full GPU surface. Two files and three directories are required and watched; cleared CPU/GPU data and registrations were checked. |

The sampled CPU preview retains its prior limits. Facial saved-master previews instead request a complete, bounded static surface (at most 100,000 triangles) and use the existing fixed local clay GPU renderer with face/whole-character focus. No asset shaders, animation playback or live morphing are introduced. Editing, applying, undoing/redoing and authoritative-input watcher changes clear stale previews.

An early generation test harness failed on a stale scratch revision and was corrected. A subsequent harness passed all three generation cases but used the wrong metadata method name before its final refit; that historical attempt remains partial. The independent continuation and the complete repository gate passed the refit. These failures are retained in local logs.

## Reproduction and CI

With the existing enabled MPFB profile and repository Python path:

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 ci/verify_custom_face.py --blender "C:/Program Files/Blender Foundation/Blender 5.3/blender.exe" --outdir "<new unused evidence directory>"
```

The Linux regression matrix adds this original-only gate after existing checks and retains only `custom_face_summary.json`. No prior assertions, official Blender origin/checksum or individual worker limits are weakened. Its bounded job allowance is 45 minutes, allowing headroom beyond the previously observed roughly 35-minute regression plus the new facial gate. Other suites retain their existing limits. Exact-head Linux and Windows results must be independently audited before claiming remote/package acceptance.

## Rights and remaining work

No dependencies, models or assets were installed/downloaded locally. The target/base/rig data already ship with MPFB. MPFB core assets are CC0; MPFB code is GPL. Sources: [official asset license](https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.ASSETS.md), [official licensing overview](https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md). Only application logic, schemas and original test code are committed; bundled target data, scenes, meshes and screenshots remain outside Git. Existing per-asset licensing and NoAI/export restrictions remain intact.

Human visual approval, arbitrary-shape/rig coverage, facial animation, detachable parts, and Godot/Unity/Unreal imports remain unrun/unapproved. The original animation milestone and owner's verified fitted-animation launcher remain preserved. Further merges require owner approval.
