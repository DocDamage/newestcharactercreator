# UNIVERSAL AI CHARACTER CREATOR — DEVELOPMENT AGENT HANDOFF

**Prepared:** November 11, 2026 (America/New_York; post-merge GitHub runs occurred November 12 UTC)  
**Repository:** https://github.com/DocDamage/newestcharactercreator  
**Authoritative branch:** `main`  
**Verified main HEAD / PR #32 merge commit:** `8f55655481e64dd3efe62d7fccb56e8f0ce3cc1c`  
**Merge state:** PR #32 **MERGED** 2026-11-12 00:11:59 UTC; PRs #24–#32 merged.  
**CI state:** **ALL FIVE** workflows **passed** on the above *main* commit.  
**Next suggested task ID:** `UCC-P1-ANIM-004` — explicit BVH→MPFB rest-space/bone-roll calibration, **not** speculative complete retargeting.

> **Instruction to the next coding agent:** Continue development of this **existing, working repo** from `main`. Do not restart, recreate the scaffold, re-ask the 39-character-creator qualification questions, or claim unsupported features. Read `AGENTS.md` and `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` before editing. Do a small, tested vertical slice, use a feature branch and open a PR. Only claim capabilities proven by real Blender/MPFB or target-engine testing. Never upload the user's private Fab animation files. **PR #32 has already merged.**

## 1. Product intent, environment and nonnegotiables

The Universal AI Character Creator is a local-first, modular character-authoring workstation intended to grow into one workflow for editable 3D humanoids, interchangeable parts, multiple character families, 2D/sprite rendering, and animations/exports usable in Godot, Unity and Unreal. It is **not yet** a finished universal character/animation editor.

- **Primary target:** Windows 11 desktop, NVIDIA RTX 3060 with 12 GB VRAM.
- **Implemented stack:** Python 3.12+, PySide6 desktop, versioned pure-Python UCC core, isolated Blender 5.3 worker, MakeHuman/MPFB, `.blend` master versions, bounded offline BVH/glTF inspection and static GLB preview.
- **Optional/future integrations:** user-installed ComfyUI and Stable Diffusion WebUI (read-only local API probes and limited opt-in workflows), locally supplied animation/Fab assets, Godot/Unity/Unreal, sprite atlases, and Aseprite integration.
- **Do not download/install without an explicit reviewed install decision** (source/version/license/size/hash/destination). No cloud AI or source upload by default. Do not scan the whole user's computer or ingest their Fab library without explicit approval.
- **No placeholders passed off as real functionality.** Clearly labeled, non-shipping synthetic fixtures may be used only for unit tests; integration proof MUST come from real Blender/MPFB, and engine proof MUST come from real engine imports.
- **Keep architecture isolated:** core must not import `bpy`, Qt or AI runtimes. Put Blender-dependent work only in `blender_bridge`; make fixed, versioned JSON workers; no arbitrary Python evaluation or user-supplied scripts.
- **Preserve originals:** staged jobs under `.ucc-jobs/`; immutable content-addressed masters under `master/versions/<sha256>.blend`; revision-checked atomic project JSON promotion; cancellation and stale-source detection; independent Blender reopen and integrity checks.
- **Licensing:** `LicensePolicy.local_preview_allowed` defaults to `False` and must be explicitly reviewed; UE-only assets are blocked from local Blender preview. Asset-specific source rights and engine rights are separate; user attestation is **not** a legal review or permission to redistribute, export or train AI.
- See the full operating contract in [`AGENTS.md`](https://github.com/DocDamage/newestcharactercreator/blob/main/AGENTS.md), the locked decisions in [`UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`](https://github.com/DocDamage/newestcharactercreator/blob/main/UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md), and repo docs. No unsolicited stack replacement.

## 2. Current verified state — what actually works

**All statements here are backed by the existing repository or the post-merge GitHub Actions; they are not claims about the owner's own Windows Blender installation.**

| Area | Verified capability | Important boundary |
|---|---|---|
| Desktop | Real PySide6 alpha: project new/open/save, metadata/slider editing, undo/redo, animation library, error handling, cancellable background jobs and opt-in Blender actions | Windows CI uses Qt offscreen; local GPU/render/DPI experience untested |
| MPFB create | Official Blender 5.3 + MPFB generated and reopened a real humanoid with **19,158 body vertices and 163 armature bones** | User's Windows Blender/MPFB binary/setup still unverified |
| Morph controls | Saved normalized Height, Muscle, Weight passed to actual MPFB macro targets; non-neutral and neutral evaluated vertex hashes differ | Sliders are not live modification; values are not physical meters/kg |
| Existing master refit | Reapplies saved MPFB macro targets on staged `.blend`, refits **existing** armature, independently reopens, checks preserved vertex skin weights and commits only a new SHA version | May block attached parts/animations; visual fit not certified |
| 3D preview | Locally converts saved master to **evaluated-geometry-baked static GLB**; interactive orbit/pan/zoom in Qt; bounds checked | No skin animation playback, materials/textures/PBR certification or engine export |
| Static skinning | Real temporary 20° rotation of the `head` bone moves **4,451 evaluated mesh vertices**, then restores neutral pose; two Blender processes agree | A pose response does not establish natural-looking animation |
| Original keyframe timeline | Real temporary Blender Action keyed on frames 1/13/25 at 24 fps, sampled on 1/7/13/19/25; measured movements **0/4,451/4,451/4,451/0**, true interpolated geometry | This is an original CI diagnostic, not user animation playback |
| Selected BVH motion | Chosen local BVH's actual source rotation values can create temporary Action on an **exactly named** weighted MPFB bone; two processes compare source and geometry hashes | No automatic Mixamo/UE alias mapping, translation or rest-space retargeting |
| Two-to-four-bone BVH | Requires direct source/target parent chain, exact weighted deform-bone names, explicit BVH up-axis, XYZ order, bounded 1–45° deltas, ≥0.90 rest direction cosine, per-bone geometry movement; tests two processes | No bone-roll conversion, arbitrary skeleton, full-body retargeting or export; for **two bones** one length ratio is **measured**, uniform multi-segment scale is **not** proven |
| File security | Immutable SHA-addressed masters; original/worker copies hashed; project identity/revision guarded; cancellation and errors do not promote stale results | Stress testing on large private projects and actual Windows Blender remains outstanding |
| Animation catalog | Private local SQLite source/hash/license index, bounded read-only BVH/glTF metadata parsing, conservative bone-name mapping candidates | No promised 100+ usable/retargeted clips; do not mistake metadata inspection for animation |
| AI and sprites | Local-only optional ComfyUI/WebUI probes; existing PNG atlas features | Complete AI generation and original 3D-to-2D sprite renderer remain future work |
| Godot/Unity/Unreal | Structural GLB inspection and explicit export blockers | **No real game-engine import, animation playback or render has been verified.** |

**Canonical project state:** `geometry_state = generated_unverified` even after the above diagnostic proofs; do **not** silently mark a character engine-ready.

### Exact post-merge CI results (latest `main`)

Verified commit: `8f55655481e64dd3efe62d7fccb56e8f0ce3cc1c`

| Test/workflow | Status | GitHub Actions run |
|---|---|---|
| Actual Linux Blender **5.3.0** + MPFB 2.0.18 smoke, real create/refit/BVH/skinning | **PASS** | https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524182 |
| Core and worker tests, Windows/Linux, Python 3.12/3.13 | **PASS** | https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524241 |
| Desktop Qt tests, Windows/Linux, Python 3.12/3.13 | **PASS** | https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524205 |
| Preflight/unit security tests | **PASS** | https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524235 |
| Windows x64 frozen desktop alpha build/self-test | **PASS** | https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524248 |

Post-merge *real* Blender evidence includes:

- MPFB humanoid: **19,158** created body vertices; **163** reopened armature bones.
- Refitted master: **163** bones and **19,158 weighted vertices** retained.
- Evaluated static GLB from refitted body: **26,756** source triangles; **1,912** sampled by the bounded viewer.
- Single bone and keyframed tests: **4,451** mesh vertices moved under head rotation and at sampled non-neutral keyframes.
- Self-authored CI-only, 25-frame BVH: `head` motion changed real mesh; originals unchanged.
- Self-authored CI-only, 25-frame **`neck03 → head`** BVH: exact parent chain, chosen `Y_UP_TO_Z_UP` profile, child rest-direction alignment cosine **0.9948647067**. Individual 12° poses of each bone moved **4,451** evaluated vertices (`neck03` max local displacement ~0.0413064; `head` ~0.0330851). Two independent Blender processes matched on sample hashes, rig evidence and mapping. **Three distinct multi-bone frame geometry states** were measured.
- The CI report explicitly says `multibone_bvh_uniform_scale_verified=false`, `multibone_bvh_retargeting_verified=false`, `windows_verified=false`, `engine_imports_verified=[]`.
- Only JSON diagnostic artifacts were uploaded; **no proprietary BVH, paid Fab assets, user files, generated `.blend`, or GLB model files** were uploaded.

**Windows alpha (ephemeral, not installer):** GitHub run https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524248 → artifact `UCC-Desktop-Alpha-Windows-x64` (artifact ID `13903550487`, ~59.24 MB). Expected expiration **November 19, 2026 at 00:13:40 UTC**. Frozen self-test covers code/Qt startup, **not actual installed Blender execution on the user's Windows PC**. JSON integration artifact on run 43125524182 (ID `13903057330`) expires November 15, 2026 UTC.

## 3. PR milestones / merge history

The repo is not awaiting PR #32. All these are **merged**:

| PR | Purpose |
|---|---|
| [#24](https://github.com/DocDamage/newestcharactercreator/pull/24) | Fix/verify real Blender 5.3 + MPFB production worker save/reopen |
| [#25](https://github.com/DocDamage/newestcharactercreator/pull/25) | Real humanoid generation and immutable master promotion |
| [#26](https://github.com/DocDamage/newestcharactercreator/pull/26) | Static saved-master GLB preview |
| [#27](https://github.com/DocDamage/newestcharactercreator/pull/27) | Actual normalized height/muscle/weight phenotype deformation |
| [#28](https://github.com/DocDamage/newestcharactercreator/pull/28) | Existing-master MPFB macro refit with preserved skinning/weights |
| [#29](https://github.com/DocDamage/newestcharactercreator/pull/29) | Static skin-pose deformation diagnostic + fix active-morph GLB bake |
| [#30](https://github.com/DocDamage/newestcharactercreator/pull/30) | Genuine Blender Action and five-frame interpolation diagnostic |
| [#31](https://github.com/DocDamage/newestcharactercreator/pull/31) | User-selected, rights-attested local BVH on one exact-name weighted bone |
| [#32](https://github.com/DocDamage/newestcharactercreator/pull/32) | Explicit axis/rest/parent chain validation + two-to-four-bone BVH movement |

PR #32 merged on **2026-11-12 00:11:59 UTC** with commit `8f55655481e64dd3efe62d7fccb56e8f0ce3cc1c`. All five **post-merge** `main` runs above passed.

## 4. Architecture and code ownership

Read the source and tests *as they exist in current main*, not only older docs. Important entry points:

| Path | Responsibility |
|---|---|
| `AGENTS.md`, `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` | Absolute implementation rules and locked user decisions |
| `src/ucc/core/models.py`, `storage.py`, `master_versions.py` | Versioned project schema, immutable .blend versions and atomic/revision-checked metadata |
| `src/ucc/jobs/protocol.py` | Version 1 allowlisted worker requests/results and JSON validation |
| `src/ucc/jobs/runner.py` | Background Blender subprocess, staging, cancellation, timeouts and logs; `--disable-autoexec` |
| `src/ucc/jobs/humanoid_generation.py`, `body_revision.py` | Genuine MPFB generation and safe existing-master refit orchestration |
| `src/ucc/jobs/pose_diagnostic.py`, `timeline_diagnostic.py` | Independent-process pose and original Action keyframe proof |
| `src/ucc/jobs/bvh_clip_diagnostic.py` | Selected local source, reviewed-rights gate, double Blender jobs, immutable hash checks |
| `src/ucc/jobs/multibone_evidence.py` | Validate every mapped bone, explicit parent/root constraints, axis/rest evidence, per-frame/rig hashes, and no unsupported claims |
| `blender_bridge/entrypoint.py` | **Only approved Blender worker dispatcher**; do not bypass it |
| `blender_bridge/mpfb_service.py`, `morphs.py`, `refit_revision.py` | Real MPFB adapter, shape-key evaluation and existing rig integrity |
| `blender_bridge/pose_deformation.py`, `timeline_animation.py` | Actual evaluated mesh and Action timeline diagnostic |
| `blender_bridge/bvh_motion.py`, `bvh_clip_probe.py`, `bvh_multichain.py` | BVH parsing/frames, single-bone source motion, exact-name 2–4 bone chain and rest-direction checks |
| `src/ucc/animations/metadata.py`, `candidate_mapping.py`, `catalog.py` | Bounded local animation metadata, name candidates (NOT retargeting), private catalog |
| `src/ucc/library/provenance.py` | Asset-specific rights, `local_preview_allowed` / UE-only / NoAI / export / redistribution gates |
| `src/ucc/desktop/window.py`, `panes.py`, `generation.py`, `animation_results.py`, `mesh_viewer.py` | Qt user actions, source/rights and up-axis selectors, local worker binding, report formatting, static preview |
| `src/ucc/preview/glb_mesh.py`, `blender_bridge/preview_export.py` | Bounded GLB geometry reader and **evaluated** static shape-baked GLB exporter |
| `ci/verify_project_generation.py` and `.github/workflows/mpfb-cloud-smoke.yml` | Genuine official Blender 5.3 + MPFB create/refit/pose/BVH integrated proof |
| `tests/` | Unit and Qt regression tests. Synthetic inputs **do not** substitute for real Blender integration |

**Technical debt to avoid growing:** `src/ucc/desktop/window.py` is now approximately **933 lines**, beyond the repo's ~300–500 LOC modularity target. Split new functionality into dedicated controller/action modules instead of adding another 150 lines there. The currently committed README and `docs/STATUS.md` still contain historical wording such as “proposed PR #32” / “PR #32 open” even though GitHub confirms it has merged; update or mark those passages as historical in an early docs-only change. Other older integration docs also intentionally describe earlier states—do not treat them as current truth.

### Current job and licensing gates

- Job protocol is **v1**, with allowlisted ops such as `create_human`, `refit_human`, `export_preview_glb`, `verify_skin_deformation`, `verify_keyframed_timeline`, `verify_local_bvh_motion`, `verify_multi_bvh_chain`.
- The multi-bone job must choose `axis_profile` explicitly: `Y_UP_TO_Z_UP` or `Z_UP_IDENTITY`. No automatic arbitrary matrices.
- BVH motion tests are strictly offline: only **regular, selected** `.bvh` files, finite numeric values, 5–240 frames for worker preview, bounded file size, exact bone names and source paths. Two worker runs receive private copies in `.ucc-jobs/` and must agree on source hash and actual rig motion.
- UI asks for source provider, license name, source URI and an explicit local-Blender-use attestation. A UI checkbox is **not** independent proof of actual legal rights. Do not allow UE-only sources into Blender; no AI/cloud/training/export permission implied.
- The two-bone CI example represents **one** link: direction measured ~0.995; length ratio measured, but cross-link uniform-scale cannot be claimed until three or more joint bones.
- Source motion currently uses **local Euler rotation deltas** and deliberately ignores root translation. Matching bone parents/rest vectors is not equivalent to bone-roll or rest-matrix calibration. **Never set `retargeting_verified=true` at this stage.**

## 5. How to build, test and run

Source checkout (Windows PowerShell; explicitly choose to install these free packages locally):

```powershell
git clone https://github.com/DocDamage/newestcharactercreator.git
cd newestcharactercreator
git switch main
git pull --ff-only
py -3 -m pip install -e ".[desktop,sprites]"
py -3 -m ucc.desktop
```

To use the **Windows alpha without Python**, download the successful Actions run artifact above, extract it, keep the complete `UCC-Desktop-Alpha` folder, and run the EXE inside it. It is unsigned and **not a public installer**. It bundles first-party bridge scripts, **not** Blender, MPFB, Fab assets or checkpoints.

Useful source checks (from repo root; use Python 3.12+ and appropriate optional packages):

```powershell
py -3 -m compileall -q src blender_bridge
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s Stage0_Starter/tests -v
py -3 -m unittest discover -s Development_Guardrails/tests -v
```

Desktop/Qt smoke (PySide6 installed; in CI it uses `QT_QPA_PLATFORM=offscreen`):

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
py -3 -m unittest discover -s tests -p test_desktop_qt.py -v
py -3 -m unittest discover -s tests -p test_preview_qt.py -v
Remove-Item Env:\QT_QPA_PLATFORM
```

**Genuine Blender/MPFB integration:** workflow `.github/workflows/mpfb-cloud-smoke.yml` runs official Blender 5.3 + MPFB in an isolated Linux runner using `ci/run_mpfb_cloud_smoke.sh` and `ci/verify_project_generation.py`. It downloads dependencies into the ephemeral runner; do not execute that downloading script on the owner's PC without approval. On Windows, the user selects *their installed* Blender executable; the worker requires enabled MPFB. CI success does **not** certify that installation.

## 6. Recommended next implementation — `UCC-P1-ANIM-004`

**Goal:** add a *verifiable, opt-in rest-space/roll-orientation calibration* slice for one compatible BVH→MPFB chain, without falsely calling it full retargeting. Prefer a small CI-original motion first; user-supplied real licensed clips will be a separate gate. Branch suggestion: `feat/bvh-rest-space-orientation-calibration`.

**Why this is next:** PR #32 already checks exact names, parents, explicit up-axis, rest **direction**, real skin weights and multi-bone motion. These checks do not uniquely define a complete bone frame: rotations **around the bone's long axis (bone roll)** remain ambiguous, and Euler XYZ numbers cannot safely be copied between arbitrary skeletons. Real-world Mixamo/Fab/UE clips may point in wrong directions even when geometry moves.

### Proposed implementation order

1. **Inspect existing code and contracts.** Read `AGENTS.md`, blueprint §9.4, `blender_bridge/bvh_motion.py`, `bvh_multichain.py`, `bvh_clip_probe.py`, `src/ucc/jobs/bvh_clip_diagnostic.py`, `multibone_evidence.py`, UI bindings, CI and tests. Confirm PR #32's merged state via GitHub before branching.
2. **Design a typed calibration contract** separate from existing 2–4-bone probes. Define source joint identity, source parent/rest offsets, explicit BVH up-axis/handedness, source Euler channel rotation **order**, target bone rest matrix/orientation, per-bone axis/roll offset and required user review. Include schema/version, SHA of source BVH/master, and rejection of ambiguous rest-frame solutions. Do not equate direction alignment with complete frame calibration.
3. **Derive transforms in controlled math**, ideally quaternions/matrices using Blender `mathutils` only inside `blender_bridge`. Verify source-to-target rest-basis and local/parent-frame conventions. Do not invent a universal Euler substitution formula; test order/composition and axis conversions against known analytical fixtures. If roll cannot be inferred from BVH offsets, require a **user-chosen or validated orientation profile** with explicit, reviewable parameters and fail closed otherwise.
4. **Test a small real MPFB chain** using a self-authored BVH in CI (e.g. `neck03 → head`). Create *two deliberately different* source rest-roll orientations under controlled setup; use actual rotations so the calibrated result can be distinguished from the old naïve Euler-delta path. Measure world/local pose matrices and evaluated mesh vertices for keyframes; require deterministic results from two independent Blender processes.
5. **Constrain observable claims:** first release should be something like `REST_BASIS_CALIBRATION_MEASURED_ON_TEST_CHAIN`, **not** `FULL_RETARGET_COMPLETE`. Distinguish three independent gates: (a) source rest pose & axes known, (b) source→target motion transform numerically correct, (c) actual skinned geometry/visual quality acceptable. Only mark a claim true if its specific gate passed.
6. **Maintain privacy:** treat reviewed local BVH rights and UE-only restrictions as before. No cloud sharing, no downloaded Fab assets, no `.blend`/BVH binary CI uploads. Keep immutable master and source bytes SHA-unchanged and verify project revision before showing results.
7. **Integrate into UI modestly:** add a small calibration/settings panel with explicit user choice, measurable failure messages and no automatic retarget button unless the mapping passes. Extract action/result logic from the oversized `window.py` into a bounded module. Avoid growing the monolith.
8. **Test every layer:** unit tests for right-handedness, Euler orders, axis conversion, parent-frame composition, zero-length offsets, opposite or near-parallel axes, mirrored left/right, nonuniform scale, missing bones, bad roll, timeouts, cancelled and stale jobs. Real Blender integration MUST show *correct geometric outcome*, not merely different geometry; also check QA/timing and rollback. Windows Qt and frozen packaging CI must pass before PR merge.
9. **Document exact limits and PR proof.** Output `Task ID`, `Changed files`, `Verified results`, `Blocked/unrun`, `License/dependency changes`, `Next action` in the PR and handoff.

### Acceptance criteria for the next PR

- Source and target rest orientation are measured and unambiguously defined for **one** controlled rig chain, with explicit axis and roll selection or a defensible mathematical recovery; incorrect/ambiguous configurations are rejected.
- At least one motion with a **nontrivial axis difference** is applied and compared against expected reference poses; two real Blender worker subprocesses agree on geometry, bone transforms and source/master hashes.
- Old PR #31 single-bone and PR #32 two-bone behavior remain intact, and all core/Qt/preflight/Windows package/real MPFB Linux integration CI passes on **the final PR head**.
- No `retargeting_verified=true` or `engine_import_verified=true` without real dedicated acceptance tests. Full-body mapping, user clip catalog and visual in-app playback remain subsequent milestones.

**After orientation calibration:** use **one** user-selected, explicitly licensed multi-bone animation already available on the owner's PC (do not ask them to upload a paid Fab pack to a public repo). Verify actual motion under multiple keyframes and visual quality in Blender, then develop an animated UCC viewer; only afterward tackle genuine skinned glTF/FBX export and real Godot/Unity/Unreal import/playback. One verified end-to-end clip precedes a 100+ animation goal.

## 7. Open blockers and pitfalls

- **Windows installation untested:** CI Windows packaging and Qt tests are not a real Blender/MPFB execution on the owner's machine. Request a test only when a task truly needs it; log Blender version, MPFB release/hash, success/failure, source SHA and privacy-safe diagnostics. No binary asset upload required by default.
- **License uncertainty:** existing UCC `LicensePolicy` handles preview vs engine export vs AI input/redistribution; user attestation is not provider contract review. UE-only/NoAI restrictions must continue to fail closed.
- **No real Fab motion assets in CI:** current successful BVH and multi-bone integration uses original 25-frame self-authored test motion, not proof for Mixamo, Fab, UE, FBX or other third-party rigs.
- **Limited BVH assumptions:** current multi-chain requires 2–4 bones, one direct chain, XYZ Euler source order, exact bone names and source/target parent names, movement <=45°, source y-up/z-up explicit choice, no root translation. Real clips with branches, different names or bone-roll conventions will be rejected.
- **One segment is not uniform scale proof.** PR #32 explicitly corrected this after review; a two-bone result only measures one ratio. Preserve this distinction in evidence and UI.
- **Outdated docs:** `README.md` and `docs/STATUS.md` still call some *already merged* PRs “proposed”/“current review”; correct this in the next documentation cleanup. `docs/integration/bvh-multibone-rest-gate.md` currently repeats the “Verification boundary” header; clean it up if touching docs. `pyproject.toml` contains an early pre-editor description; do not use it as a current feature list.
- **Complex UI file:** `src/ucc/desktop/window.py` is ~933 LOC. Isolate future animation panel/controller/report logic rather than appending another large method.
- **Actual engine readiness remains blocked:** no verified Godot/Unity/Unreal import, source skinning playback, art/texture quality, attachment fitting, public release license or installer certification. Do not remove export blockers until engine-specific tests run.
- **Not asynchronous:** do not promise to finish work later. Implement the requested increment in the same task/turn and report real CI status; if runners are queued, state that clearly and don't claim success early.

## 8. Ready-to-paste follow-on agent prompt

> Continue the **existing** Universal AI Character Creator in https://github.com/DocDamage/newestcharactercreator. `main` currently points to merged PR #32 commit `8f55655481e64dd3efe62d7fccb56e8f0ce3cc1c`; all five post-merge CI workflows passed. Read `AGENTS.md`, `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`, and this handoff. Do not restart the project. The current validated vertical slice uses real Blender 5.3/MPFB, 19,158-vertex humans, a 163-bone rig, source BVH rotation data, and an exact-name `neck03→head` 2-bone rest-direction check; 4,451 mesh vertices moved from each bone in CI. This is **not full retargeting**, Windows Blender success or engine export. Implement the next **small, real, validated** step toward BVH→MPFB *rest-space and bone-roll orientation calibration*, while preserving private assets, immutable masters, user-reviewed local rights, typed worker protocol, cancellation, and no fabricated success. Use a feature branch, tests, genuine Blender/MPFB integration, and open a PR. Update stale status docs, but don't relabel old tests as complete retarget. Report task ID, changed files, precise CI proof, blocked/unrun validation, dependency/license impacts and next action.

---

### Source-of-truth links

- Repo: https://github.com/DocDamage/newestcharactercreator
- Current merged work: https://github.com/DocDamage/newestcharactercreator/pull/32
- Latest real Blender test on **main**: https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524182
- Latest Windows alpha package on **main**: https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524248
- Latest core tests on **main**: https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524241
- Latest Qt tests on **main**: https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524205
- Latest preflight on **main**: https://github.com/DocDamage/newestcharactercreator/actions/runs/43125524235
- Current detailed multi-bone limits: https://github.com/DocDamage/newestcharactercreator/blob/main/docs/integration/bvh-multibone-rest-gate.md
- Operating contract: https://github.com/DocDamage/newestcharactercreator/blob/main/AGENTS.md
- Locked product blueprint: https://github.com/DocDamage/newestcharactercreator/blob/main/UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md

**End of verified handoff.**