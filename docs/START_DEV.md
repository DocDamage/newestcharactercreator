# Development start — no IDE required for preflight metadata tooling

The repository currently contains a tested, dependency-free **backend foundation** plus the Stage 0 environmental smoke tools. No finished graphical character creator is advertised. Commands below are optional and can be run from PowerShell once a source checkout is available.

## Verify pure Python tooling (without Blender)

From repository root with Python 3.12 or newer:

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests -v
py -3 -m unittest discover -s Stage0_Starter/tests -v
py -3 -m unittest discover -s Development_Guardrails/tests -v
```

## Use the real metadata CLI

```powershell
$env:PYTHONPATH = "src"
py -3 -m ucc new "$env:USERPROFILE\Documents\UCC\FirstHuman" --name "FirstHuman"
py -3 -m ucc info "$env:USERPROFILE\Documents\UCC\FirstHuman"
py -3 -m ucc morph "$env:USERPROFILE\Documents\UCC\FirstHuman" height 0.65
py -3 -m ucc slots
py -3 -m ucc plan-sprites --directions 8 --width 128 --height 128 --clip idle:8 --clip walk:12
py -3 -m ucc probe-ai
```

To assemble real spritesheets from **existing** transparent PNG frames (e.g., future Blender renders), install free Pillow into your development environment and use:

```powershell
py -3 -m pip install "Pillow>=11,<13"
py -3 -m ucc pack-sprites --frames-dir "C:\UCC\ExistingFrames" --output-dir "C:\UCC\Atlases" --directions 8 --width 128 --height 128 --clip idle:8
```

The PNG folder must contain `idle/dir-00/frame-0000.png`, etc., matching the exact plan. The packer verifies real pixels, RGBA, sizes, hashes, and metadata, and rejects missing frames. No generated character images are supplied in the repo.

**The project commands edit only metadata and can generate a sprite render *plan*.** A morph value does not physically change Blender geometry until MPFB target mapping is verified and integrated. A render plan does not generate PNGs.

## Local files and privacy

Do not commit `project.ucc.json` from real personal projects, private working `.blend` files, Fab animation downloads, AI checkpoint weights, or local audit logs. The asset index and job workspace should use a local user data directory and must not be uploaded to GitHub without review.

## First real integration gate

The next blocker is [P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2). Run real Blender/MPFB create/save/reopen and retain the test evidence locally. A passing GitHub Actions check only validates code logic and file contracts, not geometry, rendering or game-engine compatibility.
