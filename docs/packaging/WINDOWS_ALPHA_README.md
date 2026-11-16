# UCC Desktop — Windows alpha internal testing build

**Status:** Early, unsigned development build for the repository owner's private testing. This is **not** a finished 3D character creator, an installer, or a public release. No license to redistribute project code or source assets has been selected.

## Local native-worker packaging checkpoint — November 15, 2026

The latest private build 430 adds **File → Render animated facial sprites…**.
Save supported expression strengths first, review every source for this animated
use and choose a new output folder. The fixed 25-frame, 24 FPS sequence returns
to neutral and retains the saved material/hand. Four/eight directions at 128/256
pixels produce one 5×5 sheet per direction; both neutral endpoints are included.
Every frame must match independent original-source and saved-Action geometry,
normals and pixels before publication. Actual source tests deliver 100/200 frames;
the unmodified native standalone workflow delivers 100 at 256 pixels. All 204
UCC modules/main and 186 worker payload files match source. Regression: 1,355
passed, 14 existing skips. Real cancellation, collision and coherent faults pass.
These are private whole-character samples; facial changes can be subtle at 128
pixels. Close-ups, separated layers, lip-sync, body motion, artist/pixel-art
approval and Unity/Unreal require further work. No owner shortcut was changed.
See [animated sprite acceptance](../acceptance/UCC-P1-SPRITE-003.md).

The earlier private build 414 adds **File → Render character sprite sample…**.
Open a saved prepared human with its owned material, review every source for this
specific use, select a new destination and choose the installed Blender executable.
It renders four/eight transparent neutral directions at 128/256 pixels with
explicit yaw/pitch, then independently checks original-source and saved-scene
pixels before packing an exact atlas. Direction samples are not animation clips.
Actual unmodified Windows UI 416/418 passes four 256² views; source UI tests also
pass four 128² and eight 256² views. All 199 bundled UCC modules/main and 183 worker
payload files match current source. Regression: 1,344 passed and 14 existing skips.
No Blender, MPFB, character assets or models are bundled. Artist/pixel-art quality,
owner assets, public distribution and Unity/Unreal remain unapproved. See
[sprite acceptance](../acceptance/UCC-P1-SPRITE-002.md). The owner launcher remains
unchanged. The previous checkpoint below describes build 382 specifically.

The later private Windows build 382 includes current body/face/material controls,
material preview, frame-specific facial normals and the desktop Godot export
workflow. Actual frozen startup 383 and normal Windows UI export 384/386 pass:
fresh bundled Blender workers, actual Godot checks and saved-scene reopening.
Archive audit 385 matches all 194 UCC modules and the main entry point to source.
This remains original authored private test evidence, without public distribution
approval, animation-clip export or an owner-shortcut update.
See [current package acceptance](../acceptance/UCC-P1-PKG-002.md) for exact scope.

The private archive recorded at checkpoint 198 covers the packaging gate before
the subsequent source-corner UV extension. A frozen build of that later source
is covered only by the later private checkpoint above; it is not in archive 198
or the owner launcher.

The current local QA payload includes SHA-bound bridge scripts, pure Python
contract sources and eight Godot adapter resources. Blender loads those sources
with its own interpreter; it does not import the frozen application's Python
extension modules. Building uses a controlled DLL search path so unrelated SDK
DLLs cannot replace Qt's Windows dependencies. No Blender, MPFB, character,
animation, AI model or private runtime-kernel asset is included.

The local frozen startup check and actual external Blender saved-scene and
Godot import checks are documented in [UCC-P1-007](../acceptance/UCC-P1-007.md).
Separate actual frozen-parent diagnostics also verify the Blender runner;
these are private tests rather than a new desktop export control.
Those checks do not expose an export control, approve materials/animation quality
or grant redistribution rights. This work is not yet the owner launcher's build
or a newly accepted GitHub artifact. Keep the entire private QA folder intact.

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

## Saved MPFB body slider generation — merged PR #27

Height, Muscle and Weight values on the Character tab are **normalized MPFB phenotype controls**. Save the project, then use **Generate humanoid using saved body controls...** to create a fresh model via the installed MPFB extension. The operation does not live-edit the prior master; immutable history is preserved, and part/animation-annotated projects are blocked until compatibility is proved. The frozen executable contains the first-party worker scripts, not Blender or MPFB; the user's Windows runtime still needs testing. See [body controls](../integration/mpfb-body-controls.md).

## Existing character body refit — merged PR #28

When a saved humanoid master exists, the Character tab offers **Apply saved body controls to existing master...**. This edits a private copy through the user's installed Blender/MPFB and verifies the previous rig's bone links and skin weights before saving a new revision. Original `.blend` files are not overwritten. The portable alpha bundles the first-party `blender_bridge/refit_revision.py` script but does **not** install Blender or MPFB. The frozen startup self-test checks source presence, **not** refit behavior on your Windows PC. Read [the body refit guide](../integration/mpfb-existing-master-refit.md) before using the feature.

## Static rig pose test and corrected GLB shape preview — PR #29

The Character tab includes **Test saved rig deformation in Blender...**. After a saved master exists, this opt-in operation runs two isolated copies through the installed Blender binary, temporarily rotates one real weighted bone by 20°, measures evaluated vertex movement and verifies the pose was restored. It **never saves or overwrites the master**. [Linux Blender integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) observed 4,451 moved vertices under a head-bone test, with matching results from two independent Blender processes.

A related fix bakes active MPFB shape-key geometry into a temporary unrigged static GLB before display. It solves the real PR #28 regression where a refitted .blend contained modified shape keys but its GLB preview displayed unchanged Basis coordinates.

The Windows portable bundle includes the first-party pose helper, but **its frozen self-test does not execute installed Blender or MPFB**. The owner's Windows runtime, animation clip playback, deformation quality and game-engine imports remain unverified. [Pose test guide](../integration/rig-pose-deformation.md).

## One-second Blender keyframe test — proposed PR #30

The Character tab's **Validate one-second Blender keyframe timeline...** option creates an original, temporary three-keyframe Blender Action on a private copy of a saved MPFB humanoid, and measures actual vertex movement at five timeline frames. It does not save an Action, modify the original Blender master, copy any third-party animation, display live playback, or certify rig retargeting/engine export.

The portable application bundles its first-party timeline worker script and checks that the file is present at startup. This is not proof that installed Blender/MPFB works on the owner's Windows computer. [Full diagnostic guide](../integration/keyframed-timeline-diagnostic.md).

## Explicit user-selected local BVH motion — PR #31

In the Animation library tab, **Test selected BVH motion on saved MPFB rig...** can test one locally chosen .bvh source against the saved MPFB humanoid after the user enters their actual source provider/license/URI and confirms those rights permit local Blender preview (not UE-only). This does not automatically grant a license or upload, train on, export or redistribute any source data. It is deliberately a direct-name single-bone rotation-delta test, not complete Fab/Mixamo/UE retargeting.

The first-party offline BVH reader and worker are included in the frozen build; Blender and MPFB remain separately installed by the owner. Frozen self-tests verify file presence, not real Blender/MPFB execution on Windows. See [the local BVH guide](../integration/local-bvh-source-motion.md).

## Explicit source up-axis and 2–4 bone BVH chain test — PR #32

The Animation library tab offers **Test 2–4 bone BVH chain against saved MPFB rig...** alongside the existing single-bone test. After selecting a local file and explicitly confirming its actual reviewed Blender-use license (not UE-only), select an **explicit source up-axis profile** (BVH Y-up → Blender Z-up or Z-up identity). This version verifies real MPFB deform weights, direct source/target bone parents, rest-direction alignment and independent source-driven vertex movement for every joint in a connected chain. It does **not** solve bone roll or certify complete retargeting.

The Windows alpha bundles first-party BVH chain and evidence code; its PyInstaller self-test verifies source availability, not actual MPFB execution on the owner's Windows machine. [Details](../integration/bvh-multibone-rest-gate.md).

## Rotation-calibrated BVH rest-space test — PR #33

The Animation library tab adds **Calibrate BVH rest axes and test 2–4 bone motion...**. This requires an explicitly user-selected local BVH file, actual reviewed Blender-use license confirmation, a selected source up-axis, **two independent, corresponding rest-direction landmarks** (including terminal BVH End Site), and a saved MPFB humanoid. Real Blender computes a proper, measured source-to-target rest orientation and applies ordered BVH relative rotations through the **actual target rest-bone matrix** as quaternion keys. Uncalibratable sources fail; no original master or BVH is overwritten.

[Real Linux Blender/MPFB run #43132955795](https://github.com/DocDamage/newestcharactercreator/actions/runs/43132955795) passed this initial two-bone calibration; the Windows frozen UI self-test checks bundled sources/Qt, **not your installed Windows Blender/MPFB runtime**. User-supplied paid Fab animation quality, full retargeting and engine import remain unverified. See [calibrated BVH guide](../integration/bvh-restspace-quaternion-calibration.md).

## Source and asset protections

This artifact bundles only open dependency runtime libraries and UCC source code. It intentionally excludes Fab files, model checkpoints, purchased music/animation data, personal project directories, MPFB, Blender, and proprietary reference art. It does **not** automatically scan the computer or contact cloud AI providers.

Qt/PySide6 and Pillow have their own license requirements; the final redistributable installer must include a fully reviewed third-party notice and corresponding license terms. Do not publish this archive as a general release or sell it before deciding the project's distribution license and confirming bundled dependency obligations.

## Verification limitations

- CI Windows 11-compatible hosts exercise Qt widgets with `QT_QPA_PLATFORM=offscreen`, not GPU viewport rendering or user screen DPI.
- The application can create, save and edit **metadata** about characters, inspect user-chosen animation files, maintain a private catalog, and pack existing PNG sprites. The opt-in generation action can request a real MPFB human and save its master when Blender/MPFB are present, but has not been verified on the user's Windows PC; it cannot yet deform via sliders, retarget animations or certify Godot, Unity or Unreal imports.
- The workflow's frozen executable tests only an ephemeral empty project in a temporary directory and never reads the user's projects.
- Artifact retention is seven days; this is a development build, not a stable public download.
