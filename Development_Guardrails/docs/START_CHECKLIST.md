# Before First Commit — Checklist

Use these checkpoints, not an abstract 'ready' state.

## Environment
- [ ] Record Windows build, CPU, RAM, GPU and available storage; use actual versions, not expected ones.
- [ ] Run **read-only** `Stage0_Starter/tools/audit_local.py`; store report in ignored `evidence/` directory.
- [ ] User-approved Blender 5.3 and MPFB installation/enablement; log MPFB version and API availability.
- [ ] Execute real MPFB `create_human` and fresh-process `.blend` reopen using Stage0 scripts.
- [ ] Record MPFB headless limitation if found, then test an alternative **real** Blender automation route before changing architecture.
- [ ] Record ComfyUI/WebUI reachability, model names, versions, disk/VRAM footprint without downloading duplicates.
- [ ] Confirm target engine versions and which are actually installed; no false completion for unavailable engines.

## Repo & development
- [ ] Git `main` protected, feature branch per task, issues/PRs as appropriate; no merge on red tests.
- [ ] `.gitignore` excludes purchased animations, checkpoints, `.blend1`, temp exports, evidence with private paths, secrets, caches and user-owned art.
- [ ] Preserve the 39 locked requirements in a versioned decision record.
- [ ] Define contracts for character JSON, part sockets, skeleton profile, job protocol, asset provenance and output manifests.
- [ ] Establish baseline `ruff`, `mypy`/`pyright` where feasible, `pytest`/`unittest`, schema tests and atomic save tests.
- [ ] All backend jobs support timeout, progress, cancellation, error records and safe cleanup.

## Milestone 1 acceptance
- [ ] One actual MPFB-generated humanoid, editable parameters, deforming animation and accurate full-body preview.
- [ ] Save, close, reopen: geometry, parts, pose, material, morphology, references and provenance persist.
- [ ] Swap at least one compatible part; attach/deform correctly; undo/redo and conflict handling work.
- [ ] Exported character **imports and animates** in Godot, Unity **and** Unreal (three separate proofs).
- [ ] RGBA spritesheet rendered with user-selected angle and resolution; frame count and alpha verified.
- [ ] Intentional Blender worker crash/timeout does not damage authoritative master.

No release candidate without green engine-import evidence and an asset/license review.
