# Universal Character Creator — Stage 0 Starter Kit

**What this is:** A *read-only* Windows environment audit and an *actual* Blender/MPFB generation smoke test. It is not the character creator app and it does not download/install any software.

**Preconditions:** Existing Blender 5.3, Python 3, and MPFB extension. MPFB may need to be enabled inside Blender first.

## 1. Environment audit (PowerShell)

```powershell
py -3 .\tools\audit_local.py --output .\preflight.json
```

By default, this **does not scan drives**. It probes common Blender/Aseprite paths and local ComfyUI/WebUI endpoints. To find existing models in specific selected directories:

```powershell
py -3 .\tools\audit_local.py --scan-root "D:\AI\models" --scan-root "F:\ComfyUI\models" --output .\preflight.json
```

Use your *actual* model paths in place of these examples. Generated JSON may reveal private local paths: keep it on your PC and review before sharing.

## 2. MPFB smoke test (PowerShell)

```powershell
py -3 .\tools\run_mpfb_smoke.py --blender "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
```

This creates `ucc-smoke-results/mpfb_created.blend` and a JSON report **only if the MPFB operator is available and completes**. Then it opens the generated `.blend` in a fresh Blender subprocess to verify that real mesh geometry persists.

If it says `NOT PASSED`, open the report and examine the creation logs; **do not use a dummy cube as a replacement or claim MPFB integration works**. In some Blender add-on setups the operator needs interactive Blender context or an alternate verified MPFB service call.

## 3. Official free dependency links

- MPFB: https://extensions.blender.org/add-ons/mpfb/
- MPFB source/API docs: https://github.com/makehumancommunity/mpfb2
- Aseprite source updating/build instructions: https://github.com/aseprite/aseprite/blob/main/INSTALL.md

**No automatic third-party executable download is performed.** The assistant cannot inspect your actual Windows hard drives from this workspace.

## 4. Run the dependency-free unit tests

```powershell
py -3 -m unittest discover -s .\tests -v
```

They test only read-only model scanner behavior; **they do not prove MPFB/Blender compatibility**. The latter requires the real Windows installation and the smoke runner above.
