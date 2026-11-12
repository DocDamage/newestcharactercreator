# Universal AI Character Creator

**Project stage: functional PySide6 desktop alpha, versioned core and Linux-verified MPFB character generation, saved-body refit, static GLB preview and rig-pose deformation diagnostic.** This is not a complete character animation editor or certified Godot/Unity/Unreal export pipeline.

## Current character workflow and verified evidence (November 11, 2026)

[PRs #25–#29](https://github.com/DocDamage/newestcharactercreator/pulls?q=is%3Apr+is%3Amerged) are merged. The desktop can create a real MPFB humanoid from **saved** normalized Height/Muscle/Weight settings, edit the saved master on a private Blender copy using MPFB macro refit while preserving its rig weights, and display a private **evaluated-geometry-baked** static GLB preview. Original SHA-addressed masters and metadata backups are preserved.

**Merged [PR #29](https://github.com/DocDamage/newestcharactercreator/pull/29)** added **Test saved rig deformation in Blender...**. On its tested Linux branch, a real 20° rotation of the weighted head bone moved **4,451 evaluated mesh vertices**. Two separate Blender processes agreed on the geometry/rig fingerprints, the original pose was restored, and neither master nor project file changed. This also fixes the merged PR #28's static GLB preview regression by baking **evaluated** MPFB shape-key positions before exporting the temporary diagnostic GLB. [Real Blender integration run #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) passed; core, Qt, preflight and frozen Windows startup CI also passed on that commit.

**Explicit limits:** The test demonstrates one reproducible static skinned-bone response, **not** live animation clips, quality of shoulder/face deformation, IK, retargeting, real-world height calibration or successful engine reimport. The owner's actual Windows Blender 5.3/MPFB environment remains untested; MPFB installed from the live official extension registry is not version-hash pinned. Existing per-PR milestone descriptions below are retained as **historical development notes** and may describe earlier limitations now improved by subsequent PRs. [Current status](docs/STATUS.md) · [Rig-pose test guide](docs/integration/rig-pose-deformation.md).

## Frame-by-frame Blender animation timeline — proposed PR #30

[PR #30](https://github.com/DocDamage/newestcharactercreator/pull/30) adds an opt-in **Validate one-second Blender keyframe timeline...** action. On a private copy of an existing saved MPFB humanoid, Blender creates a temporary, original three-keyframe Action and evaluates actual bound mesh geometry at five frames (1, 7, 13, 19, 25). Two independent Blender processes must agree on per-frame hashes, interpolated mesh motion, and a restored final pose. The authoritative project and .blend remain unchanged. [Timeline procedure and limitations](docs/integration/keyframed-timeline-diagnostic.md).

**This is not your animation library playback or a retargeter.** It establishes that real Blender keyframe interpolation can deform the saved MPFB character over time. User-owned Fab/BVH/FBX clips, rendered animation in UCC and Godot/Unity/Unreal imports still need separate permission-aware integration. The [real Blender/MPFB timeline integration run #43105088396](https://github.com/DocDamage/newestcharactercreator/actions/runs/43105088396) passed: real keyframes at frames 1/13/25 generated **4,451 moved vertices** at frames 7, 13 and 19; baseline was restored at 25, and two Blender processes agreed. The feature remains on the PR branch until merged.

## Local user-selected BVH motion — proposed PR #31

[PR #31](https://github.com/DocDamage/newestcharactercreator/pull/31) introduces a carefully bounded **Test selected BVH motion on saved MPFB rig...** action. In the existing Animation library tab, choose exactly one local BVH file, enter its real provider/license/source URI and explicitly affirm that its reviewed rights permit **local Blender use outside Unreal**. This is a user attestation, not an automated license grant or engine export approval.

The worker reads actual source BVH rotation frames and tests **one exactly named, genuinely weighted MPFB bone** on private SHA-checked Blender master copies. It creates temporary source-driven keyframes, measures actual evaluated skinned geometry at five frames in two independent Blender processes, and **never overwrites** the BVH, saved .blend or UCC project. No cloud, AI, third-party asset download, full-body auto-mapping, FBX loader or installed new dependency is introduced.

**The source-to-target motion is deliberately uncalibrated direct-name rotation deltas — NOT full retargeting or engine-ready animation.** Most complex Fab/Mixamo full-body clips will require later mapped rest-pose retargeting. The [local BVH compatibility and permission guide](docs/integration/local-bvh-source-motion.md) documents strict limits. The [real Linux Blender/MPFB source-driven BVH integration run #43108579117](https://github.com/DocDamage/newestcharactercreator/actions/runs/43108579117) **passed**: an original 25-frame BVH controlled the existing MPFB head bone and moved 4,451 actual mesh vertices at intermediate frames. Two processes agreed; the original master, BVH and project stayed unchanged. Actual Windows Blender/MPFB and third-party Fab motion remain untested.

## Multi-bone BVH chain and rest-axis checks — proposed PR #32

[PR #32](https://github.com/DocDamage/newestcharactercreator/pull/32) extends the reviewed local BVH workflow from **one** MPFB bone to a **directly connected two-to-four-bone source chain**. The Animation library tab requires an explicit BVH Y-up-to-Blender Z-up or Z-up identity preset, as well as previously required local source rights confirmation. Blender checks exact bone names, actual parent links, original BVH rest offsets/directions, a measured bone-length ratio (multi-segment uniformity checked only for 3+ bones), XYZ Euler channel order and meaningful **independent skin movement for every mapped bone**. The temporary animation samples five frames in two separate SHA-checked Blender processes; neither source BVH nor the saved immutable master is overwritten.

**[Real Blender 5.3 + MPFB run #43116913629](https://github.com/DocDamage/newestcharactercreator/actions/runs/43116913629) PASSED the original CI-only neck03 → head source chain**: each existing bone moved 4,451 actual weighted vertices in an isolated 12-degree test; the child rest-direction cosine was **0.9949** under explicit Y-up-to-Z-up conversion, and two independent Blender processes agreed on actual animated geometry. This is **not** bone-roll/rest-space rotation calibration, realistic Fab retargeting, interactive UCC animation playback or certified Godot/Unity/Unreal import. [Strict usage and compatibility limits](docs/integration/bvh-multibone-rest-gate.md).

## BVH source-to-MPFB rest-space quaternion calibration — PR #33

[PR #33](https://github.com/DocDamage/newestcharactercreator/pull/33) implements the first narrow two-to-four-bone BVH **rest-rotation calibration** on the existing saved MPFB humanoid. After local reviewed-rights confirmation and explicit BVH up-axis selection, choose **Calibrate BVH rest axes and test 2–4 bone motion...** from the Animation library. Unlike the earlier uncalibrated local-Euler tests, this operation reads the BVH's terminal End Site and actual MPFB rest-bone matrices, requires **two non-collinear anatomical directions**, solves a proper source-to-target rest frame, checks every landmark within **5°**, then conjugates each frame's ordered relative rotation into each target bone's local rest axes and inserts actual quaternion keys in a private Blender Action. **The saved source/master/project remain untouched.**

[First genuine Blender/MPFB proof #43132955795](https://github.com/DocDamage/newestcharactercreator/actions/runs/43132955795) passed: `neck03 → head`, **2 landmarks**, maximum anatomical residual **2.9700°**, maximum bounded rest-matrix numeric projection **0.00001446**, **4,451 moved skinned vertices from each mapped bone**, and matching five-frame geometry across two independent Blender processes. Strict rotation output stays proper/right-handed. The source was an **original CI-only** 25-frame BVH, not a purchased Fab clip. This is **not** a full retargeter, independent external-skeleton roll proof, live UCC playback, or engine import. [Measurable acceptance criteria](docs/acceptance/UCC-P1-ANIM-004.md) · [User guide](docs/integration/bvh-restspace-quaternion-calibration.md).

## Current verified milestone (November 11, 2026)

[Pull request #24](https://github.com/DocDamage/newestcharactercreator/pull/24) removes the broken GitHub Actions runner-context expression and adds a **real Linux production-worker verification**, with evidence at [Actions run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064): Blender 5.3.0 with the official installed MPFB extension generated an editable `.blend` master (19,158 new mesh vertices, 163 reopened armature bones). A separate Blender worker process reopened an identical master successfully. The core/preflight CI checks also passed.

**Historical PR #24 limitations:** user's Windows Blender/MPFB, exact MPFB release pin, animations and game-engine imports were not verified by that step. Subsequent merged PRs added real in-app generation, phenotype regeneration, master refit and static preview; PR #29 tests an actual weighted-bone pose. See [current evidence/status](docs/STATUS.md). Older sections below describe incremental history, not the current readiness gate.

## Desktop humanoid generation — PR #25

[PR #25](https://github.com/DocDamage/newestcharactercreator/pull/25) adds an **opt-in real MPFB human generation action** in the existing desktop Character tab. After saving character metadata, select **Generate real MPFB humanoid...**, confirm, and point UCC to your already-installed Blender executable with MPFB enabled. It runs the real Blender worker twice, independently inspects the saved human/rig, checks the file hash, and makes the resulting `.blend` the project's new immutable master revision only if the saved project has not changed. Existing masters remain intact; cancellation and errors do not write a new project pointer.

This does **not** apply draft morph sliders to mesh geometry, animate or retarget a rig, or certify Godot/Unity/Unreal imports. All generated masters remain `generated_unverified` until later real deformation/export validation. The user's Windows Blender installation is still untested. See [generation instructions, failure modes and disk layout](docs/integration/humanoid-generation.md).

## Preview the saved Blender master (development PR #26)

A new **Preview saved master in UCC...** action in the Character tab converts the currently saved, content-addressed Blender `.blend` into a **private, temporary, untextured GLB** using the installed Blender executable you choose, then displays actual static triangles in the existing orbit/pan/zoom viewer. The original master and project metadata are never modified. It does not evaluate rig animation, MPFB morphs, skinning or game-engine imports. The [real Linux Blender/MPFB saved-master preview test passed](https://github.com/DocDamage/newestcharactercreator/actions/runs/43089727477), parsing 36,972 source triangles (1,946 sampled) from an actual MPFB humanoid. Windows Blender/MPFB still requires owner-machine testing. [Usage, safety, and verification details](docs/integration/saved-master-preview.md).

## Real MPFB body controls — proposed PR #27

[PR #27](https://github.com/DocDamage/newestcharactercreator/pull/27) connects the existing normalized **Height, Muscle and Weight** sliders to MPFB's documented real macro-target system. Save metadata first; **Generate humanoid using saved body controls...** creates a **new** immutable Blender master using those values. The worker independently reopens it and compares actual evaluated vertex fingerprints to prevent an un-applied slider from being reported as a changed model. Previous master versions stay intact; attached part/animation references block regeneration until validated.

**This is not live morphing** of an existing master. Normalized values are not centimeters/meters or kilograms. Real rig deformation under animation, the owner's Windows MPFB installation and Godot/Unity/Unreal imports remain unverified. The [body-control integration guide](docs/integration/mpfb-body-controls.md) explains all limitations and the independent Linux CI acceptance check.

## Update an existing humanoid master — proposed PR #28

[PR #28](https://github.com/DocDamage/newestcharactercreator/pull/28) adds **Apply saved body controls to existing master...** in the Character tab. Unlike new-base generation, this makes a private copy of the saved `.blend`, reapplies real MPFB Height/Muscle/Weight macro targets, and **refits the existing rig**. A second Blender process checks the edited body's real evaluated geometry, original bone-weight groups and armature bindings before any new immutable master revision is committed. The old master stays untouched.

This operation needs a saved character with **no external parts or animation references**, installed Blender/MPFB and saved slider values that actually differ from the current master. It is not live morphing, verified animated deformation or a certified Godot/Unity/Unreal export. [Workflow, safety and acceptance criteria](docs/integration/mpfb-existing-master-refit.md).

## Goal

A standalone Windows character creator using Blender 5.3 and MPFB to make an editable humanoid foundation, with modular body parts, animation/rigging, selectable local or cloud AI, and validated export to Godot, Unreal Engine, Unity, 2D and 2.5D workflows. The first hardware target is RTX 3060 12 GB. Broader anatomy types and 100+ animations are planned after a reliable end-to-end humanoid pipeline exists.

## Start here

1. [Full technical blueprint](UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md) — 39 locked requirements, development phases and core contracts.
2. [Coding-agent rules](AGENTS.md) — mandatory operating constraints.
3. [Stage 0 instructions](Stage0_Starter/README_START_HERE.md) and [quality gates](Development_Guardrails/docs/QUALITY_GATES.md).
4. [Preflight checklist](Development_Guardrails/docs/START_CHECKLIST.md) and [current verified status](docs/STATUS.md).
5. [Architecture decision](docs/decisions/0001-mpfb-baseline.md) and [license strategy](docs/LICENSE_STRATEGY.md).

## Test the provided preflight tools

Run from the repository root with Python 3:

```powershell
py -3 -m unittest discover -s Stage0_Starter/tests -v
py -3 -m unittest discover -s Development_Guardrails/tests -v
```

There are 15 dependency-free Python unit tests. They cover scanners, asset policies and fail-closed evidence gates — **not** the operation of MPFB in Blender or target-engine imports.

## Run the real Blender/MPFB compatibility test on Windows

Enable the official MPFB add-on in your installed Blender first. Substitute your actual Blender executable path below:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
```

The script collects local read-only audit results, runs actual MPFB creation, saves and reopens a Blender project in a second process, then checks evidence. Reports remain in ignored `evidence/`. If any step fails, `UCC-P0-001` remains blocked. Do not replace the test with a cube or claim success based on unit tests.

Optional **explicit opt-in** model directory scanning:

```powershell
py -3 .\Stage0_Starter\tools\audit_local.py --scan-root "D:\AI\models" --output .\preflight.json
```

Do not commit scanner reports containing personal paths, source Fab assets, model weights, character masters or purchased animation files.

## Development rules

Keep main stable; use one topic branch and PR per task. Don't silently install dependencies, fabricate successful integrations or ship placeholder assets. Track source permissions before any AI processing or export. No public distribution license is chosen yet. See [CONTRIBUTING.md](CONTRIBUTING.md).

**Next action:** run `UCC-P0-001` with the user's real Blender 5.3 + MPFB installation, and record logs, versions and actual saved/reopened character evidence.

## New: versioned core implementation (pre-UI)

A functional **Python metadata backend** now exists. It is not yet a graphical 3D creator. See [Implementation status](IMPLEMENTATION_STATUS.md) and [start guide](docs/START_DEV.md).

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests -v
py -3 -m ucc new "$env:USERPROFILE\Documents\UCC\FirstHuman" --name "First Human"
py -3 -m ucc info "$env:USERPROFILE\Documents\UCC\FirstHuman"
py -3 -m ucc slots
py -3 -m ucc plan-sprites --directions 8 --clip idle:8
```

Included: strict character/project data model, semantic body-part slots, reversible metadata edits, atomic revision-checked project saves, SQLite asset-provenance ledger, sprite camera/frame planner, and a cancellable Blender subprocess protocol. Its `blender_bridge/entrypoint.py` now has successful **Linux** integration evidence in PR #24; Windows Blender/MPFB remains unverified. No physical character geometry, animation export, or engine import is claimed until [UCC-P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2) passes on Windows.

**Unit tests are not Blender tests.** The real create/save/reopen test remains in `Stage0_Starter/` and `Development_Guardrails/`. Source checkpoints, purchased Fab animations, evidence containing personal paths, and project masters remain excluded from this public repo.


### Existing-PNG sprite atlases and local AI probes

These are implemented independently of Blender (no example character artwork is bundled):

- With the optional free Pillow library: \`py -3 -m pip install "Pillow>=11,<13"\`, then \`py -3 -m ucc pack-sprites --frames-dir "C:\UCC\ExistingFrames" --output-dir "C:\UCC\Atlases" --directions 8 --width 128 --height 128 --clip idle:8\`. The input files must match the generated frame plan. The tool produces real RGBA PNG sheets, a manifest with frame coordinates and source hashes, and rolls back partial output on failure.
- \`py -3 -m ucc probe-ai\` checks only loopback local ComfyUI and Stable Diffusion WebUI HTTP APIs, returning availability and limited capability metadata. It makes no POST requests, uploads or downloads, and does not reveal model filenames. See [AI probes](docs/integration/ai-probes.md).

The **Windows** Stage 0 real Blender smoke remains a blocker. New pure-Python tests cannot replace it.


### GLB export preflight, not an engine certification

\`py -3 -m ucc inspect-glb "C:\UCC\exports\character.glb"\` performs an actual read-only glTF 2.0 binary/JSON structure audit. It reports meshes, skins/joints, animations, morph targets, broken references and potential export gaps. It never marks Godot/Unity/Unreal import as passed. See [GLB offline inspection](docs/integration/glb-offline.md).


### Animation asset intake (metadata only)

UCC can now inspect one user-selected BVH, GLB or glTF file, extract declared clip and skeleton metadata, and store it in a private SQLite asset catalog. FBX and Unreal \`.uasset\` are cataloged as **requiring verified Blender/Unreal conversion** rather than inventing clip details. Unreviewed source licenses block engine export, AI input and source redistribution.

\`\`\`powershell
$env:PYTHONPATH = "src"
py -3 -m ucc inspect-animation "D:\MyAnimations\Walk.bvh"
py -3 -m ucc index-animation "D:\MyAnimations\Walk.bvh" --database "$env:LOCALAPPDATA\UCC\animation_library.db" --asset-id "walk-001" --provider "Fab" --license-name "unreviewed" --source-uri "ACTUAL_FAB_LISTING_URL"
py -3 -m ucc list-animations --database "$env:LOCALAPPDATA\UCC\animation_library.db"
\`\`\`

Replace paths and URL with real user-owned data; the example above is intentionally unreviewed. It does **not** download the user's Fab library, retarget a rig, or certify any animation's playback. See [animation intake guide](docs/integration/animation-intake.md) and [feature tracker #9](https://github.com/DocDamage/newestcharactercreator/issues/9).

## MPFB HumanService Stage 0 route (pending real Blender test)

The Stage 0 and production Blender scripts now prefer MPFB's officially documented `HumanService.create_human()` and `HumanService.add_builtin_rig()` scripting API instead of UI-operator `poll()` in background mode. A real human **and** built-in default armature must be saved and reopened in a separate Blender subprocess. The included service adapter passed a real **Linux** Blender/MPFB workflow in PR #24; mock-based tests alone are insufficient, and issue #2 remains open pending real Windows verification. See [integration notes](docs/integration/mpfb-humanservice.md).


## New: standalone UCC desktop development workstation

UCC now has a **functional PySide6 desktop UI** for character metadata editing, safe saves with revision/backup protection, undo/redo, a private animation source catalog, GLB structural inspection, read-only local AI API checks, and real sprite atlas packing from existing PNGs. This is **not yet a finished 3D character editor**; mesh deformation/retargeting and Godot/Unity/Unreal import need real integration evidence. Beginner and advanced metadata modes are included, and a saved Blender master can be opened externally in the user's installed Blender.

On Windows, with Python 3.12+:
\`\`\`powershell
py -3 -m pip install -e ".[desktop,sprites]"
py -3 -m ucc.desktop
\`\`\`
Or run \`ucc-desktop\`. No IDE is required. No third-party character assets, AI models, or game engines are installed by this command. See [Desktop v0.1 usage and limits](docs/integration/desktop-v0.1.md).

The Qt workflow tests real widgets using \`QT_QPA_PLATFORM=offscreen\` on Windows/Linux. A passing offscreen test is not proof of GPU rendering or working MPFB in Blender.


## Experimental Windows portable desktop alpha (no IDE required)

The desktop now includes an **opt-in GitHub Actions Windows alpha builder**. It packages the actual PySide6 workstation into a Windows x64 `UCC-Desktop-Alpha.exe` folder, exercises a **real frozen-executable Qt plus character project save/reopen diagnostic**, then archives the executable and SHA-256 hash as an ephemeral GitHub Actions artifact. It does not bundle Blender, MPFB, Fab assets, checkpoints, characters, or game engines. The archive is for private QA, **not a public release or distribution license decision**.

- [Windows alpha package setup and restrictions](docs/packaging/WINDOWS_ALPHA_README.md)
- [Actions build workflow](.github/workflows/windows-alpha-package.yml) — after a successful build, open the workflow run and download `UCC-Desktop-Alpha-Windows-x64` under Artifacts.
- The binary's `--self-test --self-test-report FILE.json` performs an actual Qt widget startup and temporary local project save/reopen; **it does not prove Blender/MPFB geometry, animation, GPU rendering or engine imports**.

## Read-only GLB geometry viewer (preview-only)

The optional PySide6 desktop now supports **View → Preview local GLB model...** (Ctrl+Shift+M). It renders a sampled subset of actual embedded glTF 2.0 triangle geometry with Qt's CPU painter. Orbit, pan, zoom and reset work without OpenGL drivers or third-party asset packs. The parser validates container relationships, transform bounds, vertex/index accessors and a hard aggregate face limit. It **does not** skin meshes, run motion, evaluate morphs, import materials or certify engine compatibility; this viewer is not the eventual animated character editor. See [GLB static preview](docs/integration/glb-static-preview.md).

The desktop CI requires real, non-skipped Qt widget tests on Windows and Linux, and a separate metadata/mesh parser test suite. No demo character art or proprietary asset has been committed.
