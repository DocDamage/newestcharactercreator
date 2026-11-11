# UCC Desktop — Windows alpha internal testing build

**Status:** Early, unsigned development build for the repository owner's private testing. This is **not** a finished 3D character creator, an installer, or a public release. No license to redistribute project code or source assets has been selected.

## Run without an IDE or Python installation

1. On the repository's GitHub **Actions** tab, open the most recent successful **Windows desktop alpha build (internal testing)** run.
2. Download `UCC-Desktop-Alpha-Windows-x64` under **Artifacts** and extract the ZIP twice if GitHub has wrapped the archive.
3. Keep the entire `UCC-Desktop-Alpha` folder intact; run `UCC-Desktop-Alpha.exe` inside it.
4. The optional `frozen-health.json` beside the archived build proves only that this GitHub-built application passed **real Qt widget startup and character-project save/reopen**, not 3D generation.
5. When Windows warns about an unsigned download, inspect the code and SHA-256 build manifest; do not assume an unsigned binary is authenticated.

No IDE, system-wide Python installation, MPFB install or AI checkpoint is needed to **launch this alpha UI**. Actual character generation is an opt-in feature requiring the user's installed Blender/MPFB; Windows runtime acceptance, Blender morph binding and all 3D engine exports still require validation. For source development, continue using `py -3 -m ucc.desktop` with the optional Python dependencies.

## Opt-in local Blender generation in PR #25

The desktop's Character tab now includes **Generate real MPFB humanoid...**. This feature asks for an installed Blender executable and requires MPFB to be installed/enabled **by the user**. It creates one local humanoid using Blender's genuine HumanService workflow, independently reopens it in another Blender process, and stores a content-addressed `.blend` master if both worker stages pass.

The portable archive includes the UCC-owned `blender_bridge` Python worker scripts but **does not** ship Blender, MPFB, assets or models. The frozen `--self-test` now checks worker-file presence as well as Qt and metadata. It **does not run Blender/MPFB**. Real creation has been tested on Linux CI; it still needs target-Windows verification. Live morph deformation, rig animation, export and game-engine imports remain unverified. Read [the actual generation workflow and safeguards](../integration/humanoid-generation.md) before using it.

## Read-only preview of a saved Blender master (PR #26)

The Character tab can convert an already-saved UCC `.blend` master into a temporary static GLB, displayed in the existing UCC viewer. The user must explicitly choose an installed Blender executable if one was not already selected during the current app session. No Blender binaries or third-party assets are bundled, downloaded or uploaded. The generated GLB is a private local preview only; animation, mesh deformation, textures and engine import are **not** verified. See [saved-master preview guide](../integration/saved-master-preview.md).

## Saved MPFB body slider generation — proposed PR #27

Height, Muscle and Weight values on the Character tab are **normalized MPFB phenotype controls**. Save the project, then use **Generate humanoid using saved body controls...** to create a fresh model via the installed MPFB extension. The operation does not live-edit the prior master; immutable history is preserved, and part/animation-annotated projects are blocked until compatibility is proved. The frozen executable contains the first-party worker scripts, not Blender or MPFB; the user's Windows runtime still needs testing. See [body controls](../integration/mpfb-body-controls.md).

## Source and asset protections

This artifact bundles only open dependency runtime libraries and UCC source code. It intentionally excludes Fab files, model checkpoints, purchased music/animation data, personal project directories, MPFB, Blender, and proprietary reference art. It does **not** automatically scan the computer or contact cloud AI providers.

Qt/PySide6 and Pillow have their own license requirements; the final redistributable installer must include a fully reviewed third-party notice and corresponding license terms. Do not publish this archive as a general release or sell it before deciding the project's distribution license and confirming bundled dependency obligations.

## Verification limitations

- CI Windows 11-compatible hosts exercise Qt widgets with `QT_QPA_PLATFORM=offscreen`, not GPU viewport rendering or user screen DPI.
- The application can create, save and edit **metadata** about characters, inspect user-chosen animation files, maintain a private catalog, and pack existing PNG sprites. The opt-in generation action can request a real MPFB human and save its master when Blender/MPFB are present, but has not been verified on the user's Windows PC; it cannot yet deform via sliders, retarget animations or certify Godot, Unity or Unreal imports.
- The workflow's frozen executable tests only an ephemeral empty project in a temporary directory and never reads the user's projects.
- Artifact retention is seven days; this is a development build, not a stable public download.
