# UNIVERSAL AI CHARACTER CREATOR — DEVELOPMENT HANDOFF

**Project:** Universal AI Character Creator (UCC) / `newestcharactercreator`  
**Repository:** https://github.com/DocDamage/newestcharactercreator  
**Snapshot date:** November 11, 2026  
**Authoritative branch at audit:** `main`  
**Audited HEAD:** `e487e8ed6111bbd5996cf3a772a59e9f7cdcc009`  
**Phase:** Working Python core, desktop metadata workstation, static GLB preview and Windows alpha build; **NOT** a complete rigged character creator.  
**Purpose:** Enable another coding agent or developer to continue immediately in GitHub without re-interviewing the owner, restarting the application, confusing synthetic tests with runtime proof, or misrepresenting export readiness.

> **One-line instruction to the next agent:** Preserve the existing tested backend and PySide6 UI; investigate actual MPFB/Blender runtime evidence; deliver one real rigged humanoid that can be generated, saved, reopened and inspected before connecting morphs, retargeting or engine exports. Use narrow reviewed PRs and never claim a result that was not executed.

## 0. Executive summary and immediate decisions

1. **Do not re-plan the product.** The user's 39 design decisions are already captured in `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`. `AGENTS.md` contains mandatory operating rules. Those two files are authoritative.
2. **The application already exists in alpha form.** Its pure-Python core supports versioned character metadata, body-part compatibility declarations, draft morphs, undo/redo, atomic saves, immutable `.blend` staging, Blender job IPC, asset provenance, conservative license checks, animation metadata intake, bone-name mapping candidates, GLB structural inspection, spritesheet packing, and opt-in local AI integrations.
3. **The desktop UI is real, but limited.** PySide6 can create/open/save projects, edit metadata, inspect/index user-selected animation sources, show export blockers, probe local AI APIs, pack existing PNGs and open a read-only, interactive **static** local GLB triangle preview. It does not generate or deform an MPFB human in the app, animate that preview, or prove game-engine exports.
4. **A portable Windows alpha is available through GitHub Actions artifacts.** The PyInstaller build was exercised through real frozen executable startup and temporary character-project save/reopen. Artifacts are **ephemeral**, unsigned and not a production release.
5. **The critical path remains P0 Blender/MPFB integration.** Source code now calls MPFB's documented `HumanService.create_human()` and `add_builtin_rig()`; the smoke requires a real mesh, rig and separate-process `.blend` reopen. Contract tests pass, but **the user's actual Windows Blender 5.3 + MPFB compatibility is not verified** in the evidence available during this handoff. Whether the experimental Linux cloud smoke has passed also must be checked from its **own** GitHub Actions workflow, not inferred from green core tests.
6. **All previous development PRs through #21 are merged; #22 is closed without merging.** At this audit there are **no open PRs**, and issues #2–#11 remain open. Do not confuse merged PRs with completed acceptance criteria.
7. **Do not bundle purchased Fab animations, MPFB binaries, user models or AI weights.** License and data provenance are first-class requirements. Existing Fab animations were described as held in the user's Fab/Epic library but **not yet downloaded** when requirements were gathered; recheck that factual state before requesting any assets.

### Source-of-truth priority

1. Current code and tests on the verified `main` commit.
2. `AGENTS.md` and `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` for requirements/constraints.
3. `Development_Guardrails/config/gates.json` plus verification scripts for acceptance evidence.
4. Relevant integration docs and issue acceptance criteria.
5. This snapshot handoff. **If the repository changes after the snapshot, inspect and reconcile; never overwrite newer work.**

**Documentation drift warning:** `docs/STATUS.md` and `IMPLEMENTATION_STATUS.md` contain historical statements such as “Character creator UI not implemented” or “PySide6 UI not started,” even though the desktop and GLB preview are now merged. Update those status files from verified reality in a small PR; do not treat their older tables as current facts.

## 1. Locked product scope

**Product goal:** A standalone **Windows** app allowing non-artists to create original reusable characters with a single editable authoritative 3D master, then generate 3D, 2.5D, layered 2D and pixel-art outputs. The app must work as an accessible creative tool **and** as an advanced editing workstation; do not recreate a full Blender replacement.

**First character family:** Parametric **MPFB humanoid** under the user's installed Blender 5.3. Other families (quadruped, dragon, robot, unusual anatomy) are later adapters with **distinct skeletons/topology**; never force them into one humanoid rig.

**Anatomical requirements:** Modular heads, eyes, ears, noses, mouths, torsos, arms, hands, individual fingers, legs, feet, individual toes, and optional wings, capes, tails and horns. Semantic part/socket compatibility is already modeled, but physical mesh splitting, attachment fitting, skin weights and seam-free deformation are **not** complete. A separate mesh for every bone is neither always necessary nor always correct.

**Model control:** Presets, body/face morph sliders, eventually direct manipulation and opt-in prompt edits. Current height/weight/muscle sliders change **saved draft metadata**, not actual MPFB vertices. The UI must say so until verified MPFB target mapping exists.

**Animation target:** Manual edits, imported animation packs, skeleton retargeting, facial shape keys/lip sync, and an eventual **100+ verified usable clips**. Fab clips may use mixed UE4/UE5/Mixamo rigs; source files can have engine-only or AI restrictions. Do not count indexed filenames or name-mapping candidates as playable, retargeted animations. Animation priority follows the working humanoid pipeline.

**Exports:** First milestone must validate real imported, animated characters in **Godot, Unreal and Unity**. Later RPG Maker MZ and Lumina are adapters. 2D includes RGBA sprite sheets, multiple resolutions/camera angles, separated layers and SNES-like/high-detail pixel-art styles. A static GLB preview or successful file write does not establish engine support.

**AI:** Local ComfyUI and Stable Diffusion WebUI initially; explicit user-selected cloud support later. No data upload, AI inference, full-drive scan or checkpoint download without user intent/permission. No assumption that a generated reference image equals production-ready 3D topology/rigging. First GPU target: RTX 3060 12 GB VRAM; avoid overlapping heavy GPU jobs.

**Distribution:** Preserve private and potential commercial use, but no project-wide distribution license has been chosen. Third-party program code, Qt/PySide6 and each Fab asset must be reviewed independently before a public installer or redistributed sample project.

## 2. Current GitHub state — verified at handoff

**Repository URL:** https://github.com/DocDamage/newestcharactercreator  
**Main SHA at audit:** `e487e8ed6111bbd5996cf3a772a59e9f7cdcc009`

### Important merged PRs

| PR | Implementation | State at audit | Evidence boundary |
|---|---|---|---|
| [#1](https://github.com/DocDamage/newestcharactercreator/pull/1) | Blueprint, Stage 0 scripts, agent rules, safety/quality gates | Merged | Planning and pure-Python tests only |
| [#12](https://github.com/DocDamage/newestcharactercreator/pull/12) | Core model, persistence, worker protocol, asset ledger, PNG atlas, AI probes, GLB inspection | Merged | Back-end tests, not verified character creation |
| [#13](https://github.com/DocDamage/newestcharactercreator/pull/13) | BVH/glTF animation metadata intake and private SQLite catalog | Merged | Not actual retargeting |
| [#14](https://github.com/DocDamage/newestcharactercreator/pull/14) | Opt-in localhost ComfyUI text-to-image and PNG retrieval | Merged | Mock-server tests; live generation needs user environment |
| [#15](https://github.com/DocDamage/newestcharactercreator/pull/15) | MPFB HumanService-based rigged-human smoke and worker adapter | Merged | Service mocks do not establish Windows/Blender compatibility |
| [#16](https://github.com/DocDamage/newestcharactercreator/pull/16) | Mixamo / UE4 / UE5 bone-name mapping candidates | Merged | Name matching only, no performed retarget |
| [#17](https://github.com/DocDamage/newestcharactercreator/pull/17) | PySide6 project and asset workstation | Merged | Real Qt offscreen checks passed, not GPU/UI acceptance |
| [#18](https://github.com/DocDamage/newestcharactercreator/pull/18) | Cloud Blender/MPFB smoke workflow trigger | Merged | Test success must be read from the specific cloud run |
| [#19](https://github.com/DocDamage/newestcharactercreator/pull/19) | Portable Windows PyInstaller alpha + self-test | Merged | Functional frozen-app smoke, not release-ready |
| [#20](https://github.com/DocDamage/newestcharactercreator/pull/20) | More cloud MPFB diagnostics and production-worker validation script | Merged | Runtime outcome **not confirmed in this handoff** |
| [#21](https://github.com/DocDamage/newestcharactercreator/pull/21) | Read-only static GLB 3D viewer with orbit/pan/zoom and safety bounds | Merged | Static preview, not skinning, morph animation or real engine import |
| [#22](https://github.com/DocDamage/newestcharactercreator/pull/22) | Duplicate preview PR from interrupted session | **Closed without merge** | Unique additions had been consolidated into #21 |

The conflict in #21 was resolved by merging the newer `main` into its branch, preserving the Windows packaging and MPFB workflow changes while retaining the preview. GitHub reported the corrected #21 as mergeable; four GitHub workflows passed on the premerge commit before it was merged.

### Specific CI evidence previously observed

The final #21 premerge commit was `e827ce606305ec50985a1646f587682dc9d09eff`. Its GitHub Actions runs completed successfully:

| Workflow | Run | Verified result |
|---|---|---|
| Preflight Unit Tests | [43077075448](https://github.com/DocDamage/newestcharactercreator/actions/runs/43077075448) | Success |
| Character Core and Worker Tests | [43077075430](https://github.com/DocDamage/newestcharactercreator/actions/runs/43077075430) | Success |
| Desktop Qt Smoke Tests | [43077075336](https://github.com/DocDamage/newestcharactercreator/actions/runs/43077075336) | Success, Windows/Linux Python 3.12/3.13 |
| Windows desktop alpha build | [43077075577](https://github.com/DocDamage/newestcharactercreator/actions/runs/43077075577) | Success, frozen EXE tested |

These results apply to the identified commit, not automatically to all future changes. Earlier Qt smoke tests **falsely appeared green while skipped on Linux** due to missing `libEGL.so.1`; the CI was corrected to fail on missing imports and to install the needed Linux libraries. Do **not** weaken that no-skip requirement.

**Alpha artifact:** On the successful #21 Windows workflow, `UCC-Desktop-Alpha-Windows-x64` was observed at approximately 59.1 MB, with creation time 2026-11-11 18:23 UTC and stated expiry **2026-11-18 18:23 UTC**. GitHub artifact access/retention can change; use the latest successful Windows alpha workflow for any future download. Verify SHA-256 manifest and preserve the entire extracted folder.

### Open GitHub issues

All of these remain open, including tasks with partial implementations:

- [#2 UCC-P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2) — Actual Windows Blender 5.3/MPFB generate + rig + save/reopen smoke (**critical blocker**).
- [#3 UCC-P0-002](https://github.com/DocDamage/newestcharactercreator/issues/3) — Reproducible dependency / license inventory.
- [#4 UCC-P0-003](https://github.com/DocDamage/newestcharactercreator/issues/4) — Blender worker protocol and actual integrated error/rollback proof.
- [#5 UCC-P0-004](https://github.com/DocDamage/newestcharactercreator/issues/5) — Desktop and 3D preview technology spike; static CPU preview exists, final animated viewport undecided.
- [#6 UCC-P1-001](https://github.com/DocDamage/newestcharactercreator/issues/6) — Character project graph/parts and physical validation; metadata is implemented.
- [#7 UCC-P1-002](https://github.com/DocDamage/newestcharactercreator/issues/7) — Fully editable, physically rigged humanoid vertical slice.
- [#8 UCC-P1-003](https://github.com/DocDamage/newestcharactercreator/issues/8) — Actual Godot + Unity + Unreal imports/playback.
- [#9 UCC-P2-001](https://github.com/DocDamage/newestcharactercreator/issues/9) — Licensed Fab animation intake + genuine mixed-rig retarget + 100 usable clips.
- [#10 UCC-P2-002](https://github.com/DocDamage/newestcharactercreator/issues/10) — Blender-originated 2D/2.5D/pixel-art renders and layered exports.
- [#11 UCC-P3-001](https://github.com/DocDamage/newestcharactercreator/issues/11) — Real authorized local AI workflows, model discovery and mesh-part evaluation.

## 3. Architecture and code map

### Core philosophy

The **canonical source of geometry and rig state** is a versioned `.blend` file, not an editable GLB or generated PNG. The sidecar `project.ucc.json` owns cross-tool metadata. Pure-Python domain code must stay independent from Qt, Blender's `bpy`, optional AI runtimes and game engines. Blender runs in a separate process with a strict JSON request/response protocol, cancellation/timeout, and per-job staging.

```text
User-selected local files / assets
              |
  PySide6 desktop (src/ucc/desktop)
     |         |                 |
  Metadata   Animation+AI      Static GLB / sprite tools
     |         |                 |
      --- Pure Python UCC core + provenance ---
                   |
          JSON worker/job protocol
                   |
     Separate Blender/MPFB Python process
                   |
      STAGED .blend -> separate reopen/validation
                   |
         Immutable revision / project pointer
                   |
  Future: export/import validation in Godot, Unity, Unreal
```

### Important paths — inspect before modifying

| File / directory | Responsibility and present boundary |
|---|---|
| `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` | Complete 39-decision spec and staged implementation plan. |
| `AGENTS.md` | Mandatory rules: no fake successes, unapproved placeholder assets, silent installs, broad rewrites or private uploads. |
| `pyproject.toml` | Python >=3.12, `ucc-character-core` alpha, optional `sprites` = Pillow, `desktop` = PySide6, `ucc` and `ucc-desktop` entrypoints. |
| `src/ucc/core/models.py` | `CharacterProject`, `PartAsset`, `PartInstance`; strict v1 schema and state invariants. |
| `src/ucc/core/anatomy.py` | Humanoid semantic slots/socket catalog. Other body families not implemented. |
| `src/ucc/core/commands.py` | Session-scoped undo/redo, draft morph edits, part proposals. Does **not** alter the 3D master. |
| `src/ucc/core/storage.py` | Atomic JSON save, optimistic revision/conflict checks, backup history and path confinement. |
| `src/ucc/core/master_versions.py` | Content-addressed immutable `.blend` staging; all unverified until a real Blender validation. |
| `src/ucc/jobs/protocol.py`, `runner.py` | Typed job requests/results, subprocess boundaries, timeout/cancel/logs. |
| `blender_bridge/mpfb_service.py` | MPFB `HumanService` discovery and creation/rig adapter; actual version/runtime compatibility must be proven. |
| `blender_bridge/entrypoint.py` | Blender-only `bpy` entrypoint for environment inspection, human creation and model inspection. |
| `Stage0_Starter/tools/` | Local environment audit and real generate/save/reopen smoke launcher. |
| `Stage0_Starter/blender_bridge/` | Blender-side Stage 0 generator and independent reopen checker. |
| `Development_Guardrails/` | Acceptance gates, evidence collector, license policy validator and Windows Stage 0 runner. |
| `src/ucc/library/provenance.py` | SQLite source hashes and per-asset fail-closed usage, AI and redistribution rights. |
| `src/ucc/animations/metadata.py`, `catalog.py` | BVH/glTF/GLB metadata extraction and private animation catalog; `.fbx`/`.uasset` conversion still required. |
| `src/ucc/animations/candidate_mapping.py` | Mixamo/UE4/UE5 name-based mapping suggestions; **no retargeted transforms**. |
| `src/ucc/ai/probe.py`, `generate.py` | Read-only local AI probes; opt-in ComfyUI text-to-image with local PNG retrieval. |
| `src/ucc/export/inspect_glb.py` | Offline GLB structural inspection, not target-engine import certification. |
| `src/ucc/preview/glb_mesh.py` | Bounded local GLB triangle decoding, scene transforms and sample mesh extraction. |
| `src/ucc/desktop/mesh_viewer.py` | Qt CPU-rendered static 3D preview; orbit/pan/zoom/reset; no animation, skinning or editing. |
| `src/ucc/desktop/controller.py` | Pure-Python desktop project lifecycle and revision-safe editing. |
| `src/ucc/desktop/window.py`, `panes.py`, `background.py` | PySide6 window, character/animation/tools panels, background worker for file operations. |
| `src/ucc/desktop/__main__.py` | Qt launcher and Windows frozen executable `--self-test` path. |
| `src/ucc/sprites/plan.py`, `atlas.py` | Direction/frame plan plus **real** PNG atlas packing from existing input images; does not render new frames from 3D. |
| `src/ucc/cli.py` | Main command-line operations for metadata, diagnostics and sprite tools. |
| `docs/schemas/` | Versioned JSON schemas. Reject unrecognized/future schema values instead of destructive migration. |
| `docs/integration/`, `docs/packaging/` | Integration contracts, limitations, Windows alpha instructions. |
| `ci/run_mpfb_cloud_smoke.sh` | Cloud script for pinned Blender/MPFB and production-worker integration attempt; read logs before declaring success. |
| `tests/` | Core, worker, asset policy, desktop, GLB, ComfyUI and other regression tests. |

### Format and reliability invariants

- `project.ucc.json` describes the character; no claim that changing a morph field deforms the `.blend`.
- `geometry_state` values include `not_generated`, `generated_unverified`, `validated`; don't mark `validated` without actual Blender evidence.
- Part status remains `proposed` until physical attachment/deformation validation. Name/socket matching alone is insufficient.
- The `.blend` staging store preserves previous versions by SHA-256. A staged copy is **not** automatically a production master.
- Newer schema versions are rejected rather than silently downgraded.
- Local file paths are validated against symlink/traversal abuse; output is staged atomically where supported.
- The CLI, catalog, UI and preview never confer license permissions merely because a file is present.

## 4. What is implemented and what has **not** been verified

| Capability | Actual deliverable | Test class / verified boundary | Missing to declare complete |
|---|---|---|---|
| Character metadata/project | Versioned model, strict validation, save/reopen, revisions, backups, undo/redo | Pure Python tests and frozen-app project roundtrip | Real MPFB mesh/morph roundtrip |
| Anatomical slots / parts | Semantic socket catalog; compatibility/rig declarations, proposals | Unit tests | Seamless actual meshes, weighted attachments and visual deformation |
| Blender worker | Allowlisted JSON contract, subprocess timeout/cancel, `HumanService` bridge | Mock/contract and worker tests | Real Windows Blender 5.3 + MPFB test with rig/reopen |
| Saved Blender masters | Immutable content-addressed staging | File/rollback/hash tests | Genuine Blender inspection before marking geometry validated |
| Desktop app | PySide6 GUI, metadata edits, animation intake and tools, background jobs | Real Qt offscreen Windows/Linux CI; frozen EXE startup | Production visual layout, DPI/drag UX, real authoring viewport |
| Static GLB 3D preview | Embedded binary GLB mesh samples, orbit/pan/zoom/reset | GLB parser + Qt offscreen tests | Animated skinning, morphs, correct materials, selectable bones |
| Windows portable alpha | Frozen `.exe` directory, private QA ZIP, checksum, built-in self-test | Windows runner ran and verified executable | Installer, signing, licensing, user acceptance and Blender bundling policy |
| Animation intake | Read-only BVH/glTF/GLB metadata plus private source hashes; FBX/uasset as conversion-required | Parser/catalog and policy tests | Legally permitted source conversion, actual clips and retarget quality |
| Bone candidate mapping | Exact alias candidates for Mixamo/UE4/UE5; no automatic correction of rest poses | Name/coverage tests | Real source+target skeleton transforms, baked keyframes and visual motion |
| Sprite sheet generation | Existing PNG frames packed as RGBA atlases with metadata | Real image test outputs | Rendering those frames from rigged Blender character and layered Aseprite delivery |
| Local AI | ComfyUI/WebUI probes and opt-in ComfyUI text-to-image workflow | Local mock HTTP tests | Real local checkpoint inference, art review and topology-safe 3D part creation |
| Game-engine exports | GLB structural inspector and export requirements | Offline structure tests | Real Godot, Unity and Unreal imports/animation playback |
| Beyond humanoids | Architecture anticipates other families | Contracts/planning | Actual family adapters, models and separate rigs |

**No currently observed evidence** validates a 100+ retargeted-clip library, integrated MPFB morph control, game-engine import/playback or the complete universal creator. Do not use optimistic words like “done” for those milestones.

## 5. How to run the working code — no IDE necessary

These are **examples**, not statements that the user's local machine was accessed or software already installed. Start in a checked-out repository root. Use an appropriate Python 3.12+ installation.

### Desktop (source installation)

```powershell
py -3 -m pip install -e ".[desktop,sprites]"
py -3 -m ucc.desktop
```

Alternatively, after installation run `ucc-desktop`. Qt and Pillow are optional dependencies installed only when the user explicitly executes this command. Blender, MPFB, game engines, paid assets, model weights and Aseprite are **not installed by it**.

### Portable Windows alpha (no Python required)

Open **GitHub → Actions → Windows desktop alpha build (internal testing)**, choose the latest successful run, and download artifact `UCC-Desktop-Alpha-Windows-x64` while it is retained. Extract GitHub's artifact wrapper and the inner application ZIP if needed; keep the complete `UCC-Desktop-Alpha` directory intact. Launch `UCC-Desktop-Alpha.exe` and inspect `SHA256SUMS.txt` and `frozen-health.json`. It is an **unsigned internal QA build**, not a validated production installer.

### Core metadata CLI

```powershell
$env:PYTHONPATH = 'src'
py -3 -m ucc new "$env:USERPROFILE\Documents\UCC\FirstHuman" --name "First Human"
py -3 -m ucc info "$env:USERPROFILE\Documents\UCC\FirstHuman"
py -3 -m ucc slots
py -3 -m ucc plan-sprites --directions 8 --width 128 --height 128 --clip idle:8
```

### Optional local inspection and AI

```powershell
py -3 -m ucc inspect-animation 'D:\AnimationSource\Walk.bvh'
py -3 -m ucc inspect-glb 'D:\CharacterExports\Character.glb'
py -3 -m ucc probe-ai
```

For an explicitly authorized, **local-only** ComfyUI concept image (not a mesh), follow `docs/integration/comfyui-generation.md`. Actual checkpoint names and licensing must be user-confirmed. For sprites, run `pack-sprites` only with existing correctly named/validated RGBA PNG frames and a chosen output directory. Preview a selected GLB in the desktop via **View → Preview local GLB model...** (Ctrl+Shift+M). It is a static rest-pose inspection tool.

### Real Windows Blender/MPFB P0 — top priority

After installing and enabling the **official MPFB extension** in the user-selected Blender executable, from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'
```

**Adjust to the actual installed path.** This is a verification command, not an automatic download. It creates private output under ignored `evidence/`, audits the environment, attempts a **real** HumanService humanoid mesh and built-in rig, saves a `.blend`, then uses a fresh Blender subprocess to reopen and inspect it. It collects reports and applies the P0 gate. Check `evidence/mpfb_smoke/summary.json`, `mpfb_create_result.json`, `reopen_result.json` and the `.blend` itself before declaring success. Do **not** upload paths, personal asset inventories or proprietary content into public GitHub issues.

### GitHub automated test commands

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s Stage0_Starter/tests -v
py -3 -m unittest discover -s Development_Guardrails/tests -v
py -3 -m compileall -q src blender_bridge
```

For the real offscreen GUI suite, install PySide6 and run with the proper `QT_QPA_PLATFORM=offscreen` and `UCC_REQUIRE_QT=1`. CI already enforces this on Windows/Linux Python 3.12 and 3.13. A missing Qt import must **fail**, never silently skip and report green.

## 6. CI and acceptance-gate playbook

Current workflows:

- `.github/workflows/preflight.yml` — read-only environment/guardrail unit tests.
- `.github/workflows/core-tests.yml` — core, worker, asset and schema tests, Windows/Linux × Python 3.12/3.13; includes optional Pillow for real sprite tests.
- `.github/workflows/desktop-tests.yml` — real PySide6 offscreen widget tests, Windows/Linux × Python 3.12/3.13; must not skip Qt imports; includes GLB preview widget and decoder tests.
- `.github/workflows/windows-alpha-package.yml` — PyInstaller portable Windows alpha, source/frozen self-tests, SHA-256 and 7-day artifact.
- `.github/workflows/mpfb-cloud-smoke.yml` — experimental pinned official Blender 5.3 + MPFB **Linux** integration; manual dispatch and relevant file triggers. `ci/run_mpfb_cloud_smoke.sh` adds production-worker create/reinspect diagnostics. **Never substitute green unit tests for this integration run.**

### Quality gates (`Development_Guardrails/config/gates.json`)

| Gate | What must be observed | Current conservative assessment |
|---|---|---|
| `P0_SPIKE` | Real Windows/target Blender MPFB mesh+rig, saved `.blend`, reopened in separate process and evidence hashes | **BLOCKED / NOT VERIFIED** |
| `P0_COMPLETE` | Worker protocol and recovery, dependency inventory, licensing boundary review | **PARTIAL** |
| `M1_CHARACTER` | Actual parametric and facial mesh changes, reversible compatible parts, rigged deforming character and reopen | **BLOCKED** |
| `M1_EXPORTS` | Real import and animation in Godot/Unity/Unreal; sample RGBA render; robust crash recovery | **BLOCKED** |
| `M2_ANIMATIONS` | Licensed mixed-rig retarget proof and 100 distinct previewed/usable clips | **BLOCKED** |

Use `py -3 Development_Guardrails/tools/verify_gate.py --list` to enumerate required test IDs. Passed evidence includes exact artifact paths/hashes, timestamps, commands, tool versions and required human sign-off. A Python fixture with a `BLENDER` signature is a **unit-test fixture**, not a verified `.blend`. No green unit-test count may upgrade an integration gate.

### Cloud smoke check that must happen first

Open GitHub's **Actions → MPFB 2.0.18 / Blender 5.3 Linux smoke (experimental)** and inspect the latest relevant run and detailed step logs. Specifically: version/download/checksum, extension installation, `HumanService` discovery, real created vertex count, actual armature/bone count, first save and fresh subprocess reopen, and production-worker roundtrip. If the workflow fails at download/extension install, document that as **environment setup failure**, not proof the MPFB API fails. If it reaches HumanService and fails, preserve the precise API/traceback without weakening geometry/rig requirements. A Linux pass still does **not** establish user Windows compatibility.

This snapshot cannot confirm a Linux cloud smoke **PASS** from the GitHub run data retrieved; mark status **UNKNOWN / CHECK ACTIONS**, rather than inventing a green result. The next agent can investigate the run directly and issue a narrowly scoped fix if necessary.

## 7. Ordered next-development work (no more broad questionnaire)

### Priority A — true blocker: real MPFB/Blender evidence (`#2`)

**A1. Cloud integration diagnosis (can work in GitHub without touching the user's PC).** Read the actual pinned Linux smoke run logs and JSON artifacts. Verify official Blender download/checksum, MPFB extension install, module import, `HumanService.create_human()`, `add_builtin_rig()`, `.blend` save/reopen, plus production `BlenderJobRunner` create/inspect. Record the exact failure stage and version. Fix a reproducible bug with a small PR and rerun. **Exit:** Real Linux integration evidence if possible; explicitly report remaining Windows gap.

**A2. Windows compatibility procedure.** From actual Windows Blender 5.3 and enabled MPFB, run `Development_Guardrails/scripts/run_stage0.ps1`. Capture private JSON outputs/mesh bone counts and visual inspection. Do not assume Blender is in the example directory. If user-PC access is unavailable, provide a minimal verified command and say **UNRUN**.

**A3. Add mesh/rig quality validation after basic save/reopen.** On real Blender output check skin modifier binding to armature, joint influence/weight normalization, nonzero bone transforms, basis pose, symmetry and deliberately animated deformation. Save and reopen the tested artifact. The initial 5-bone/100-vertex smoke is not a substitute for deformation acceptance.

### Priority B — connect project state to **real editable geometry** (`#4`, `#6`, `#7`)

**B1. MPFB morph capability mapping.** Probe the actual enabled MPFB version's allowed targets and ranges. Introduce a versioned mapping between UCC draft `height/weight/muscle` (and later face properties) and verified MPFB service targets. Do not guess parameter names. On slider change use an isolated Blender work copy; never mutate the saved master from the UI thread. Verify vertex displacement or target state and reopen persistence.

**B2. Character creation UI transaction.** Add a real “Generate humanoid” action **only after** worker success is possible. Background Blender job → staged `generated_human.blend` → fresh-process validation → immutable master staging → revision-checked metadata pointer update → regenerate preview GLB. Explicit progress/errors/cancel/rollback. Do not add controls whose only action is fake geometry or a status string.

**B3. Part interchange vertical slice.** Begin with one permitted **rigid accessory or clearly compatible part**. Confirm socket attachment, source license, transforms and save/reopen; then test a *skinned* compatible part with weight continuity and animation deformation. Never naïvely slice MPFB mesh into fingers/toes and assume clean seams.

**B4. Animated viewport.** The existing Qt `QPainter` GLB viewer is static/CPU-bound. Prototype an offline hardware-accelerated renderer or local packaged Three.js/Qt WebEngine against a **real validated** skinned GLB. Verify animations, bones, morph targets, normals, texture fallback, picking, frame stepping, and Windows DPI/GPU behavior. Write a measured ADR before replacing the static fallback.

### Priority C — certify target exports (`#8`)

**C1. Godot:** Export a genuinely rigged/animated permitted GLB and import it into a version-recorded Godot project. Validate scale, orientation, skeleton, at least one animation and optional morphs in editor and runtime.

**C2. Unity:** Test a verified Unity import path/rig configuration, material compatibility, avatar or humanoid retargeting, and animation playback. Do not assume all GLB or FBX variants map identically.

**C3. Unreal:** Test export and import into a version-recorded Unreal project, skeleton/bind pose, animation sequence and root motion; use proper FBX/other validated route. Do not assume Unreal `.uasset` files are generic portable animation files.

**C4. Reusable evidence matrix:** Exact files/hashes, settings, engine version, screenshots/video, failures and reviewer acceptance; do not label source Blender export success as an engine-import success.

### Priority D — expand features after core vertical slice (`#9`, `#10`, `#11`)

**D1.** Acquire user-approved Fab pack downloads and verify per-asset licenses; classify `.uasset`, FBX, BVH and glTF; build true source-to-target rest-pose retargeting, keyframe baking and visual previews. Count **100 usable** clips only when individually validated; name mapping candidates do not count.

**D2.** Render rigged character frames from Blender for 4/8/16 directions and user-defined angles; feed existing PNG atlas packer; test alpha, pivots, frame duration, layer IDs and Godot/Unity imports. Add optional Aseprite cleanup adapter with licensing care.

**D3.** Run explicitly approved ComfyUI local text-to-image against a real checkpoint. Keep model/license/provenance records; review generated images. AI-assisted body parts require subsequent validated mesh topology, fitting, UV, rigging and deform quality.

### Priority E — packaging, maintenance and licensing

- Replace stale implementation/readiness tables in `docs/STATUS.md` and `IMPLEMENTATION_STATUS.md` with dated, evidence-linked facts; keep old history out of the current column.
- Extend Windows frozen-app self-test to open and **render a real user-supplied test GLB** in a test environment without shipping a third-party model (generate a tiny test-only GLB in CI when needed); guard hidden-import and resource packaging failures.
- Add deterministic fixture and integration-test directories, documented process/VRAM timeouts and robust cancellation of Blender subprocess trees.
- Review PySide6/Qt, MPFB, Blender, Pillow, Aseprite and any other runtime obligations before signing or distributing an installer; add notices and a chosen project license only with explicit owner decision.
- Use modular task-scoped PRs and preserve a functional `main`. Keep files generally around 300–500 LOC by responsibility, not artificial splitting.

## 8. Operational risk register

| Risk | Why it matters | Mitigation / verification |
|---|---|---|
| MPFB API behavior differs under background mode or Blender 5.3 | Core generation may never reach usable geometry | Real HumanService + rig + separate reopen; versioned ADR and fallback supported by extension docs |
| Cloud Linux smoke does not represent local Windows | OS/extensions/drivers differ | Both cloud and user Windows integration evidence are distinct checks |
| Static GLB preview mistaken for final editor | Misleading demo, no animation/skin | Keep static labels and explicit missing features until verified skinned viewport |
| Invalid or incompatible mesh part swap | Seams, bone weights, clipping, destructive edits | Rig/socket/pose/vertex checks and staged copy before promotion |
| Paid Fab or NoAI asset distributed or used in prohibited AI workflow | License/privacy risk | Per-asset provenance; fail closed; source files never committed |
| Malicious/huge imported GLB | Crash/memory exhaustion | Existing 128 MiB / per-accessor and aggregate-triangle bounds; no external URI loads; maintain regressions |
| Two editors or agents save same project | Lost user changes | Monotonic revisions, optimistic conflicts, backups and atomic writes |
| Blender/AI crash mid-transaction | Irrecoverable character data | Immutable `.blend` revisions; staged work, rollback and evidence logs |
| RTX 3060 12 GB shared by Blender + AI | Out-of-memory and UI freeze | One controlled heavy GPU job at a time; preset budgets, cancellation, CPU fallback |
| False-positive CI or mocks described as integration proof | Broken milestones declared complete | No skipped critical tests; real tool executions and human review for gates |
| Outdated docs/head assumptions | Agent redoes work or overwrites fixes | Always check `main`, open PRs, CI and issue bodies before changing files |
| Unsigned portable Windows alpha treated as release | Trust/compliance issues | Internal QA only; hash and self-test; installer/signing/license review later |

## 9. PR / agent execution contract

For every task:

1. Fetch current `main` SHA, inspect open PRs and issue dependencies, and read `AGENTS.md` plus relevant modules before editing.
2. Use **one narrow feature branch** and an issue ID in the PR. Never force-push or overwrite another collaborator's work without a reviewed lease/merge plan.
3. Write measurable acceptance criteria with **implemented vs tested vs untested** explicitly separated.
4. Implement production behavior only where capability is supported. Use small isolated synthetic fixtures for unit tests, never ship them as user character assets or count them as MPFB/game-engine proof.
5. Test syntax, targeted pure-Python tests, entire relevant unit suite, Qt offscreen on Windows/Linux if UI changed, Windows frozen app if packaging/runtime changed, and actual Blender/engine tests where relevant.
6. Inspect the exact CI job steps/logs for skips, missing libraries, `continue-on-error` or superficially green tests. Green workflow summaries alone are insufficient for integration claims.
7. Confirm no third-party source files, credentials, user path inventories, model weights or personally identifying logs are added to the Git diff.
8. Before merge, check `mergeable=true` and branch currency; resolve main-vs-branch conflicts while **preserving both sides' changes**. The earlier PR #21 needed this after #19/#20 merged.
9. Report: **Task ID; Changed files; New behavior; Tests actually run; Tests not run; License/dependency changes; Evidence; Next task.** Keep the `main` branch stable until reviewed.
10. No further broad questionnaire. Ask the owner only for a specific unavailable local asset or an action required for an otherwise blocked integration (for example the Windows MPFB smoke result).

## 10. Paste-ready next-agent instruction

> You are continuing the Universal AI Character Creator project at https://github.com/DocDamage/newestcharactercreator. Read `AGENTS.md`, `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`, this handoff, and inspect CURRENT `main` plus open PRs/issues. Do not restart the project, change engine stack, invent placeholder assets, weaken licensing gates or report success from mocks. Current code has a tested Python character-metadata backend, versioned `.blend` staging, PySide6 desktop workstation, static CPU GLB preview, private animation catalog, name-only bone mapping, PNG atlas packer, local AI adapters, a portable Windows alpha and a Blender/MPFB HumanService bridge. No verified actual Windows humanoid creation, morph binding, animated 3D editor or Godot/Unity/Unreal export exists yet. Your first task is to inspect the **actual** MPFB Linux cloud smoke workflow and its JSON/step logs, identify the earliest real failure, fix it in a small focused PR if reproducible, and preserve genuine evidence. If it passes Linux, retain Windows as an independent outstanding gate. Then implement a real validated humanoid save/reopen and worker-to-desktop project transaction; next bind real MPFB morph controls; then prove animation and engine import. Run appropriate cross-platform CI, preserve private Fab/AI files, link evidence and leave an actionable next step.

---

### Handoff integrity / caveats

This document is a **dated repository snapshot**, not proof of any currently running user-PC process. Repo HEAD and merged PR status were fetched from the connected GitHub repository during preparation. Exact pinned premerge workflow run IDs and Windows artifact metadata were observed through GitHub's CI tool. The MPFB cloud workflow source was read, but this handoff has **not verified a successful Blender 5.3 + MPFB cloud runtime or the user's Windows runtime**. Preserve those as unknown or blocked until inspected. Software versions, licenses and external download links may change; validate them when working on that integration. A green PySide6 offscreen test or signed-off metadata save does not imply a character creator is fully working.
