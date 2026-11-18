# Unreal native registered animation observer

This editor-only adapter uses the legacy FBX import path of Unreal 5.9.0 build 60351404 on Windows. Build it inside an owned probe project with the installed Unreal toolchain. Enable the installed Cascade and ACLPlugin modules to satisfy the editor renderer settings and default curve compression. Use the legacy FBX importer for this project. Keep the observation plugin out of delivered projects.

Run the commandlet with an empty owned output folder and an empty probe project for import. Quote each absolute path when invoking from a shell.

- Import uses -run=UccNativeAnimation -UccPhase=Stage -UccFbx=<absolute FBX> -UccOutput=<empty absolute folder>. It writes three saved native assets under /Game/UccAnimation and import.json with their object paths. The AnimSequence stores its own Unreal least-destructive bone codec with frame stripping disabled.
- Reopen starts a separate editor process on a fresh owned copy of those exact assets. Use -run=UccNativeAnimation -UccPhase=Verify -UccOutput=<empty absolute folder>. Verify reads saved assets without importing or saving them. Compare their bytes before and after in the caller.

The observation requires 301 native keys spanning ten seconds at 30 Hz. It checks the terminal data-model pose against the initial pose and samples the first 300 keys through the saved SingleNode skeletal animation. It separately ticks an engine preview world across the loop.

- bind.json gives the LOD0 native vertex positions, the ordered bone names and rest matrices, their parent indices, and the indices actually used by nonzero native skin weights.
- pose_world.f32 gives 300 frames of bone matrices in bind order. Matrices are row-major with column-vector convention. Translation is in Unreal world centimeters.
- raw_skin_world.f32 gives 300 frames of XYZ CPU skin positions in the same native LOD0 vertex order and centimeter basis.
- observation.json records the saved object identities, clock, codec and seven preview-world tick poses as an input to independent admission.

The host must check the exact source, bone hierarchy and mesh correspondence against an independent oracle. For the original nonshipping control, Unreal positions correspond to Blender meters through (x, y, z) → (-100y, -100x, 100z). The verified serializer retained a constant UccAnimationBasis parent with no skin influence and used FBX unit metadata. The observation does not attest to rendered GPU output, interactive PIE, cooked builds, appearance approval or distribution.
