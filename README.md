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
