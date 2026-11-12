# UCC-P1-ANIM-005 — explicit mapped BVH timeline and private Blender review

This is an **opt-in, real Blender/MPFB diagnostic** on a previously saved, content-addressed humanoid master. It extends the calibrated quaternion motion introduced in UCC-P1-ANIM-004. It does **not** certify an animation for production, automatically map a mixed rig, or enable redistribution.

## Using the existing Windows/PySide6 desktop

1. Open an existing saved MPFB humanoid project. Save metadata before starting. Select an actual regular local **BVH** file in **Animation library**. FBX, `.uasset`, GLB and Fab library URLs are not BVH imports.
2. Enter the *actual* source provider, exact license title and source URL. Confirm the **local Blender preview** permission only after reviewing the specific license; UE-only and unreviewed content is rejected. No AI input or engine-export license is inferred.
3. Choose exactly one source-axis conversion: `Y_UP_TO_Z_UP` or `Z_UP_IDENTITY`. Do not rely on automatic axis guessing.
4. In the **explicit bone pairs** editor, enter **3–8 source -> target lines**, in **parent-to-child** order, for example:
   ```text
   SourceNeck02 -> neck02
   SourceNeck03 -> neck03
   SourceHead -> head
   ```
   The left names must be the actual BVH joint names; the right names must be real, substantially weighted MPFB **deform bones**. Each member must be the direct child of the prior member on *both* sides; the BVH source selection must start at its root. This is a **mapping example**, not a universal Mixamo/Fab/Manny profile. Changing an input clears license consent.
5. Click **Review explicit 3–8 bone BVH mapping across full timeline...** and select the installed Blender executable if prompted.
6. UCC uses two independent isolated Blender subprocesses and temporary SHA-verified copies. On success, the result includes a **private local path** to `review_motion.blend` under `.ucc-jobs`. **Open that copy in Blender**, select the actual armature Action, scrub frames 1 through the BVH frame count, and manually inspect any joint twisting, hyperextension, self-intersection, unwanted child motion, range of motion, skin tearing, limb discontinuities and relative scale. No auto-upload or gallery is created.

## What is checked

- An independent bounded BVH metadata/parser preflight, explicit source/target name mapping with unique names, exact direct-parent relationships, XYZ Euler rotation channels, nontrivial motion, 5–240 frames and bounded scale.
- Shared source-to-target proper SO(3) orientation from **at least two independent anatomical rest-direction correspondences**, with target Blender bone `matrix_local` calibration, correct quaternion conjugation and ≤5° rest residual. Non-collinear anatomy is required; this does **not** independently verify bone-roll assumptions for an arbitrary purchased rig.
- Actual MPFB skin weights and individual weighted movement of each selected bone; source-driven quaternion keys across the complete BVH timeline; **every** frame's evaluated skinned vertex SHA, vertex count and displacement. Reject >80° per-frame quaternion steps, >0.8 model-diagonal adjacent displacement, and >1.5 model-diagonal deformation from frame 1.
- Separate Blender workers must agree on calibration proofs and **all** frame hashes; the private Action file is SHA-checked, then may be opened for real human inspection. Main master, original source BVH and `project.ucc.json` are SHA/revision-guarded and remain unchanged.
- Error or cancellation does **not** promote an animation into the authoritative project. This operation does not automatically save a new master, expose the original BVH to cloud tools, or export to a game engine.

## Interpretation of evidence and limitations

`REAL_REVIEWED_BVH_FULL_TIMELINE_MOTION` means only the selected explicit mapping was **measured** by Blender; its successful local test does **not** make `retargeting_verified`, `animation_visual_quality_verified`, `bone_roll_independently_verified`, `joint_twist_visual_quality_verified`, or `engine_import_verified` true. All remain **false**.

The first CI case uses a **non-shipping original BVH generated from the actual MPFB rest offsets** with differently named source joints, not a third-party motion library. It tests the plumbing, real weighted geometry and independent Action reopen, **not arbitrary Fab/Mixamo/Unreal rig compatibility**. The user's licensed assets and Blender 5.3 on their Windows machine require separate testing. The private animated `.blend` is deliberately **not an uploadable Actions artifact**.

Only a locally acquired, explicitly permitted animation clip with an accurate source skeleton, reviewed rights and enough anatomical rest information should be submitted for future real compatibility and visual review. Fab account ownership alone does not grant non-Unreal use, AI input, or redistribution rights.
