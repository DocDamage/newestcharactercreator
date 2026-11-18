# Private Unity animation development

This Milestone 1 profile prepares one registered MPFB body action for Unity 6000.4.5f1. It uses a Generic Animator to preserve the existing deformation skeleton and the 30 Hz source clock. The admitted Blender profile has 13,380 visible vertices, 163 bones, 300 source samples and one virtual FBX endpoint matching the opening pose. Only the material-unassigned profile is in scope here.

`ucc.jobs.unity_animation_source.prepare_unity_animation_source` takes the saved project and an exact Unity permission record. The first Blender process stages a binary FBX, complete bind data, source weights, corrective operands and the original raw and corrected surface samples. The second process reopens the registered Blender source, independently samples it, and reimports the FBX to compare the take, skeleton hierarchy and world transforms. Both jobs run in private working folders.

`ucc.jobs.unity_animation_engine.verify_unity_native_animation` takes those independently verified source files, the pinned local Unity executable and a guard for the saved project and permission context. Its first Unity process imports the FBX, binds the original weights and saves a native animation scene. The second opens a copy of the saved project with no Library cache, observes normal Animator advancement and wrap, and captures all fixed-clock raw skin and bone samples. The host compares those observations against the fresh Blender reference. It requires every Blender vertex to be mapped, verifies bone names and hierarchy and accounts for FBX's local rest-axis conversion. The Blender reference arrays stay outside the Unity project.

The Unity work folder contains the exact commands, editor logs, native bind observation and fresh playback observation. A raw-admission receipt is written only after comparison completes.

`stage_unity_animation_correction` makes a separate project copy and attaches the live Direct3D 11 pass. It uses the original quad topology, the saved Unity mesh fingerprint and the six operands independently recomputed in Blender. The pass corrects positions from Unity's current native skin, then reconstructs normals and draws from the same corrected buffer. The material-unassigned profile uses a neutral preview material.

`verify_unity_corrected_animation` requires a fresh import with ordinary Animator wrap, lit raster variation and fresh current-camera draw evidence at each of 300 fixed-clock samples. The host compares corrected positions and normals against Blender at every native vertex, including duplicate vertices at render seams. The limits are 10 micrometers and 0.1 degrees. Native evidence remains in the local work folder. This verification and an atomic private publication are separate requirements for the complete export.

Run the focused source, numeric and worker-packaging tests from the repository root on Windows.

```powershell
$env:PYTHONPATH = 'src;tests;.'
py -3.12 -m unittest test_unity_animation_authorization test_unity_animation_source test_unity_animation_evidence test_unity_corrected_animation_evidence test_worker_dispatch_contract test_worker_payload
```

Keep native evidence, character sources and permissions on the local machine. The installed editor is selected and pinned by hash for verification.

From the desktop, open the saved MPFB project and choose **File → Export private animated Unity project…**. Select its Unity authorization, the installed Blender and Unity editors, and a new export folder. The desktop verifies the published files before reporting completion.

The same export is available from the CLI with absolute paths.

```powershell
py -3.12 -m ucc.cli export-unity-animation $project --authorization $authority `
  --database $catalog --blender $blender --unity $unity --unity-sha256 $unitySha `
  --destination $newPrivateFolder
```

The destination is created only after cache-free playback verification. Open the exported folder in Unity, then open `Assets/UCC/AnimatedCharacter.unity` and press Play.
