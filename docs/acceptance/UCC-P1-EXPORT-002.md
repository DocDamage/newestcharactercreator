# UCC-P1-EXPORT-002 — explicit desktop Godot character package

Status: accepted for the two original authored private test characters in the
source desktop on Windows. Full blueprint goal remains incomplete.

Connect the accepted prepared material/hand/expression graph to a normal desktop
export action. Export a neutral character with its rig, facial shapes, UVs and
owned color/roughness; include no animation clips or nonlinear body-animation
corrective runtime. Preserve the editable master and project/history.

Dependencies: accepted material preparation, exact GLB evidence, unit-sum Godot
skin adapter and local cancellable worker infrastructure. Use installed tools
only. The normal workflow requires explicit per-use review of every named source
and a new chosen destination. Existing preview/catalog permissions stay unchanged.
NoAI/source restrictions remain in the review and output receipt.

Touched areas: closed export request, source/rights admission, destination staging,
Godot build/reopen verification, normal desktop dialog/action, tests and docs.
Reversibility: no existing destination is replaced; private staged output remains
recoverable on failure. Publish only an entirely verified new folder atomically.

Acceptance: real desktop action and chosen inputs; fresh Blender save/reopen
evidence; actual Godot import, unit-sum eight-influence skin, all 12 facial shapes,
material and saved-scene readback/render; relocated package reopening; exact
source/destination identity checks; deny rights/UE-only/NoAI erosion, stale edits,
collisions, redirects, cancellation, timeout and failed publication; full regression
and independent private evidence/hash audit. No placeholders or purchased sources.

Private acceptance uses original authored diagnostic characters and explicit
author-test permission only. It grants no owner/catalog or public distribution
permission. Normal UI reviews start unconfirmed.

## Verified behavior — November 15, 2026

File → Export private Godot character opens a review of the exact saved master,
expression library, material manifest and registered hand source. Each permission
starts unchecked; a review note and new destination are mandatory. The closed
`UCC_PRIVATE_STATIC_GODOT_EXPORT_V1` request preserves NoAI, rejects UE-only and
source-redistribution/AI grants, and does not promote catalog permissions.
The user selects installed Blender/Godot executables; there is no software scan,
installation, network operation or default upload.

The job freshly checks the source/hand/material in Blender, saves and independently
reopens the candidate, and requires byte-identical saved-master/no material repair.
It then imports the actual GLB, applies the established eight-influence unit-sum
skin adapter, packs a self-contained character scene and independently reopens
that saved scene in a fresh Godot process. Verification does not reapply the
adapter. The host checks bound reports, material values, saved-scene hashes and
decoded nonblank, unclipped neutral/expression PNGs before publication.

Exact project/source/proof/executable/adapter identities and hashes are guarded
throughout one deadline and cancellation scope. Verified files enter a private
staging folder under the chosen parent. Exclusive atomic rename publishes only
a new folder; existing destinations are never replaced. Failure after rename
rolls back only the job's identified folder. Project metadata, editable master,
backup history and session undo/redo are unchanged.

Actual desktop cases 367/369 use the normal action, real review dialog, QThread,
Blender workers and Godot processes; no worker/backend result substitution.
They test saved colors `#94603d`/roughness .65 and `#7d513c`/.72 with the original
registered shorter-left-hand character. All four inputs receive explicit private
author-test review. Both publish the chosen new folder and pass:

- 163 bones, 12 canonical facial shapes, zero animation clips;
- 14,517 seam-expanded vertices, 26,756 triangles and exact position/UV matching;
- all positive skin influences retained with exact unit-sum encoding;
- all 12 single-shape deformations compared to source GLB deltas, maximum error 0;
- rest skin error at most `6.47911406304047e-7` meters;
- saved color/roughness error below `1e-6`, metallic 0, no textures or override;
- distinct real neutral/expression renders, decoded and visually inspected.

Current host report admission was tightened after those UI successes. This
reader-only change did not alter the producer, UI success path or target scripts.
Audit 372 and the final acceptance audit re-read both unchanged published packages
with the final reader. Full regression 373 follows all Python changes.

Actual relocation 375 copies each `character.tscn` into a separate nested game
project, with no GLB and no external resource reference in the character scene.
Fresh Godot processes pass rig/skin/UV/material and all-12-shape comparisons.
Inspection reference files belong to the test, not the model's dependencies.
Earlier relocation helper 374 failed GDScript parsing before verification; its
logs remain retained. Only the corrected helper's two complete results are accepted.

Actual desktop negative checks 376 verify cancellation of live Blender PID 30016,
no published destination, no modal error and unchanged project/master/history.
Choosing a pre-existing destination produces an observed error dialog before any
Blender/Godot child starts and preserves its original marker. Actual fault 377
changes roughness in a private copy of the saved scene; fresh Godot verification
rejects with return code 2 and leaves the fault unchanged, demonstrating no repair.
Both original packages remain byte-identical.

Full required-Qt regression 373: **1,344 tests, 1,330 passed, 14 existing Windows
symlink-privilege skips**, 200.460 seconds, return code 0. All Python sources
predate that run. Eleven new tests cover rights, dialog defaults, stale sources,
concurrent save preservation, destination races/redirects, material-repair rejection
and post-rename journal failure rollback. Transaction fixtures are explicitly
synthetic unit data under `tests/fixtures`; they are not Blender or engine proof.
Existing process timeout coverage remains part of the full suite; no new real
end-to-end timeout run is claimed.

Versions: Python 3.12.10, PySide6 6.11.2, Blender 5.3.0 `02f0899d78e3`, MPFB 2.0.18,
Godot 4.7.1 stable `a13da4feb8d8aefc283c3763d33a2f170a18d541`, RTX 3060 12 GB,
Mobile/Vulkan, NVIDIA 610.88. Exact commands, return codes, logs, source/output
hashes and screenshots remain in private `evidence/export001` records 365–378.

## Limits and next task

This exports a static prepared material-bound human, its rig and facial shapes.
It includes no clips or nonlinear body-motion corrective runtime. Other character
families, arbitrary rigs, paid asset permissions, artist quality, textures,
Unity/Unreal and sprite exports remain unverified by this task. No dependency,
license or NoAI policy changes; no installation, public upload, commit/push/merge,
owner-launcher update or frozen executable acceptance.

Reproduce from this source checkout: open a supported saved material-bound
character with applied body/face intent and no animation references; choose the
File export action, review each exact source for this use, enter a new folder and
choose installed tools. Open the resulting `project.godot` for preview or use
`character.tscn` in a Godot 4.7 project.

The single next task is a current private Windows package: bundle the new static
Godot adapter resources and verify the actual frozen desktop/worker export path.
The old frozen archive and owner's shortcut do not contain these source changes.
This following gate is now recorded in [private package acceptance](UCC-P1-PKG-002.md);
the owner shortcut remains unchanged.

API references: [Godot mesh baking](https://docs.godotengine.org/en/stable/classes/class_meshinstance3d.html)
and [scene import options](https://docs.godotengine.org/en/stable/classes/class_resourceimporterscene.html).
