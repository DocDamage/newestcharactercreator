# BVH rotation-axis calibration against MPFB rest-bone matrices — PR #33

**UCC-P1-ANIM-004, first implementation slice.** [Full acceptance contract](../acceptance/UCC-P1-ANIM-004.md).

This operation verifies source-BVH XYZ rotation deltas after conversion to **real MPFB local rest-bone axes**, using two or more independent, corresponding anatomical rest directions. It is not automatic full-body retargeting, a licensed animation exporter, or a real-time UCC viewport.

## User steps

1. Open a saved, generated MPFB humanoid in UCC and save pending metadata edits.
2. In **Animation library**, choose one explicitly selected local BVH file and enter its actual provider, source URI and reviewed source-specific license. Confirm that the file may be previewed in Blender (not UE-only). The approval is **user-attested**, not a guarantee from Fab.
3. Explicitly choose the source up-axis preset: BVH Y-up → Blender Z-up or BVH Z-up identity.
4. Choose **Calibrate BVH rest axes and test 2–4 bone motion...**. Point UCC to its already-installed Blender executable.
5. For each of two independent, SHA-identical private worker copies, Blender checks exact names and parent links for **2–4 connected and weighted deform bones** and a known XYZ BVH rotation channel order. It reads BVH joint offsets plus a terminal **End Site** rest direction. Every landmark is compared with the actual MPFB armature's head/head or head/tail rest vectors.
6. At least two anatomical rest directions must be separated by 10° in both source and destination. The solver establishes an orthonormal, positive-determinant global source-to-target rest rotation and checks that every landmark residual is **≤5°**.
7. Each target bone's actual `matrix_local` is independently read. Because MPFB can contain tiny numerical scale noise in that 3×3 rotation, the worker **measures** its determinant and projects it onto SO(3) **only if near-valid** (raw determinant within 0.001 of +1, bounded maximum correction ≤0.0005). Reflections, large shears and incompatible orientation fail. The **corrected rotation** must still pass the strict determinant and orthogonality error ≤1e-5.
8. Actual BVH source rotations are composed in declared XYZ channel order; the relative frame rotation is `R_delta = R_start^-1 @ R_frame`, not a subtraction of Euler angles. For each MPFB target rest frame `M_i` and solved source-to-target world orientation `R_s2t`, the local conversion is `C_i = M_i^-1 @ R_s2t`. The target pose rotation is `C_i @ R_delta @ C_i^-1` and Blender receives its quaternion.
9. Blender separately tests each mapped bone's real skinned movement, then inserts a **temporary quaternion Action** for the original BVH's motion and measures five evaluated mesh frames. Two independent workers must match all hashes, landmark residuals, bone matrices and actual motion.
10. The Action is not committed, the BVH is not rewritten, the saved `.blend` is immutable and `project.ucc.json` is unchanged. The resulting panel shows measured joint/vertex counts and warns that **full retargeting and real animation quality are still unverified**.

## Explicitly unsupported

- BVH skeletons without a terminal End Site or independent rest-orientation evidence.
- Arbitrary source/target mappings, Mixamo/Unreal aliases, pose-space remapping of whole bodies, other Euler channel orders, root motion, scale changes, IK, or FBX/.uasset import.
- A BVH with more than four mapped joints, unsupported user authorization, invalid/mismatched anatomy, degenerate vectors or target rest matrices outside numeric correction cap.
- Claims that bone-roll consistency has been independently confirmed for purchased external skeletons, that the UCC viewport plays imported motion, or that Godot/Unity/Unreal accepts this character.
- Using a Fab asset whose actual license does not permit local Blender use. UCC is not an automated legal license reviewer and does not upload the source to any cloud or AI provider.

## CI proof and status

The [real Blender/MPFB integration run #43132955795](https://github.com/DocDamage/newestcharactercreator/actions/runs/43132955795) **PASSED** the first genuine calibrated two-bone fixture:

- Blender 5.3.0 + official MPFB, original self-authored 25-frame source BVH, actual `neck03 → head` target chain.
- **2 anatomical rest landmarks**, largest residual **2.9700°** (threshold 5°).
- MPFB rest-frame numerical correction max **0.00001446** (threshold 0.0005), then strict proper SO(3) validation.
- Both bones independently moved **4,451 real evaluated weighted mesh vertices**. Five frame hashes varied and returned to source baseline at the last frame.
- Two separate Blender workers agreed. BVH, original Blender master and project JSON were unchanged.
- `retargeting_verified=false`, `engine_import_verified=false`, `bone_roll_independently_verified=false` remain honest.

The [original first attempts](https://github.com/DocDamage/newestcharactercreator/pull/33) failed because actual MPFB refit rest matrix determinant was measured at 1.000014475, just outside strict 1e-5. The bounded numeric projection fixes this; **it does not relax strict output rotation validation**. The final branch CI matrix must still be checked on the latest commit before merge.

## Next development step

After all acceptance gates pass and this PR is merged, test an owner-supplied, explicitly permitted multi-bone BVH with known rest orientation/roll references; compare real visual deformation over a clip, add reviewed/manual source-to-MPFB mapping and only then consider true `retargeting_verified` status or engine export. Do not claim general Mixamo/Fab retargeting based on this CI-only anatomical fixture.
