# Saved rig static deformation diagnostic — development PR #29

This increment adds **Test saved rig deformation in Blender...** to UCC's Character tab. It checks whether moving one real weighted deform bone changes the **evaluated mesh coordinates** of the saved humanoid.

It is a non-destructive diagnostic, not animation playback, retargeting, a skinning-quality score, an exported pose, or game-engine certification.

## Use on Windows

1. Open a character project that already references an immutable Blender master under master/versions/(sha256).blend.
2. Save any pending metadata changes first. A rig test always refers to the saved project revision, not unsaved slider positions.
3. Select **Test saved rig deformation in Blender...** on the Character tab. Select your installed Blender executable when prompted. The choice is only remembered in the current application session.
4. UCC checks the original master content hash and opens **two** separate Blender background subprocesses. Each receives its **own private copy** of the same saved .blend, never the authoritative file as an output.
5. Each process opens the copy with Blender's --disable-autoexec option, finds the human and attached armature, checks actual vertex groups, bone identities, and armature modifier links, and chooses a non-root deform bone with a substantial number of weighted vertices.
6. Blender temporarily rotates one eligible bone by **20 degrees**, compares evaluated mesh coordinates before/after, and restores the exact pose basis. At least 16 vertices must move and the real mesh fingerprint must change. The restored fingerprint must match the pre-test fingerprint.
7. The two independent Blender reports must match the selected bone, axis, vertex counts, evaluated geometry hashes, rest-pose hash and skin-weight hash. UCC rechecks saved project identity/revision and the original master SHA-256 before presenting the measurements.

The output displays the bone name, moved vertex count, maximum movement (in Blender object-local units), and source SHA. No .blend file is saved by the diagnostic and no project revision is created.

## Failure and security behavior

- Missing/redirected master, incorrect SHA, stale project revision, invalid Blender binary or worker path: fail before running Blender.
- Missing rig modifier or significant bone weights: fail, not a pretend pose.
- Non-finite evaluated vertices, mismatched topology, no meaningful pose response, incorrect pose restoration, mismatched worker reports: fail.
- Cancellation signals the worker and discards unfinished evidence.
- Another editor changes the project during testing: refuse to display stale measurements; never rewrite the project.
- No user-selected bone script, arbitrary rotation angle, downloaded model, downloaded extension, Fab asset scanning, or cloud API is used.
- Blender temporary workspaces and local diagnostics stay under .ucc-jobs/(uuid) and are ignored by Git. CI uploads JSON summaries only.

**Limit:** A mesh moving from one temporary bone rotation establishes **one static skinning response**. It does not demonstrate animated clips over time, proper shoulder/elbow deformation, visual appearance under rotation, preserved volume, IK, ragdoll, game-engine playback, or animation retargeting. The project geometry state remains generated_unverified.

## Related fix: the static GLB must show actual active MPFB morphs

Earlier static previews disabled glTF morph export but could then display the original Basis geometry after TargetService.reapply_macro_details(). The exporter now bakes the **evaluated mesh** into temporary unrigged in-memory objects before producing the private static GLB. The source .blend is untouched, and the result is still untextured, unanimated and uncertified for engine imports. UCC's static GLB coordinator refuses workers that do not explicitly report this evaluated-geometry bake.

This also repairs the previously merged PR #28 Blender integration failure that detected an unchanged static GLB despite a changed MPFB evaluated mesh. [Real Linux Blender integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) **passed** the refitted-body GLB comparison with actual evaluated-mesh baking; the defect is fixed in the proposed PR #29 branch.

## Observed integration result — November 11, 2026

The [real Blender/MPFB smoke #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) **passed** the generated-body, existing-rig refit, evaluated-shape GLB bake and two independent transient pose jobs. A weighted head-bone 20-degree rotation moved **4,451 evaluated vertices**; maximum displacement was approximately **0.05496 Blender object-local units**. The posed vertex fingerprint differed from baseline and matched baseline again after the pose was restored. The two Blender subprocesses reported the same bone, hashes and vertex counts. The refitted master retained the 163-bone armature and the original master was not modified. The static GLB reader parsed 26,756 source triangles with 1,912 drawn samples.

The [core matrix #43101713380](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713380), [Qt matrix #43101713184](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713184), [preflight #43101713174](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713174), and [Windows frozen alpha build #43101713379](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713379) also passed at the prior tested commit. Final CI must be checked again after documentation changes.

No result establishes working Windows Blender, animated clip playback or an imported engine character. Only JSON diagnostic summaries were uploaded.

## Required verification

The Python contract tests use synthetic stubs *only* to check failures and boundaries; they are not real Blender evidence. GitHub's Linux Blender 5.3 + official MPFB integration must:

- Generate a real humanoid, apply/reopen its saved body controls, and refit its existing skeleton without losing weights.
- Read a shape-baked static GLB and verify the old and refitted meshes actually differ, with no mutation of the original master.
- Run the real transient pose diagnostic in two separate Blender worker processes on the refitted master, with measurable mesh movement and identical evidence.
- Verify that the saved project and source master hash remain unchanged.

Desktop Qt offscreen, Python core, preflight and frozen Windows startup checks remain separate. The owner's **actual Windows Blender/MPFB rig deformation** and real Godot/Unity/Unreal animation playback must still be tested locally.

**Next task:** once this real pose test passes, test actual animation clips on the saved rig with frame-by-frame geometry comparisons and explicit source license/provenance checks. Do not describe the static probe as a working animation system.
