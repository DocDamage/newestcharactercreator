# Universal Character Creator — Development Guardrails & Verification Kit

**Purpose:** Companion to `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` and `Stage0_Starter/`. The blueprint defines the product; this kit imposes implementation constraints and verifiable go/no-go gates. **This kit is not the finished creator.**

## Before you start

1. Extract the **complete combined package**. Keep `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`, `Stage0_Starter/`, and `Development_Guardrails/` in one directory.
2. Give your coding agent **both** the blueprint and `Development_Guardrails/AGENTS.md`. Explicitly tell it to start with `UCC-P0-001` only.
3. Install/enable MPFB in Blender 5.3 yourself. Do not assume it works headlessly; test it. Do not download random extensions/checkpoints automatically.
4. On Windows, run `Development_Guardrails/scripts/run_stage0.ps1` (instructions in that file) with `-BlenderPath` and optional `-ScanRoot`. This gathers a local audit and a Blender+MPFB smoke report in an `evidence/` folder.
5. Run `py -3 Development_Guardrails/tools/verify_gate.py --gate P0_SPIKE --evidence-dir evidence`. It **must fail** if the real Blender/MPFB smoke test failed, was skipped, or proof is missing. A successful structural gate also requires examining the Blender-created file and logs.
6. Run unit tests: `py -3 -m unittest discover -s Development_Guardrails/tests -v`.

## Packaging layout

```
UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md
Stage0_Starter/
Development_Guardrails/
  AGENTS.md
  README.md
  config/gates.json
  config/asset_manifest.json
  config/P0_SPIKE.evidence.example.json
  docs/START_CHECKLIST.md
  docs/QUALITY_GATES.md
  docs/EXPORT_TEST_MATRIX.md
  docs/ASSET_POLICY.md
  docs/IMPLEMENTATION_HANDOFF.md
  docs/FAILURE_RECOVERY.md
  scripts/run_stage0.ps1
  tools/collect_p0.py
  tools/verify_gate.py
  tools/check_asset_policy.py
  tests/
  .github/workflows/unit-tests.yml
```

**GitHub Actions:** When you initialize the real repository, copy `Development_Guardrails/.github/workflows/unit-tests.yml` to the repository root `.github/workflows/` so GitHub recognizes it.

## Gate policy

- A file existing is not evidence of a working imported/animated character. The gate checks files, hashes, and a subset of Stage 0 machine reports; a human must validate engine import and visually review deformations.
- Missing evidence, unknown licenses, or crashes => **BLOCK**, not `PASS`.
- Never synthesize P0 evidence or fabricate an actual Blender/MPFB test result. Example JSON files deliberately contain `not_run`.
- Do not ship MPFB, Aseprite, Fab source animations or AI checkpoints as part of a public installer without a specific distribution/license review.

## Immediate success criterion

One real MPFB human is created in **your** installed Blender 5.3, saved as a `.blend`, reopened by a **separate** Blender process with substantial geometry intact, with a report identifying the version and observed behavior. UI work starts only after this gate is green or an explicitly documented alternate MPFB integration approach passes equivalently rigorous tests.

## Scope

Our design must be extensible to animals, dragons, unusual anatomy, more than 100 animation clips, 2D/2.5D and 3D, but **those are not all required in the first coding milestone**. First get one rigged and customizable human with reliable save/reopen and three target-engine imports. The blueprint is authoritative if kit guidance conflicts; escalate any contradiction as an Architecture Decision Record (ADR), not a silent rewrite.
