# ADR 0002 — Versioned domain core and isolated Blender worker

**Status:** Implemented as a pre-UI backend, Blender integration pending real validation.

## Motivation

MPFB's Blender operators and Blender Python cannot be assumed to run safely inside the Qt application process. An external Blender process also means user edits survive its crashes. However, core data should be testable without MPFB, Python UI packages, licensed asset downloads or a GPU.

## Decision

- Core character records are immutable `dataclasses`, with strict JSON schema version 1 and explicit state `not_generated`, `generated_unverified`, or `validated`. The first project can be a metadata draft without fabricated geometry.
- Project edits are metadata commands with bounded undo/redo and monotonically increasing revisions. They **never** silently alter a `.blend`.
- Disk persistence is scoped to an explicit project directory. Locking and optimistic revisions reject lost updates, metadata is written by temporary file + `os.replace`, and previous revisions are snapshotted. This is not yet a multi-file geometry transaction.
- `PartAsset` entries must include family, slot, socket, type, license record ID and (for skinning) rig and rest-pose fingerprint. Metadata selection creates only a `proposed` attachment. Independent Blender fit and deformation checks will have to promote it; a model not yet verified cannot be considered export-ready.
- Any Blender job is JSON `protocol_version=1`, uses a UUID, allowlisted operation, isolated per-job folder, no shell invocation, timeout, cancellation and evidence logs. Results are staged; no direct authoritative model mutation or automatic promotion.
- Approved job commands initially cover inspection and MPFB default human creation. The exact MPFB operator and headless behavior require actual Windows testing, and must not be inferred from code compiling.
- Sprite generation starts as an immutable deterministic **plan**; no claims of real images without rendering.
- A local SQLite metadata catalog tracks source SHA256 and explicit, conservative asset license flags. It is outside the repo and contains no purchased binary assets.

## Alternatives rejected

- Automatically building arbitrary geometry from AI reference images before rig validation.
- A single universal skeleton for human/dragon/quadruped.
- Using `.glb` preview as authoritative editable character source.
- Qt code calling `bpy` in-process.
- Treating successful file writing as successful import into Godot/Unity/Unreal.
- Unconstrained generated Python scripts as worker jobs.

## Next

1. Execute actual MPFB create/save/reopen and identify supported Blender 5.3 context.
2. Define a checked and **multi-file atomic transaction** for geometry+metadata promotion.
3. Build an initial real human viewport without introducing replacement assets unless authorized.
4. Run real engine import tests with versioned sample character and permitted clips.
