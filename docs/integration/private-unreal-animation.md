# Private Unreal animation export

This profile uses the installed Unreal 5.9.0 build 60351404, MSVC 14.44.35227 and Windows SDK 10.0.26100.0 on Windows. It prepares one original registered MPFB loop with 300 samples at 30 Hz, plus the endpoint needed by the native Unreal clip.

The Blender workers retain original world pose and geometry references in their private job directories. Unreal stages the FBX, verifies the native mesh and clip in a fresh process, then saves a preview scene. The preview actor evaluates the current native skin, applies the six stored corrective topology operands, and submits the corrected surface and normals. The renderer receives topology and correspondence data. The independent Blender playback references stay on the host.

Publication requires a fresh project to reopen in real Direct3D 12 Play in Editor, sample every corrected pose, cross the native loop seam and show a change in the lit raster. The host checks sampled positions and normals against Blender with limits of 10 µm and 0.1°. The export contains the scene, native mesh, skeleton, animation and first-party preview plugin. The development observer and private evidence stay in local job folders.

The desktop command **File → Export private animated Unreal project…** takes the exact Unreal authorization for the saved animation, the installed Blender and Unreal executables and a new destination. The equivalent CLI accepts absolute paths.

```powershell
py -3.12 -m ucc.cli export-unreal-animation $project --authorization $authority `
  --database $catalog --blender $blender --unreal $unreal --unreal-sha256 $unrealSha `
  --destination $newPrivateFolder
```

The private output opens as `AnimatedCharacter.uproject` in the pinned editor. Open **CharacterScene** and select **Play** if needed. The profile covers editor playback with a neutral preview material. Player build acceptance, appearance approval and redistribution are separate.
