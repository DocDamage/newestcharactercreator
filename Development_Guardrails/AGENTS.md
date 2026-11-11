# Coding Agent Operating Contract — Universal Character Creator

These instructions supplement `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`. Follow the blueprint's locked decision record and implementation sequence. The current target is Windows 11, Blender 5.3, RTX 3060 12 GB, MPFB, ComfyUI, Stable Diffusion WebUI, Aseprite, Godot, Unity, Unreal.

## Absolute constraints

1. **Do not restart the project or change the stack** without a written ADR and user authorization. Make additive, incremental changes; maintain prior working features.
2. **No fabricated success.** Do not claim generation, rigging, animation, export, or engine integration works merely because a script returns 0 or a sample file exists. Capture real logs and target-application verification evidence.
3. **No unauthorized placeholders.** Do not introduce substitute assets, fake geometry, sample sprites/models, dummy animations, or AI-generated promotional art into the product as though complete. Small non-shipping synthetic unit-test fixtures may be used if clearly named, isolated under `tests/fixtures`, and needed to test logic; never pass such fixtures as proof of Blender/MPFB integration.
4. **Never silently download or install** software, models, dependencies, assets, or extensions. The user has authorized free tools in principle, but present provenance, license, size, version, hash where provided, disk requirements, and destination before executing a real install on their PC. No covert networking.
5. **No default cloud transmission.** API provider selection and data upload require explicit user choice at the time of use. Local model discovery is read-only and opt-in; no whole-disk scan without affirmative permission.
6. **Fab and other third-party files must remain private.** Do not check in purchased assets or redistribute sources. Verify per-asset license, especially NoAI and UE-only flags; store provenance. AI training permission is *not* implied by personal game use.
7. **Preserve originals.** Snapshot the editable master, stage edits in temporary working copies, validate, then atomically commit. Undo/redo state must remain coherent; recover after Blender/AI crashes.
8. **Keep core isolated.** `ucc-core` cannot import `bpy`, Qt, or model runtime code; `ucc-blender-bridge` is the sole Blender process adapter. Every provider uses a versioned contract. Family-specific rigs must not be forced into a single universal skeleton.
9. **Quality over breadth.** One end-to-end verified human beats dozens of menu items that are not wired. No new UI control without defined behavior, tests, and error states.
10. **Modularity.** Separate domain/data/IO/UI/engine adapters; target files around 300–500 LOC, split logically rather than allowing monoliths. Add type annotations and structured errors to boundary code. Use formatting/linting/types/tests where viable. Do not add unused dependencies.

## Work protocol for each task

- **Inspect** the existing code, tests, decisions and environment before editing.
- **Plan** task ID, dependencies, touched files, reversibility, and *measurable* acceptance criteria.
- **Implement** the smallest vertical slice; provide a diff or patch, never replace unrelated modules wholesale.
- **Test** in layers: unit -> integration -> actual Blender/MPFB -> actual engine imports as applicable. Record exact tool versions, commands, return codes, logs, hashes and screenshots for visual checks.
- **Review** source/license impact, security of input paths, VRAM behavior, provenance, cancellation, timeouts and rollback.
- **Report** what works, what is blocked, how to reproduce, and the **single next task**. Never label an unexecuted test as passed.

## Sequential task ordering

1. `UCC-P0-001` MPFB operator smoke test, real save/reopen, compatibility ADR.
2. `UCC-P0-002` dependency inventory and license decisions (no install without verification).
3. `UCC-P0-003` versioned Blender job protocol + timeouts, cancellation, rollback.
4. Milestone 1: editor and character graph -> save/load -> part swap -> rig/animation preview -> reimport in Godot/Unity/Unreal -> sprite sample.
5. Milestone 2: mixed-rig retargeter, **100+ usable clips**, Fab per-pack license scan, exact clip states.
6. Milestone 3: AI part workflows and other body families; controlled model selection and GPU queues.

## Security and compatibility corner cases

Malformed JSON, missing files, symlink escape, duplicate IDs, mixed units, negative scale, mismatched bind poses, missing texture references, wrong forward/up axes, unsupported blendshapes, missing bones, blendshape-name collisions, external model version change, no internet, 12 GB VRAM OOM, Blender cancellation/crash, unsaved files, and source license uncertainty must produce explicit errors and reversible behavior.

## Agent final response format

`Task ID`, `Changed files`, `Verified results`, `Blocked/unrun tests`, `License/dependency changes`, `Next action`. Never claim installation or engine integration on a computer you cannot control.
