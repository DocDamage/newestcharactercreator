# UCC Desktop — Windows alpha internal testing build

**Status:** Early, unsigned development build for the repository owner's private testing. This is **not** a finished 3D character creator, an installer, or a public release. No license to redistribute project code or source assets has been selected.

## Run without an IDE or Python installation

1. On the repository's GitHub **Actions** tab, open the most recent successful **Windows desktop alpha build (internal testing)** run.
2. Download `UCC-Desktop-Alpha-Windows-x64` under **Artifacts** and extract the ZIP twice if GitHub has wrapped the archive.
3. Keep the entire `UCC-Desktop-Alpha` folder intact; run `UCC-Desktop-Alpha.exe` inside it.
4. The optional `frozen-health.json` beside the archived build proves only that this GitHub-built application passed **real Qt widget startup and character-project save/reopen**, not 3D generation.
5. When Windows warns about an unsigned download, inspect the code and SHA-256 build manifest; do not assume an unsigned binary is authenticated.

No IDE, system-wide Python installation, MPFB install or AI checkpoint is needed to **launch this alpha UI**. Actual character creation, Blender morph binding and all 3D engine exports still require integration work. For source development, continue using `py -3 -m ucc.desktop` with the optional Python dependencies.

## Source and asset protections

This artifact bundles only open dependency runtime libraries and UCC source code. It intentionally excludes Fab files, model checkpoints, purchased music/animation data, personal project directories, MPFB, Blender, and proprietary reference art. It does **not** automatically scan the computer or contact cloud AI providers.

Qt/PySide6 and Pillow have their own license requirements; the final redistributable installer must include a fully reviewed third-party notice and corresponding license terms. Do not publish this archive as a general release or sell it before deciding the project's distribution license and confirming bundled dependency obligations.

## Verification limitations

- CI Windows 11-compatible hosts exercise Qt widgets with `QT_QPA_PLATFORM=offscreen`, not GPU viewport rendering or user screen DPI.
- The application can create, save and edit **metadata** about characters, inspect user-chosen animation files, maintain a private catalog, and pack existing PNG sprites. It does not yet manufacture real human meshes, retarget animations or certify Godot, Unity or Unreal imports.
- The workflow's frozen executable tests only an ephemeral empty project in a temporary directory and never reads the user's projects.
- Artifact retention is seven days; this is a development build, not a stable public download.
