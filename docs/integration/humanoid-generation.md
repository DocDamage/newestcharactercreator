# Create a real MPFB humanoid in the UCC desktop — v0.2 alpha

**Source branch:** [PR #25](https://github.com/DocDamage/newestcharactercreator/pull/25). **Status:** the genuine Linux Blender-to-project integration passed in [run #43086427807](https://github.com/DocDamage/newestcharactercreator/actions/runs/43086427807). The owner's Windows Blender/MPFB installation is still not verified.

This adds the first end-to-end desktop project flow from an actual Blender-generated mesh. It is **not** an animated character editor, a morph-binding system, a licensed Fab retargeter or a certified Godot/Unity/Unreal export adapter.

## How to use on Windows

1. Open a new or existing UCC project in the desktop and **save any metadata edits** first.
2. In the **Character** tab select **Generate real MPFB humanoid...**.
3. Review the limitations and confirm the operation.
4. Select the actual Blender executable **you installed**. The official MPFB Blender extension must already be installed **and enabled** in that Blender 5.3 installation. This application does not discover, download, install or automatically enable Blender/MPFB.
5. During generation, the editor locks project editing to prevent stale in-memory changes. **Character → Cancel current humanoid generation** requests termination of the Blender subprocess tree; the window remains open while it stops.
6. If both Blender worker operations succeed, UCC displays the created vertex count, independently reopened bone count, committed revision and SHA-256. **Open saved master in Blender...** becomes available for visual examination.

The process is: worker `create_human` → Blender writes `generated_human.blend` → second worker `inspect_character` reopens a byte-identical copy in a different Blender process → validate meshes/bones/version → stage immutable `.blend` revision → revision-checked, atomic `project.ucc.json` pointer update → desktop reopens the saved project.

**The MPFB default humanoid is not affected by the current height/muscle/weight UI sliders.** Those controls are draft project metadata, not actual MPFB morph operations. The saved master is always labeled `generated_unverified`, because structural reopen checks do not establish mesh deformation, skin weights, animation retargeting, or engine import.

## On-disk safety and expected disk use

- `master/versions/<sha256>.blend`: immutable content-addressed master. Earlier versions are retained if generating again. Never overwrite an existing master revision.
- `project.ucc.json`: authoritative pointer written atomically after both Blender workers pass; current project ID and disk revision must still match the snapshot taken before generation.
- `history/`: previous project metadata backups.
- `.ucc-jobs/<uuid>/`: **private project-local** worker request, result, stdout/stderr and staged Blender masters for diagnosing success/failure. These logs and binary masters are **not** committed to this public repository or uploaded through CI; they can take disk space and may contain user paths. Review locally before deleting old completed job folders.

No automatic scanning of AI models, Fab libraries or disks is performed. The tool never makes a cloud call to create a humanoid. The user explicitly chooses the local executable each time.

## Fail-closed behavior

| Failure | Behavior |
| --- | --- |
| Missing Blender/MPFB or incompatible extension | Real worker raises error; no master pointer commit |
| Missing generated `.blend`, symlink, invalid header, small file | Reject before promotion |
| Saved master differs from file inspected by independent Blender process | Reject on SHA-256 mismatch |
| Insufficient MPFB-generated geometry or armature, lost vertices/bones, mismatched Blender version | Reject, preserve previous project |
| Another editor changes project revision or project identity during generation | Optimistic-conflict rejection; new output is left in private jobs area but not made authoritative |
| User requests cancellation | Worker kills subprocess tree when possible; checks cancellation before staging and just before metadata commit. If already committed, the completed revision remains valid |
| Disk save error or unexpectedly missing worker bridge | Fail and preserve authoritative old metadata; a recoverable unreferenced content-addressed file may remain |
| Frozen EXE missing bundled `blender_bridge` | Self-test fails; no imaginary generation functionality |

## Evidence and remaining gates

- [PR #24 Linux smoke](https://github.com/DocDamage/newestcharactercreator/actions/runs/43083744705) established real default MPFB creation, rig and independent saved-file reopen on Linux, **not Windows**.
- [PR #25 Linux integration run #43086427807](https://github.com/DocDamage/newestcharactercreator/actions/runs/43086427807) **passed** the actual `ci/verify_project_generation.py` path: creation of 19,158-vertex humanoid, 163 reopened bones, 6,571,540-byte uncompressed master, revision-checked UCC commit and saved project reopen. It remains `generated_unverified`; no windows, deformation, animation or engine import proof.
- Packaging includes only the first-party Blender bridge source, not Blender, MPFB, licensed Fab assets, checkpoints or rendered models. The unsigned Windows alpha needs an installed Blender+MPFB before generation can run.
- Still outstanding: actual Windows creation/inspection, manual appearance/skin deformation review, binding slider values to MPFB morphs, rigged GLB export/animated 3D viewport, and actual engine re-import.

**Next development task after Windows generation is proven:** bind and test real MPFB morph target operations on a copy of the verified saved master; do not fake mesh changes through project metadata.
