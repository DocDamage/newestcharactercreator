# UCC desktop v0.1 — functional metadata and asset workstation

This is the **first desktop UI**, implemented in PySide6. It provides real project and file operations and deliberately does **not** depict a working humanoid 3D editor or animation retargeting. No example character geometry, Fab assets, or pretrained weights are bundled.

## Setup on Windows (no IDE necessary)

Using Python 3.12 or newer, from the checked-out repository root in PowerShell:

```powershell
py -3 -m pip install -e ".[desktop,sprites]"
py -3 -m ucc.desktop
```

Or run the installed `ucc-desktop` console entry point. `PySide6` and `Pillow` are free Python dependencies; these commands install them only when **you** explicitly run them. Blender/MPFB, Unreal, Unity, Godot, Aseprite, Fab assets, and model checkpoints are **not installed** by the desktop.

## What is real today

- **File → New character:** choose a name and an **empty existing folder**; writes a versioned `project.ucc.json` through the existing atomic, conflict-aware `ProjectStore`. It rejects nonempty folders.
- **File → Open / Save metadata:** validates a real saved project, checks schema, writes backups and rejects concurrent edits rather than silently overwriting a different revision. Close/New/Open asks before discarding unsaved edits.
- **Edit → Undo/Redo:** reversible renaming, height/muscle/weight metadata, with increasing revision numbers. These values **do not physically deform MPFB meshes yet**. Sliders commit when released.
- **Create/Advanced modes:** basic metadata editing or a read-only catalog of defined body attachment slots and export blockers. They are not actionable 3D attachment widgets yet.
- **Open saved master in Blender:** only available when the project already references a real staged `.blend`. User selects installed Blender executable, with `--disable-autoexec` to prevent automatically running embedded scripts. This launches the user's own Blender, not a fake viewport.
- **Animation library:** select and inspect one BVH/GLB/glTF/FBX/uasset; index its actual metadata and source SHA in the private local SQLite catalog. GUI policy is **always unreviewed**; it cannot approve AI use, Unreal/Godot/Unity exports, or redistribution. No animation file is downloaded or uploaded.
- **Tools:** inspect a selected GLB's structure, read-only probe of local ComfyUI/Stable Diffusion WebUI, and pack existing appropriately named transparent PNG frames into actual RGBA sprite sheets. These tools run in a worker thread to keep the UI responsive. No GPU/AI generation is automatically started.

## Known limits and engineering safeguards

- No embedded 3D viewport, live character generation, real bone movement, MPFB slider binding, or licensed retargeting pipeline yet. The source-backed MPFB `HumanService` smoke and a fresh Blender reopen must run in the target installation before those are claimed.
- The desktop does **not** count named bone matches as retargeted animation, PNG atlas generation as character creation, or a valid GLB header as successful engine import. Actual Godot, Unity, and Unreal playback remains required.
- Private user project files and proprietary asset databases remain under user-selected project folders / Qt's local application-data directory; no source assets, models, scanned locations, or credentials are pushed to GitHub.
- While a disk inspection/atlas/API probe is running, the relevant tabs are disabled and closing is blocked to protect in-progress local work. Operations are bounded by the existing format checks.
- PySide6 is an **optional** dependency. Backend and CLI tests remain fully runnable without it. GitHub's new `Desktop Qt Smoke Tests` workflow uses real installed PySide6 widgets in offscreen mode on Windows and Linux. It does not exercise a GPU or a real screen, and real installer/DPI testing will still be required.

## Source entry points

- `src/ucc/desktop/controller.py`: pure-Python project lifecycle and revision handling.
- `src/ucc/desktop/window.py`: QMainWindow composition, local actions, error paths.
- `src/ucc/desktop/panes.py`: character, animation and tools panels.
- `src/ucc/desktop/background.py`: dedicated Qt QThread worker for filesystem/API tasks.
- `src/ucc/desktop/__main__.py`: launch without relying on an IDE.

## Next UI stage

After real MPFB creation/rigging passes, add a tested 3D viewport and Blender-derived model preview, bind body controls to **actual** mesh changes, and validate end-to-end saved model/animation in Godot, Unity, Unreal. Until then, this UI is a useful early workstation, not the finished Universal Character Creator.
