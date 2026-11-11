# MPFB HumanService first — Stage 0 generator and rig smoke

**Status:** source-backed implementation with pure-Python contract tests; **not validated** inside the user's Blender 5.3 installation.

## Why this changes P0

The former Stage 0 smoke called the UI operator `bpy.ops.mpfb.create_human()` and depended on `.poll()` being true in `--background`. MPFB's own [scripting examples](https://github.com/makehumancommunity/mpfb2/blob/master/script_samples/03_adding_a_default_rig.py) expose a more direct `HumanService` API for automation: `HumanService.create_human()` and `HumanService.add_builtin_rig(basemesh, "default")`. Its [HumanService documentation](https://github.com/makehumancommunity/mpfb2/blob/master/docs/services/humanservice.md) identifies both methods and their roles. This avoids relying on UI-specific operator context, **but is not proof that background mode or Blender 5.3 works**.

The new `blender_bridge/mpfb_service.py` dynamically locates MPFB's enabled extension module using the pattern shown by MPFB's official examples (the extension may be nested under `bl_ext.*`). The code doesn't install, enable, download, or add unreviewed extensions. Ambiguous or absent MPFB modules block generation with an actionable error.

The P0 generator now creates **one real humanoid basemesh and one default built-in rig** (including the individual toe option), requires substantial mesh geometry and five or more armature bones, saves to a temporary job directory, and independently reopens the `.blend` in a **new Blender process** to validate persistent mesh and rig. The implementation does not claim correct skinning, retargeted motion or engine export merely because a mesh and rig exist.

## To run locally (when ready, no IDE)

From the repo root in PowerShell, after installing and enabling MPFB in Blender:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'
```

Replace the example path with the actual Blender executable. The existing script stores audit and saved/reopened character evidence privately under ignored `evidence/` and keeps the gate blocked if MPFB is missing or runtime generation fails. No user project is modified. Check the P0 report for `method=HumanService`, `rig_choice=default`, `new_mesh_vertices`, `rigs[].bone_count`, `reopen_result.json` and real `.blend` output.

The production worker `blender_bridge/entrypoint.py` uses the same service adapter and stages `generated_human.blend`; it deliberately returns `verified_reopen=false`. The worker cannot promote output to a production character automatically. No new user-editable rig option is exposed before MPFB compatibility is established.

## Failure cases and next actions

- **MPFB not loaded:** confirm the official extension is installed and enabled. The service lookup will not silently import an arbitrary named module from a user path.
- **Multiple MPFB extensions:** disable duplicates; the adapter refuses arbitrary selection.
- **Service import fails:** record exact Blender/extension versions and logs in a private issue; test MPFB's official script samples and verify the module import context rather than introducing synthetic geometry.
- **Human created but default rig failed:** retain the failed smoke log but do not treat a mesh-only result as a pass.
- **Background generation fails:** document the precise Blender/MPFB limitation, then test an explicitly documented, isolated GUI-context route; **do not weaken the quality gate**.

After P0 passes, the next tasks are MPFB morph mapping, rigging/deformation validation, editable master save/reopen and one real Godot/Unreal/Unity import test. `mpfb_service.py` contract tests use mock Blender/MPFB objects and are **not** substitutes for P0.
