# MPFB HumanService first — Stage 0 generator and rig smoke

**Status (2026-11-11, proposed PR #24):** **Real Linux Blender 5.3.0 + official MPFB extension generation and independent reopen passed.** Actual Windows compatibility, deformation, animation and game-engine imports remain unverified.

## Why this changes P0

The former Stage 0 smoke called the UI operator `bpy.ops.mpfb.create_human()` and depended on `.poll()` being true in `--background`. MPFB's own [scripting examples](https://github.com/makehumancommunity/mpfb2/blob/master/script_samples/03_adding_a_default_rig.py) expose a more direct `HumanService` API for automation: `HumanService.create_human()` and `HumanService.add_builtin_rig(basemesh, "default")`. Its [HumanService documentation](https://github.com/makehumancommunity/mpfb2/blob/master/docs/services/humanservice.md) identifies both methods and their roles. This avoids relying on UI-specific operator context. The [real Linux run](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064) demonstrates that the service works in **that** Blender 5.3.0 Linux environment, not in a user's Windows installation.

The new `blender_bridge/mpfb_service.py` dynamically locates MPFB's enabled extension module using the pattern shown by MPFB's official examples (the extension may be nested under `bl_ext.*`). The code doesn't install, enable, download, or add unreviewed extensions. Ambiguous or absent MPFB modules block generation with an actionable error.

The P0 generator now creates **one real humanoid basemesh and one default built-in rig** (including the individual toe option), requires substantial mesh geometry and five or more armature bones, saves to a temporary job directory, and independently reopens the `.blend` in a **new Blender process** to validate persistent mesh and rig. The implementation does not claim correct skinning, retargeted motion or engine export merely because a mesh and rig exist.

## Observed Linux evidence (separate from Windows)

- [PR #24 smoke + production worker run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064): **success**, no skipped required creation/reopen steps. The separate official download step checked Blender 5.3.0 SHA-256; the official Blender Extensions installer succeeded.
- The Stage 0 script created a real MPFB humanoid + built-in rig, saved the `.blend`, and reopened it in another Blender process.
- The **production** `BlenderJobRunner` created one new 19,158-vertex human mesh and a default armature. An independently invoked Blender inspect worker found two total meshes (19,166 vertices including the startup cube) and **163 bones**. It checked a byte-identical saved `.blend` copy (2,164,606 bytes, SHA-256 `5fd31980ba72298cab4d18010d05295e9c7b121d1b7cbc445a9c6b48b7fe06cf`).
- [Core tests](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628189) and [preflight tests](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628138) passed. The integration artifact retains **JSON only**, temporarily; `.blend` files remain on the ephemeral runner.
- **Important reproducibility caveat:** the workflow installs MPFB from the official live extension registry using `extension install -e mpfb`, not a version-pinned 2.0.18 archive. Blender is pinned; MPFB's exact installed manifest version is **not yet recorded**. A future dependency-free version/manifest capture or verified pin is still needed. No result proves a particular MPFB patch release or the user's Windows setup.

## To run locally (when ready, no IDE)

From the repo root in PowerShell, after installing and enabling MPFB in Blender:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'
```

Replace the example path with the actual Blender executable. The existing script stores audit and saved/reopened character evidence privately under ignored `evidence/` and keeps the gate blocked if MPFB is missing or runtime generation fails. No user project is modified. Check the P0 report for `method=HumanService`, `rig_choice=default`, `new_mesh_vertices`, `rigs[].bone_count`, `reopen_result.json` and real `.blend` output.

The production worker `blender_bridge/entrypoint.py` uses the same service adapter and stages `generated_human.blend`; it deliberately returns `verified_reopen=false`. The separate `ci/verify_production_worker.py` runner **actually reopens that master through a second JSON worker job**, checks byte-identical input copies, validates mesh/bone counts and preserves only JSON evidence. It does not promote output into a user's character project or claim deformation quality. Windows parity and the transactional desktop generation action are still pending.

## Failure cases and next actions

- **MPFB not loaded:** confirm the official extension is installed and enabled. The service lookup will not silently import an arbitrary named module from a user path.
- **Multiple MPFB extensions:** disable duplicates; the adapter refuses arbitrary selection.
- **Service import fails:** record exact Blender/extension versions and logs in a private issue; test MPFB's official script samples and verify the module import context rather than introducing synthetic geometry.
- **Human created but default rig failed:** retain the failed smoke log but do not treat a mesh-only result as a pass.
- **Background generation fails:** document the precise Blender/MPFB limitation, then test an explicitly documented, isolated GUI-context route; **do not weaken the quality gate**.

After the Windows P0 gate passes, the next tasks are a crash-safe desktop worker-to-project transaction, MPFB morph mapping, rigging/deformation validation, and one real Godot/Unreal/Unity import test. `mpfb_service.py` contract tests use mock Blender/MPFB objects and are **not** substitutes for P0.
