# Preview a saved Blender humanoid in UCC — static GLB v1

**Increment:** [PR #26](https://github.com/DocDamage/newestcharactercreator/pull/26), built on merged PR #25. This is a **genuine geometric preview** of a saved project's Blender master, not animated skinning, MPFB morphing, part selection, or game-engine export validation.

## What it does

Once a UCC project has a generated, content-addressed master:

1. Open the saved UCC project and save any pending metadata edits.
2. In the Character tab click **Preview saved master in UCC...**, or choose **View → Preview current saved Blender master...**.
3. If Blender was not already chosen during this app session, select **your installed Blender executable**. There is no disk scan, automatic installation, hidden model discovery or cloud upload.
4. UCC hashes and validates the immutable `master/versions/<sha256>.blend`. A private `.ucc-jobs/<uuid>/candidate.blend` copy is made through the existing versioned Blender worker protocol.
5. An isolated Blender subprocess opens the copy with `--disable-autoexec`, exports a **temporary, geometry-only** `preview.glb`, and exits without saving the source master.
6. UCC uses its existing bounded glTF 2.0 reader to validate real embedded triangles and displays a static CPU-rendered 3D preview. Left-drag orbits, right-drag pans, the mouse wheel zooms, and Reset recenters the camera.

The temporary GLB is **private and local** inside `.ucc-jobs/<uuid>/`. It is not published, committed, used as an engine export, or made authoritative. UCC project JSON and the source `.blend` remain unchanged. The preview is discarded if another editor changes the selected project revision or its saved master.

## Explicit output restrictions

The Blender adapter exports only substantial mesh objects (more than 100 vertices each), excluding the startup cube. It disables materials, image textures, UV coordinates, animation, skins, morph export, lights and cameras. The output is **untextured static triangle geometry only**; it cannot demonstrate deformed bone weights, animation frames or face expressions. The viewer samples at most 2,000 faces and announces the number of source faces and any downgrade/warnings.

**Safety checks:** fixed allowlisted `export_preview_glb` worker command, no arbitrary user Python/workflow, no external GLB buffers, at most 128 MiB output, at most 250,000 selected mesh vertices, strict accessors/transforms and finite coordinates, no symlinks or path traversal, SHA-256 recheck of original and worker-staged masters, explicit cancellation and stale project detection. Original `.blend` revisions are never rewritten.

## Failure cases

| Failure | Behavior |
| --- | --- |
| No generated master | Action disabled; create a real humanoid first |
| Unsaved metadata | Save before preview, avoiding stale revision ownership |
| Missing/incompatible Blender or glTF exporter | Worker error; prior master and project remain untouched |
| Tampered content-addressed master / redirected symlink | Reject before launching Blender |
| Oversized mesh, failed GLB export, unsupported accessor | Reject preview; retain local diagnostic logs |
| Another editor changes project or master during conversion | Refuse to display stale preview |
| Cancellation | Stop Blender subprocess and leave project unchanged |
| Switch to a different project | Clear prior preview so it cannot be mistaken for the current character |

## Verification and boundaries

- Unit tests in `tests/test_preview_export.py`, `test_master_preview.py`, `test_jobs.py`, and Qt preview tests cover the protocol, source integrity, fixed export settings, cancellation, project switching and rendering. Synthetic fixtures are **not** MPFB proof.
- `ci/verify_project_generation.py` tests actual Blender 5.3 and installed MPFB on Linux: generate + save + independently inspect, reload the UCC project, open its saved master in a new Blender worker for a real GLB export, parse actual triangles, and confirm that no extra project revision or master mutation occurred.
- A Linux integration pass **does not** prove Windows compatibility, photo-realistic materials, correct bone deformation, animation, editable mesh parts or successful reimport into Godot/Unity/Unreal.
- The Windows portable alpha already bundles UCC's `blender_bridge` directory. The new preview source is checked by the frozen-executable self-test, but a real preview still requires the owner's installed Blender.

**Next gate:** verify actual Windows Blender/MPFB generation and preview, then test physical MPFB morph changes and real skin-weight deformation on staged copies before claiming an editable animated character.
