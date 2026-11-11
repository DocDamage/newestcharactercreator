# Humanoid bone-name compatibility *candidate* report

**Status:** real, deterministic name matching; no bone transforms, retargeting, rendering, export, or animation playback is performed. This feature operates only on one explicitly selected **source** and **target** file and does not copy purchased animation bytes. It is safe to run before the owner downloads their Fab library, but it will need two actual user-provided files to produce a meaningful report.

## Supported profiles

- **Mixamo** — e.g. `mixamorig:Hips`, `mixamorig:LeftArm`, `mixamorig:LeftForeArm`, `mixamorig:LeftHand`, and corresponding unprefixed bones. MPFB also documents the `mixamo` built-in rig, but that does not certify equivalent rest poses.
- **UE4 mannequin** — `pelvis`, `spine_01`–`spine_03`, `clavicle_l`, `upperarm_l`, `lowerarm_l`, `hand_l`, `thigh_l`, `calf_l`, `foot_l`, `ball_l` and right-side counterparts.
- **UE5 Manny-style** — common UE naming with `spine_05` as a distinct upper chest role. UE5 twists, root-motion helpers, and IK bones are reported as unused unless incorporated into a future reviewed retargeting adapter.

The converter uses **only documented exact aliases**, not fuzzy string similarity, source/target AI embeddings, or nearest-match bone heuristics. It preserves left/right distinction. Partial rigs cannot be automatically recognized without sufficient bilateral anatomy; you may supply an explicit profile hint for inspection, but the report will still list all unmapped required roles.

**MPFB default / Rigify / dragon / quadruped and other families are not silently reclassified as UE or Mixamo.** They require named family-specific mapping profiles and real rest-pose/geometry review. Profiles are not proof of compatible rig versions.

## Command (Windows, no IDE)

With Python 3.12+ and the repository on your computer, using **your own** two inspected BVH/GLB/glTF files:

```powershell
$env:PYTHONPATH = 'src'
py -3 -m ucc.animations --source 'D:\MyAnimations\MixamoWalk.bvh' --target 'D:\MyModels\UnrealHumanoid.glb'
```

If either file has a partial skeletal description, use only the appropriate explicitly verified hints:

```powershell
py -3 -m ucc.animations --source 'D:\MyAnimations\MixamoWalk.bvh' --target 'D:\MyModels\Target.glb' --source-profile mixamo --target-profile unreal_ue5
```

The CLI reads only the specified files and calls the existing **metadata-only** `inspect_animation_file()` routine; `.fbx` and `.uasset` files remain blocked until real Blender/Unreal conversion has extracted bone metadata. It returns JSON on stdout; it does not save private paths, upload artwork, or modify the source files.

## Output interpretation

`status=NAMING_CANDIDATES_ONLY_NOT_RETARGETED`, `retargeted=false`, `preview_verified=false`, `engine_validated=false`, and `can_execute_without_manual_review=false` are invariant. Each candidate names its source and destination bone and the semantic role inferred from exact aliases, e.g. `LeftForeArm` → `lowerarm_l` (`forearm.L`). Missing required roles, unknown helper bones and strict source/target inventory hashes are reported.

A candidate map has **not** handled any of the following: source and destination bone axes, relative rest poses, scale units, root motion, yaw/pitch handedness, twist bones, IK chains, bone length ratios, animation compression, nonhuman proportions, licensing, or in-game deformation. Before marking a clip usable, import the actual licensed data into Blender, inspect the rest poses, compute transform corrections, retarget with verified constraints, preview movement visually, and validate inside the chosen engine.

## References

- MPFB official rig documentation: https://github.com/makehumancommunity/mpfb2/blob/master/docs/services/rigservice.md
- MPFB official supported rigs: https://github.com/makehumancommunity/mpfb2/blob/master/script_samples/03_adding_a_default_rig.py
- Unreal/Mixamo correspondence example: https://uhiyama-lab.com/en/notes/ue/animation-retargeting-complete-guide/

This mapping preflight contributes to [UCC-P2-001](https://github.com/DocDamage/newestcharactercreator/issues/9) but does **not** close its retargeting acceptance gate.
