# Locked blueprint requirements and acceptance map

Updated November 16, 2026. Objective: complete the entire locked
`UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`, preserving the existing stack,
working features, originals, privacy and per-use source rights. This objective
remains active across milestones. No row below implies project completion.

`Scoped` means the linked record establishes only its documented specimen,
version and workflow. `Open` means product acceptance is still required, even
where source code, diagnostics or a partial implementation exists. Historical
blueprint checkboxes are not current evidence. Every scope extension needs its
own actual application evidence; unit tests and CI status alone are insufficient.

## Current batch and shared contracts

| Task | Dependencies | Owner/files | Measurable exit |
| --- | --- | --- | --- |
| UNITY-A transaction | Accepted source 540, runtime source 575, engine/runtime 576 | Transaction worker: `jobs/unity_export*.py`, focused tests; coordinated optional verifier arguments | Exact project/revision/source/rights/material/executable/resource guards; one deadline/cancel; sealed enumerated payload; new-folder publication; final delivered-byte verification; rollback and fault evidence |
| UNITY-B desktop | UNITY-A API | Desktop worker: Unity dialog/workflow, `desktop/window.py`, its two focused test modules | Explicit per-source rights and installed editor selection; new-folder destination; responsive progress/cancel; actionable errors; truthful completion through normal controls |
| UNITY-C package | Integrated A/B, final source freeze | Verification worker: independent publication tests, package/Qt workflow checks, private package harness | Current resource-complete frozen executable performs actual desktop export; independently audited payload/evidence; owner launcher/package preserved |
| UNREAL-007 source | Accepted finite original-source/native baseline 006 | Transaction worker: Unreal source preparation/reference/FBX metadata/worker and focused tests | Standard staged/fresh source jobs, original raw bone bases and complete source closure, explicit Unreal permissions, unchanged originals and no private baseline dependencies |
| UNREAL-007 engine/interface | Accepted 006 and source contract | Desktop worker: first-party observer/toolchain/engine jobs, then Qt controls | Portable observer-free project, installed-tool preflight, source/native import and read-only reopen, final delivered-byte verification and ordinary desktop action |
| UNREAL-007 independent admission | Same fixed profile/caps as 006 | Verification worker: bounded native decoder/math/material checks and fault tests | All thirteen source-derived gates, exact saved/reopened data, independent publication/package acceptance; no GPU or distribution inference |
| Full requirements/integration | All batches | Primary: this map, acceptance/status/handoff, integration and GitHub | Review exact diff and evidence; maintain every open requirement; commit/push cadence; draft milestone PR; merge only after all acceptance/check gates |

Agreed transaction API: `export_unity(store, *, request, destination,
blender_exe, worker_script, mpfb_data_dir, unity_exe, cancel=None,
timeout_s=3600, progress=None) -> UnityExport`. Request is the existing closed
`UnityExportRequest`; destination is `ExportDestination`. Result binds destination,
request/receipt/master hashes, private workdir and measured position/normal maxima.
Shared progress events describe real stages. Original-master vectors remain
private. Verification of a byte-identical final-project copy must continuously
guard the actual published payload. Changes to verifier arguments are owned by
the transaction worker. Workers do not perform GitHub mutations.

Baseline reused: checkpoint `d40a04f`; [Unity acceptance](acceptance/UCC-P1-UNITY-001.md)
and [numerics](acceptance/UCC-P1-UNITY-001-NUMERICS.md), private receipts 540/575/576.
These establish 178 diagnostic states and 356 images, exact native position bytes,
3.526 micrometre maximum observed source position difference and 0.220184 degree
normal difference. They establish no shipping animation library, artist approval,
publication, player build or broad compatibility. Baseline regression: 1,391 passed,
14 existing Windows symlink skips. Repeat only checks invalidated by changes.

Current API evidence: actual complete transaction582 and independent persisted
audit pass all 62 delivered files, 356 images and 5,168,052 exact native position
byte comparisons while preserving source/master/history. Final streaming-guard
regression590 passes 1,449 tests with 14 existing skips, including genuine Windows
junction, nested-budget and traversal faults. Current normal frozen589 positive,
collision and live cancellation plus independent audits pass locally. A/B are
merged through PR69/70 after final-head checks and artifact audits. Package
interval C remains open for the newly discovered receipt-cutoff correction. See the Unity record for
precise scope and private evidence identifiers.

Actual [Unreal baseline 006](acceptance/UCC-P1-UNREAL-001.md) now passes all
thirteen finite native bind gates in installed Unreal 5.9, with a separate
read-only reopen, four exact saved assets, 6,350 protected file bindings and
fourteen rejected host observation faults. No live engine faults were injected.
Production workflow 007 is in progress with separate source, engine/interface
and independent-verification ownership; primary owns contracts, shared resource
registration and the enclosing publication transaction. Current request/recipe
tests pass; no production Unreal export/UI/package success is claimed yet.

## Requirement-to-evidence and remaining tasks

Blueprint section references cover the locked decision record and detailed
requirements together. A row remains open until every listed subrequirement has
direct evidence. Requirements not fully evidenced are deliberately conservative.

| ID / blueprint sections | Requirement | Current evidence and explicit remaining work |
| --- | --- | --- |
| ENV-01 / 3, 7, 15.0, 18 | Installed Python/Blender/MPFB versions; operator, GUI/background, real save/reopen; compatibility profile | Scoped: existing P0 records and real humanoid acceptance; preserve pinned Blender 5.3 / MPFB 2.0.18. Open: compatibility migrations on version changes. |
| ENV-02 / 8, 15.0, 18 | Aseprite detection, configured AI endpoint probes, permissioned model inventory, GPU/disk capacity, dependency license inventory | Open: audit existing local reports before implementing missing inventory/probe workflows; no duplicate downloads or scans without consent. |
| CORE-01 / 5, 15.1 | Versioned character/part/animation/license contracts; schema invariants, unknown-version read-only behavior, migrations/backups | Scoped: existing core/storage/schema tests and saved projects. Open: audit full schema/migration/unknown-version workflow and catalog table coverage. |
| CORE-02 / 5, 6.4, 15.1 | Atomic save/load/autosave/history; stable IDs/source links; command validation and coherent undo/redo; crash/network-storage recovery | Scoped: saved native history and body/face/part acceptance. Open: complete autosave/crash/network-path/restart matrix and all edit commands. |
| CORE-03 / 5.4 | SQLite WAL catalog, hash deduplication, indexed provenance, reversible migration | Scoped: registered-source catalog workflows. Open: all required entity tables, migration recovery and asynchronous large-file hashing review. |
| CORE-04 / 4, 7, 13 | Isolated core/Qt/Blender/AI boundaries; versioned job protocol; shell-free subprocesses; staged original preservation | Scoped: existing worker suite and actual source jobs. Open: extend invariants/tests through every new operation. |
| CORE-05 / 7, 12, 15.1 | Cancellable bounded job queue, owned process-tree cleanup, progress/retry/logs, deterministic seeds/cache/version manifests | Scoped: actual Blender/Unity cancellation/deadline records. Open: unified queue/retry and complete reproducibility/resource cases. |
| CORE-06 / 1, 6.4, 15.2 | Text-driven shape edits and imported reference artwork alongside modular selection; constrained reviewed edit commands | Open: normal prompt/reference import-to-preview-to-Apply workflow, strict supported command schema, destructive/unsupported edit review and no prompt evaluation. Concept image generation alone does not satisfy text-driven character editing. |
| HUMAN-01 / 1, 6, 7, 15.2 | Real MPFB generation; persistent body/face/height/build/age morph controls in tested ranges; recipe retention | Scoped: [customization](acceptance/UCC-P1-CUSTOM-001.md), existing body/reference acceptance. Open: complete legal/tested morph inventory, extremes and asymmetry controls. |
| HUMAN-02 / 6.1, 6.3, 15.2 | Independent anatomical face/fingers/toes selection; full slot tree, symmetry/asymmetry/reset | Open: complete selection/edit behavior for every named anatomy slot, mirrored sides and digits. Existing hand category is only a subset. |
| PART-01 / 6.2, 6.3 | Real compatible interchangeable category, rest/socket/family/topology/weight/UV/material checks, 20-pose validation, undo | Scoped: [registered hands](acceptance/UCC-P1-PART-001.md). Open: other categories, seam/normal continuity and user-visible fit warnings. |
| PART-02 / 1, 6 | Heads/eyes/ears/noses/mouths/torso/arms/hands/fingers/legs/feet/toes modular variants | Open: dependency-ordered category expansion without blind slicing; retain border loops or reviewed transition geometry. |
| PART-03 / 1, 6, 9.5 | Clothing/hair/accessories, weapons/shields, attachments, clipping, weights and secondary rig compatibility | Open: normal inventory/fit/posed/deformation workflows and per-asset provenance. |
| PART-04 / 6.3 | Proxy/weight-transfer and reviewed AI-assisted fitting/retopology stages | Open: staged proposals, boundary matching, original preservation and actual fit/pose acceptance. |
| RIG-01 / 6, 9.3, 16.2 | Humanoid rig semantics/hierarchy/bind basis, A/T poses, normalized complete influences, 20 selected motions | Scoped: actual 163-bone static/bind/runtime diagnostics. Open: complete usable-motion/A-T-pose quality matrix; names alone never establish compatibility. |
| FACE-01 / 1, 9.6 | Real expression morphs, blink/gaze/eye controls, saved intent and playback | Scoped: [facial](acceptance/UCC-P1-FACIAL-001.md), bounded canonical controls. Open: full blink/eye closure/gaze and human visual approval. |
| FACE-02 / 9.6 | Working visemes AA/EE/IH/OH/OU/FV/MBP/L/rest; audio/text timing; supported engine morphs and 2D facial fallback | Open: actual phoneme/lip-sync deformation, timing provider and layer fallback; labels are insufficient. |
| MOTION-01 / 9.1, 15.2 | Usable idle/walk/run/jump/attack/hit/death on initial human | Scoped: existing intake/fit/cache records. Open: exact seven usable target actions, root/loop/feet/hands and visual/grasp acceptance. Diagnostics are not clips. |
| MOTION-02 / 9.2, 13.2 | Permissioned Fab acquisition; local FBX/GLB/glTF/BVH and licensed Unreal extraction; source FPS/duration/rig/provenance | Scoped: measured local FBX/source references. Open: format breadth, explicit supported Unreal path, per-pack audit and unknown-license states. No account scraping. |
| MOTION-03 / 9.3, 9.4 | MPFB/Rigify/UE4/UE5 Manny-Quinn/Mixamo/declared glTF maps; confidence, rest correction, translation scale, IK/root, baking | Scoped: narrow original-source/native fitting. Open: actual mixed-rig family tests, quaternion continuity, penetration/foot-slide/knee/hand checks and user-reviewed mappings. |
| MOTION-04 / 9.4, 15.4 | At least 100 usable licensed indexed clips; distinct preview/retarget/engine states, categories and policy tags | Open: count only accepted actual clips; 178 authored diagnostic states and 30 intake sources do not meet this target. |
| MOTION-05 / 9.5 | Speed/reverse/trim, layer/mask/transition, key editing, per-joint overrides, facial curves, root visualization/onion skins | Open: full non-destructive timeline controls, new baked actions/cache and normal playback acceptance. |
| MOTION-06 / 1, 7, 15.7 | Skeletal/physics/baked/AI-assisted secondary motion for hair/cape/wings/tail | Open: family-specific rigs, collision/interaction tests and reusable baked output. |
| EXPORT-01 / 11.1, 11.6 | Source-bound profiles; geometry/rig/morph/material/texture/scale/axis/root tests; truthful generated/offline/engine states | Scoped: Godot static and Unity preparation. Open: complete representative animation and target-engine validation through final user outputs. |
| EXPORT-02 / 11.2 | Godot GLB, skeleton/rest/skin/morph/material scene and idle/walk/attack playback | Scoped: [static Godot](acceptance/UCC-P1-EXPORT-002.md), actual app/package. Open: body motion/representative clips/root/scale and broader version coverage. |
| EXPORT-03 / 11.3 | Unreal skeletal FBX, per-clip AnimSequences, morph/material/bounds, Preview/PIE; later Manny/IK mapping | Scoped: [actual private Unreal 5.9 static bind import/reopen](acceptance/UCC-P1-UNREAL-001.md), thirteen independent field gates and exact saved/native data. Open: production portable export/desktop/package, live engine faults, shader/GPU/usable clips/PIE/player, Manny/IK and wider compatibility. |
| EXPORT-04 / 11.4 | Unity FBX, explicit Generic/Humanoid/Avatar choice, root/scale/morphs/clip playback | Scoped: [Unity](acceptance/UCC-P1-UNITY-001.md) source/bind/diagnostics, complete API and normal frozen589 private export/failure gates. Open: final remote checks/integration, Avatar/usable clips, player builds and full engine gate. |
| EXPORT-05 / 11.4 | URP reference materials, Built-in fallback; explicit pipeline/version compatibility | Scoped: pinned Built-in Forward/D3D11 diagnostics only. Open: URP, lighting/material breadth, performance and supported release matrix; HDRP remains later explicit target. |
| EXPORT-06 / 11.5 | Engine-neutral GLB/JSON/sprites; RPG Maker MZ layout preset; future Lumina adapter | Open: documented neutral handoff and MZ usage; Lumina deferred until schema supplied. Native Spine project writer is not promised; ordered layers/transforms/pivots are required. |
| RENDER-01 / 10.1 | Saved projection/yaw/pitch/roll/lens/scale/anchor/framing/shadow/alpha/lighting profiles; side/4/8/16/custom orbit/perspective | Scoped: fixed four/eight-direction output. Open: full camera profile controls/persistence, asymmetry-safe real left/right rendering and optional mirroring. |
| RENDER-02 / 10.2, 10.3, 15.3 | Transparent high-res RGBA, exact FPS/frame sampling, multi-angle/resolution motion, deterministic packing/JSON anchors/hitboxes/sRGB | Scoped: [sprites](acceptance/UCC-P1-SPRITE-002.md), [facial animation](acceptance/UCC-P1-SPRITE-003.md). Open: body-motion eight-direction walk at 64/128, 32/256/custom, complete settings/metadata and cross-engine sprite use. |
| RENDER-03 / 10.3 | Separated part/facial masks/layers with occlusion/draw-order/pivots and editable high-resolution intermediates | Open: genuine independently rendered layers and recomposition/ordering tests, including attachments. |
| RENDER-04 / 10.3, 10.4 | Stable pixel grid, deterministic palette/source/dither/nearest rules, SNES-inspired and high-detail styles, pixel-textured 3D | Open: actual style pipeline and artist review; low-resolution rendering is not sufficient. |
| RENDER-05 / 10.3 | No blanks/halos/clipping/overlap/flicker, exact counts/pivots, extrema framing, hands/feet quality | Scoped: source-bound raster and atlas checks. Open: full body-motion/equipment/style/visual matrix and golden views. |
| RENDER-06 / 10.5 | Existing Aseprite CLI integration, layered native project import/roundtrip, retained editable sources | Open: verified configured-tool roundtrip and metadata alignment without bundling unlicensed executables. |
| RENDER-07 / 1, 11.2 | True side-plane 3D, sprites in 3D and orthographic full-3D 2.5D workflows | Open: actual target-engine scenes and normal export controls; no menu-only acceptance. |
| UI-01 / 12.1 | Standalone offline Windows app; beginner Base/Body/Face/Parts/Outfit/Animate/Export guidance, presets/before-after/reset | Scoped: functioning Qt creator/source workflows. Open: complete guided non-artist journey and tested ordinary-user acceptance. |
| UI-02 / 12.1 | Advanced docks, selection tree, precise transforms, bone/morph/weights/rig/camera/sheets/provenance/telemetry; Open in Blender | Open: audit existing advanced controls, implement missing workstation behavior and preserve manual-edit warnings. |
| UI-03 / 12.2 | Bundled offline Three.js GLB viewer; orbit/pan/pick stable IDs, gizmos constrained commands, overlays/symmetry/pose/material/screenshot | Scoped: actual native GPU previews in current app. Open: audit approved viewport/ADR against locked Three.js requirement, full picking/gizmo/overlay behavior; no silent stack substitution. |
| UI-04 / 12, 16.4 | Responsive progress/cancel/retry/logs, retained preview, keyboard/focus, DPI 100/125/150/200%, display-layout restoration | Open: full accessibility, off-screen recovery and end-to-end failure matrix; existing busy/cancel checks are scoped. |
| UI-05 / 12.2, 13 | Local trusted content, strict typed bridge, no unrestricted navigation/evaluation; no inert controls | Open: audit all bridge commands/navigation and each newly exposed control; keep unimplemented features unavailable. |
| UI-06 / 11.6, 15.3 | GUI-visible export quality and compatibility report with truthful generated/offline/engine status | Open: inspect actual report UX and per-profile failures/capabilities; a success message or private receipt alone does not close this requirement. |
| AI-01 / 1, 8.1, 8.5 | Explicit local/cloud/provider/job choice; typed probe/models/validate/submit/poll/cancel capabilities | Open: actual configured provider flows with no default upload or guessed capabilities. |
| AI-02 / 8.2, 8.3 | Existing ComfyUI and WebUI APIs, validated workflow/node/model selection, owned progress/history/cancel; no unrelated checkpoint/job changes | Open: live opt-in endpoints, offline/error/recovery tests and explicit settings restoration where needed. |
| AI-03 / 8.4 | Selected folders/drives/permissioned whole-PC discovery with exclusions/estimates/progress/cancel/denied-drive recovery | Scoped: earlier read-only scanner tests. Open: complete normal UI modes and safe type/size/hash/license/confidence/dedup records; unknown stays unknown. |
| AI-04 / 8.4, 13 | Safe headers/metadata only, no pickle/model execution, no reparse loops/unselected network paths or automatic moves/deletes | Open: extend scanner safety tests through every supported format and root mode. |
| AI-05 / 8.4 | One GPU-heavy job; 12 GB VRAM preflight, CPU/RAM/disk budgets, approved unload/low-memory retry, cancel/OOM recovery | Open: actual resource queue/backend contention and recovery acceptance on target hardware. |
| AI-06 / 8.5, 15.6 | Text concepts/reference variation/turnarounds/isolated parts/outfits/textures/normal-mask/segmentation/facial workflows | Open: tested compatible templates, prompts/seeds/model/scheduler/size/source provenance and review-only Apply. |
| AI-07 / 2, 6, 15.6 | Image-guided compatible part construction/procedural edits, topology/UV/fit/skin/seam/deformation review and repair | Open: real proposal-to-review-to-attachment flow; reference images never establish clean meshes. |
| FAMILY-01 / 1, 2, 6, 15.7 | Humans/races/monsters/animals/quadrupeds/dragons/robots/unusual bodies | Open: separate family-specific topology/rig/slots/units/morph/capability/export/retarget profiles; humanoid remains first. |
| FAMILY-02 / 15.7 | Species joints/movement/nonhuman clips, wings/tails/capes, quality automation and lower LODs | Open: actual family deformation/secondary/engine workflows and reviewed LOD derivation. |
| SAFETY-01 / 13.1, 18 | No silent installs/downloads; exact provenance/license/version/size/hash/disk/destination/approval; backups on replacement | Ongoing invariant. Open: audit any future installer/updater and archive traversal defenses before use. |
| SAFETY-02 / 13.1 | Validated roots/paths/jobs/ZIPs/endpoints; no prompt execution; remote auth/TLS only after consent; custom-node dependency review | Scoped: existing worker/scanner/license tests. Open: complete adversarial matrix through new features. |
| RIGHTS-01 / 13.2 | Per-asset/product/creator/acquisition/file hash/license/flags/NoAI/UE-only/source-repackage/public classification | Scoped: current source permission gates. Open: complete per-pack/catalog/license export review; unknown defaults non-distributable. |
| RIGHTS-02 / 13.3 | MPFB/Blender/Qt/Aseprite/model notices, redistribution obligations, expert review, distinct private/game/asset/creator distribution | Open: final software/content/legal review and intended distribution decision; no public release authorized. |
| QA-01 / 13.4 | Missing/wrong tools/context, worker crash, rig/rest/morph/negative-scale faults and source-preserving recovery | Scoped: existing source/job/fault acceptance. Open: complete normal workflow matrix for every adapter. |
| QA-02 / 13.4 | OOM/offline/node errors, removed drives/duplicate models/cloud consent, missing license, alpha/overflow, upgrade and network-storage faults | Open: all detailed blueprint rows need direct acceptance as features become dependency-ready. |
| QA-03 / 16.1 | Unit/fuzz/integration/opt-in AI/engine/golden visual/safety/regression classes | Scoped: checkpoint 1,405 tests and private actual jobs. Open: missing Unicode/long-path/malformed data/visual/property tests and full final-head regression. |
| QA-04 / 16.2 | Whole smoke matrix: generate/extreme morph/swap/A-T rig/viseme/actions/three engines/2D/restart/kill/offline AI | Open: end-to-end combined specimen acceptance; individual scoped records do not close this gate. |
| QA-05 / 16.3 | Head-specific CI checks and independently inspected artifacts, no private/licensed content/model downloads in CI | Ongoing invariant. Open: current milestone draft PR and exact-head checks/artifact audits; never cancel healthy jobs on observer timeout. |
| QA-06 / 14, 16.3 | Enforced lint/format, critical-area type checking, pytest and actual schema validation with appropriate dependency/version pinning | Open: audit configured tools and existing environment, wire missing quality gates without silent installation or unused dependencies. JSON parseability alone is not schema validation. |
| RELEASE-01 / 15.7 | Current frozen Windows normal workflow, installer/updater/recovery, opt-in crash diagnostics, signing/channels if distributing | Scoped: Godot/sprite and current Unity589 normal portable app/export/collision/livecancel, exact ZIP/extraction/startup. Open: final integration and full installation/update/rollback/product acceptance. Owner launcher remains preserved. |
| RELEASE-02 / 1, 15.7, 16 | Visual/usability approval, performance/VRAM/broad hardware, engine/version/player builds, documentation and distribution decision | Open: final audit of every row and all explicit blueprint requirements; only then project completion. |

## Integration and GitHub state at resumption

Worktree `ucc-godot-export/newestcharactercreator`, branch `feat/export-001-godot`,
clean at `d40a04fd4b18dbf7913ccdf4c2ba3b9b0a2dccb8`; remote branch matches.
Remote main is `2c03434c75034b8cfb810b0d38daeb00122f004e`. Eight earlier draft
PRs #61Ã¢â‚¬â€œ#68 remain open; they must not be recreated, discarded or silently merged.
Current branch descends from #68 (`3e23952`). No PR or workflow run exists for
the checkpoint branch at inspection. Main has no branch-protection entry or
ruleset returned; the user's explicit acceptance/check gates still apply.

At the first scheduled push, use one draft PR for the current milestone with
the verified parent/integration branch and clearly disclose inherited checkpoint
scope. Never merge unrelated older PRs merely to flatten the branch stack.
Commit/push each reviewable slice or at 60 active minutes; review staged source
for private data before pushing. A/B/C are separate acceptance merge intervals;
none is complete until its actual app/engine evidence and final-head checks pass.
Prune only proven merged task branches with no unique work or active checkout.
