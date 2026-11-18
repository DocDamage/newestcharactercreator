# Private Unity animation development

This Milestone 1 profile prepares one registered MPFB body action for Unity 6000.4.5f1. It uses a Generic Animator to preserve the existing deformation skeleton and the 30 Hz source clock. The admitted Blender profile has 13,380 visible vertices, 163 bones, 300 source samples and one virtual FBX endpoint matching the opening pose. Only the material-unassigned profile is in scope here.

`ucc.jobs.unity_animation_source.prepare_unity_animation_source` takes the saved project and an exact Unity permission record. The first Blender process stages a binary FBX, complete bind data, source weights, corrective operands and the original raw and corrected surface samples. The second process reopens the registered Blender source, independently samples it, and reimports the FBX to compare the take, skeleton hierarchy and world transforms. Both jobs run in private working folders.

`ucc.jobs.unity_animation_engine.verify_unity_native_animation` takes those independently verified source files, the pinned local Unity executable and a guard for the saved project and permission context. Its first Unity process imports the FBX, binds the original weights and saves a native animation scene. The second opens a copy of the saved project with no Library cache, observes normal Animator advancement and wrap, and captures all fixed-clock raw skin and bone samples. The host compares those observations against the fresh Blender reference. It requires every Blender vertex to be mapped, verifies bone names and hierarchy and accounts for FBX's local rest-axis conversion. The Blender reference arrays stay outside the Unity project.

The Unity work folder contains the exact commands, editor logs, native bind observation and fresh playback observation. A raw-admission receipt is written only after comparison completes. The raw admission is a development gate. Corrective GPU parity, rendered playback and atomic private publication are separate remaining gates for the complete export.

Run the focused source, numeric and worker-packaging tests from the repository root on Windows.

```powershell
$env:PYTHONPATH = 'src;tests;.'
py -3.12 -m unittest test_unity_animation_authorization test_unity_animation_source test_unity_animation_evidence test_worker_dispatch_contract test_worker_payload
```

Keep native evidence, character sources and permissions on the local machine. The installed editor is selected and pinned by hash for verification.
