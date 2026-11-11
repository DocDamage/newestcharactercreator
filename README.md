# Universal AI Character Creator

**Project stage: preparation and environment validation.** This repository is a development foundation, not a finished character creator.

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

Included: strict character/project data model, semantic body-part slots, reversible metadata edits, atomic revision-checked project saves, SQLite asset-provenance ledger, sprite camera/frame planner, and a cancellable Blender subprocess protocol. Its `blender_bridge/entrypoint.py` is an **untested real Blender integration candidate**. No physical character geometry, animation export, or engine import is claimed until [UCC-P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2) passes on Windows.

**Unit tests are not Blender tests.** The real create/save/reopen test remains in `Stage0_Starter/` and `Development_Guardrails/`. Source checkpoints, purchased Fab animations, evidence containing personal paths, and project masters remain excluded from this public repo.


### Existing-PNG sprite atlases and local AI probes

These are implemented independently of Blender (no example character artwork is bundled):

- With the optional free Pillow library: \`py -3 -m pip install "Pillow>=11,<13"\`, then \`py -3 -m ucc pack-sprites --frames-dir "C:\UCC\ExistingFrames" --output-dir "C:\UCC\Atlases" --directions 8 --width 128 --height 128 --clip idle:8\`. The input files must match the generated frame plan. The tool produces real RGBA PNG sheets, a manifest with frame coordinates and source hashes, and rolls back partial output on failure.
- \`py -3 -m ucc probe-ai\` checks only loopback local ComfyUI and Stable Diffusion WebUI HTTP APIs, returning availability and limited capability metadata. It makes no POST requests, uploads or downloads, and does not reveal model filenames. See [AI probes](docs/integration/ai-probes.md).

The Stage 0 real Blender smoke remains the blocker. New pure-Python tests cannot replace it.


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

The Stage 0 and production Blender scripts now prefer MPFB's officially documented `HumanService.create_human()` and `HumanService.add_builtin_rig()` scripting API instead of UI-operator `poll()` in background mode. A real human **and** built-in default armature must be saved and reopened in a separate Blender subprocess. The included service adapter is tested with mock extension objects, not actual Blender/MPFB; do not mark issue #2 complete from CI alone. See [integration notes](docs/integration/mpfb-humanservice.md).


## New: standalone UCC desktop development workstation

UCC now has a **functional PySide6 desktop UI** for character metadata editing, safe saves with revision/backup protection, undo/redo, a private animation source catalog, GLB structural inspection, read-only local AI API checks, and real sprite atlas packing from existing PNGs. This is **not yet a finished 3D character editor**; mesh deformation/retargeting and Godot/Unity/Unreal import need real integration evidence. Beginner and advanced metadata modes are included, and a saved Blender master can be opened externally in the user's installed Blender.

On Windows, with Python 3.12+:
\`\`\`powershell
py -3 -m pip install -e ".[desktop,sprites]"
py -3 -m ucc.desktop
\`\`\`
Or run \`ucc-desktop\`. No IDE is required. No third-party character assets, AI models, or game engines are installed by this command. See [Desktop v0.1 usage and limits](docs/integration/desktop-v0.1.md).

The Qt workflow tests real widgets using \`QT_QPA_PLATFORM=offscreen\` on Windows/Linux. A passing offscreen test is not proof of GPU rendering or working MPFB in Blender.
