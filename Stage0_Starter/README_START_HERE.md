# Universal Character Creator — Stage 0 smoke

This runs a read-only local environment audit and a real Blender/MPFB human creation, rigging, save and fresh-process reopen test. The tests do not install or enable third-party software.

## 1. Prerequisites

Install and enable Blender 5.3 and the official MPFB extension in Blender. Python 3.12+ is needed for the outer tests. The MPFB `HumanService` API is used rather than the UI `create_human` operator, reducing dependence on an interactive context. Compatibility remains unverified until you actually run the smoke.

## 2. Run the complete quality gate (PowerShell)

From the repository root, substituting your actual Blender path:

```powershell
powershell -ExecutionPolicy Bypass -File .\Development_Guardrails\scripts\run_stage0.ps1 -BlenderPath 'C:\Program Files\Blender Foundation\Blender 5.3\blender.exe'
```

This writes private evidence into `evidence/`, checks MPFB generated an actual human mesh **with a built-in rig**, saves a `.blend`, and uses a separate Blender process to reopen it and count meshes, vertices and armature bones. A failed test is **not passed** by a dummy cube, generated metadata or a synthetic fixture. The script exits nonzero if the required gate fails.

## 3. Optional read-only model inventory

```powershell
py -3 .\Stage0_Starter\tools\audit_local.py --scan-root 'D:\AI\models' --output 'evidence\preflight.json'
```

Do not scan other folders without your explicit approval. Local file names, paths and model inventories must not be posted in this public GitHub repo.

## 4. Unit tests (not Blender tests)

```powershell
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s Stage0_Starter/tests -v
py -3 -m unittest discover -s Development_Guardrails/tests -v
```

Read [MPFB HumanService integration notes](../docs/integration/mpfb-humanservice.md) and [quality gates](../Development_Guardrails/docs/QUALITY_GATES.md).
