# Blender 5.3 worker: current contract and limitations

This code is a **real integration attempt, but has not yet run in Blender 5.3**. It is intentionally isolated from the rest of the character editor.

## Contract

`src/ucc/jobs/protocol.py` defines `protocol_version=1`, a strict UUID job ID, and initial operations:

- `inspect_environment`: report Blender version and whether the MPFB `create_human` operator is registered and pollable.
- `inspect_character`: open a **staged copy** of a provided `.blend` and count meshes/vertices, armatures/bones, and shape keys. This is structural inspection, not visual rig approval.
- `create_human`: call `bpy.ops.mpfb.create_human()` when available in the current Blender context and stage `generated_human.blend`; it remains **unverified** until reopened and reviewed separately.

`src/ucc/jobs/runner.py` invokes the Blender executable with explicit argument arrays, `--background`, `--disable-autoexec`, the bundled `blender_bridge/entrypoint.py`, and a request/result pair within a per-job directory. It does not use `--factory-startup` (which can suppress extensions).

### Example: inspected environment only

From repository root, once Blender 5.3 and MPFB are installed:

```powershell
$env:PYTHONPATH = "src"
py -3 -m ucc probe-blender --blender "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --jobs "$env:LOCALAPPDATA\UCC\jobs"
```

This command does **not** create a character. If `mpfb_operator.registered=false` or `poll=false`, the create command remains blocked. To attempt the full real create/save/reopen smoke use the existing Stage 0 script:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
```

Substitute the actual installed executable path. Never commit reports that expose local paths or proprietary assets.

## Failure, security and recovery

- No arbitrary Python, Blender code or custom script request is supported by the JSON protocol.
- Inbound `.blend` files must be explicitly copied into a new job workspace via `staged_inputs`; the original remains unchanged.
- Output directories are unique by UUID, and previously used IDs cannot be reused.
- Jobs are killed on timeout or cancellation, with logs retained; an error result never becomes a successful stage.
- There is **no** automatic write from a job to the character's authoritative master model. A future promotion routine must reopen and validate the new master in Blender before replacing the old one atomically with JSON metadata.
- MPFB `create_human.poll()` may fail in background mode due to context. Record the actual failure and use the P0 issue to evaluate a verified interactive-context route. Do not fake geometry to make a gate pass.
- The RTX 3060 12 GB GPU requires an actual resource scheduler for AI and render workloads; no GPU concurrency is claimed at this stage.
