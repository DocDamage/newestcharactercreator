# UCC-P1-PART-001 — compatible left-hand assets and atomic swapping

Status: real local library, revision API, desktop/GPU/history/reset/cancellation/conflict and watcher checks pass. The reproducible three-body/face gate also passes locally. Final local source regression passes; exact-head CI, artifact inspection and Windows package acceptance remain pending. This is one compatible part category; it does not complete the creator blueprint or approve human visual quality or engine imports. Further merges require owner approval.

## Behavior

The Character tab's **Left hand parts** group builds two real skinned hand assets from the saved character using the already-installed MPFB data. The choices are **Original hand**, **Shorter fingers** and **Longer fingers**. Choosing an item is provisional: it does not edit project metadata, change geometry or create a revision. **Apply selected hand** runs the real transaction, then commits the part reference and immutable master pointer together. Undo/redo restores both in one step.

**View saved character and hands** displays all 26,756 actual skin triangles through the existing static GPU renderer. A separate Blender observation measures the actual saved left-hand bounds; the camera uses those bounds rather than an inferred screen region. Face, whole-character and hand focus remain available. The view is static, uses the fixed clay shader, and does not certify material fidelity, animation clips or engine export.

Original restores the exact original master bytes and removes the hand selection. Existing body and facial settings are retained. Restore Original before changing body or face settings; those controls are disabled while a hand part is selected. After changing the character, build compatible hands again. Dirty metadata, animations, other attachments, unsupported sources and stale libraries cannot silently overwrite the character.

## Actual asset and fitting contract

This first adapter supports the pinned MPFB 2.0.18 base/default-rig family with canonical transforms and an unanimated neutral source. The actual anatomical root is `wrist.L`, parented to `lowerarm02.L`, with 20 bones in its hand branch and 163 bones in the complete default rig. No generic skeleton is forced onto another family.

Each standalone asset contains one real skin mesh and one default armature: 1,747 vertices and 1,735 polygons, original UVs/material dependencies, exact float32 weight memberships and bind data. It contains no hidden whole body, joint-cube substitute or extra scene objects. The region has one closed 22-vertex reference border, unchanged by both declared target supports. Finger-length targets use a fixed strength of 0.25. Each variant's displacement from the bound source must remain below 30 mm and preserve its wrist border within 1 micrometre. Pinned source topology, border, polygon IDs, data files and target hashes are checked independently by the core and bridge.

Installation consumes the standalone asset's real vertex IDs and parametric coordinate attributes. The 112 declared joint-helper coordinates supply the corresponding bind update. Skin stays joined in the original topology with shared wrist vertices, as permitted by the blueprint's component model. This avoids the shading failure observed in the earlier separate-mesh attachment experiment; that experiment remains unaccepted. This is a source-bound topology adapter, not arbitrary cutting, generic hand fitting or negative-scale mirroring.

Libraries are immutable project-local files under `parts/objects` and `parts/manifests`. Their closed canonical manifest binds original master, project identity, body/face intent, both actual asset files, independent geometry observations and retained rights. Existing project schemas v1/v2 remain unchanged; `parts` stores the selected manifest/variant identity. Building a library does not change the project revision.

## Independent revision and preservation

The stage reconstructs both real asset expectations from the original master, reads the standalone asset payloads, and independently reproduces the declared current hand state. The current saved scene must match before any proposed replacement is built. Active masters also require a matching immutable revision receipt; an unknown externally rehashed file cannot be adopted just because metadata names a registered hand.

The verifier repeats original-source reconstruction and observes the saved result without resetting its keys or repairing its rig. Full/visible skin, all original shape keys including facial keys, exact weights, topology, UV/material state, rest rig, modifier stack, transforms, rig controls and unrelated geometry must match. It then compares 20 saved-surface poses with 20 independent reference poses, including actual skin and normal hashes and exact restoration after every pose. Potential nonadjacent hand self-overlaps and hand/body overlaps are recorded. These observations do not constitute human clearance or visual approval.

All source, library, installed-data and worker-output identities are checked again before promotion. A complete expected project snapshot is checked under the metadata save lock, including protection against an external edit that did not increment its revision. Publication retains the conservative `generated_unverified` master state and proposed part status; it does not invent whole-character validation. Already-applied selections still undergo real verification and create no new revision. Original restores the original file bytes rather than resaving a nominally neutral scene.

Cancellation, process timeout, stale state and external save conflicts retain authoritative metadata/master. Prior immutable masters and receipts remain available for history. Focused static previews bind the saved project/master and their directories; changed inputs clear the CPU/GPU surface, hand bounds and watcher registrations.

## Executed evidence

Private files are outside Git under `evidence/parts001`. Purchased data and the owner's authoritative project are not mutation fixtures. Screenshots stay local and are not uploaded for AI inspection.

| Gate | Observed result |
| --- | --- |
| Final local source regression, `full-regression-03.log` | 860 tests in 115.268 seconds: 846 passed, 14 existing Windows symlink-privilege skips; required Qt enabled. The earlier 858-test snapshot passed; subsequent attempt02 exposed an overly broad filename check in the new artifact-retention test. The corrected exact eleven-path whitelist passes without changing retained diagnostics. |
| Normal library API, `library-api-01` | Two real assets and canonical manifest registered through two workers; 40 skin-pose checks; project bytes/revision/master unchanged. |
| Normal revision API, `revision-api-01` | Shorter, verified no-op, longer, shorter, original; 200 full-skin pose checks, atomic part/master changes, exact original reset, all prior masters preserved. |
| Actual desktop, `desktop-hand-suite-01` | Windows Qt/Blender/OpenGL on the short/light/narrow-face character: build/apply, provisional choice, complete focused GPU preview, different actual vertex buffers/framebuffers, one-step undo/save/redo/save, exact original reset preserving facial settings, cancellation and post-stage external conflict with preserved state reloaded. |
| Focused watchers, `static-hand-watchers-01` | Disposable project and master mutations clear full CPU/GPU data, hand camera bounds and all registrations; two files and three directories watched. Accepted originals unchanged. |
| Saved-scene faults, `revision-scene-faults-01` | Positive reference accepted; eight actual rehashed scene/report faults rejected: one-ULP strength, key coordinate, one-ULP weight, rest roll, UV, material, saved pose and unrelated key. Valid verification retains all 40 pose checks; corrupt saved states reject before that traversal. |
| Standalone asset faults, `product-hand-faults-01` | Eight rehashed assets rejected by the normal independent worker, including geometry, coordinate attribute, weight, ID, rest, UV, modifier settings and saved pose. |
| Three-body/face repository gate, `formal-hand-gate-01/hand_parts_summary.json` | Passed in 489.172 seconds: three actual body/face cases, six real hand assets, 120 library skin-pose checks plus 360 revision pose checks, exact resets and zero potential-overlap poses in all nine selections. Additional real no-op/reference verification, pre/post-stage cancellation, subprocess timeout, post-stage external save, unknown rehashed master rejection and eight rehashed saved-scene faults pass. Original projects/masters and installed assets remain unchanged. |

Reproduce on an already-configured Blender/MPFB installation:

```text
python ci/verify_custom_face.py --blender <installed-blender> --outdir <new-face-output>
python ci/verify_hand_parts.py --blender <installed-blender> --source-root <new-face-output> --outdir <new-hand-output>
```

Linux CI adds this gate after the existing face gate and retains only `hand_parts_summary.json`. Existing regression/native-fit/body-contact/symmetric gates, official download checks and timeouts remain unchanged. Expected Linux diagnostic totals become seven regression, five native-fit, five body-contact and six symmetric JSON records; all 23 require inspection before acceptance.

## Rights and remaining work

No software, dependency, model or asset was installed/downloaded locally. Only the already-installed, pinned MPFB data is used. Original source rights remain attached; manifests conservatively deny AI input, automatic engine-export authorization and source redistribution. Local preview permission does not grant those rights.

Exact-head CI/archive/Windows executable checks and review remain required. Final local regression passes above; source launcher SELF_TEST_OK and all 79 bundled bridge modules are present. All twelve protected owner inputs, launchers and accepted animation evidence files retain their hashes. Preflight 3/3 and guardrails 12/12 pass locally; the three-case gate is accepted above. Arbitrary body/rig compatibility, additional part categories, changing body/face with a selected part, detached engine meshes, facial animation, broad clip compatibility and actual engine imports remain outside this slice. The broader blueprint goal remains incomplete.
