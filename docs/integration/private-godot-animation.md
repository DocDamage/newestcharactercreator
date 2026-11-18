# Private Godot animation export

UCC can prepare one exact saved MPFB humanoid action for Godot 4.7.1 on
Mobile/Vulkan. The supported profile is a 300-sample action at 30 Hz on the
registered smooth, unassigned-material humanoid. Blender reopens the saved
source before Godot checks the imported rig and corrective deformation.

In the desktop, open the saved character and choose **File → Export private
animated Godot project…**. Select the local authorization for that action,
the installed executables, and a new destination. The desktop keeps the
operation cancellable while the local native checks run.

Run from the UCC checkout with the installed Blender and matching Godot console
and main executable pair. Use full local paths. The destination must be a new
folder outside the saved project and catalog.

```powershell
py -3.12 -m ucc export-godot-animation $project `
  --authorization $localAuthorization --database $catalog `
  --blender $blender --godot $godotConsole --godot-main $godot `
  --destination $newPrivateFolder
```

The local authorization is a JSON object with exactly these fields.

| Field | Value |
|---|---|
| `schema_version` | Integer `1` |
| `policy` | `UCC_PRIVATE_FIRST_PARTY_GODOT_AUTHORIZATION_V1` |
| `selection` | Exact `RegisteredInputSelection` for the saved action, including the project, master, clip, binding, source and catalog hashes |
| `permissions` | One reviewed `EngineInputPermission` per consumed source, including the original motion |
| `purpose` | Description of this private local use |
| `private_local_execution_confirmed` | Explicit owner confirmation for this local run |

Use `prepare-godot-animation` with the same inputs and without
`--destination` to verify and retain the inputs without publishing a project.
The two commands keep their actual native logs under the project's `.ucc-jobs`
folder. Errors and cancellation leave the requested destination unpublished.

After successful export, run the new folder's `project.godot` with the
selected Godot binary using `--path`. The scene plays the native 10-second
loop with first-party corrective skin and normal computation. The publication
receipt records the fresh-process render and loop checks. The exported scene,
code and data are for private local use. Additional animation profiles, authored
materials, player builds and distribution require their own verification.
