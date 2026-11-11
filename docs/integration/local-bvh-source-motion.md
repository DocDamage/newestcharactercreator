# Local BVH source-motion probe — PR #31

This is UCC's first **explicitly user-selected external animation file** that can be evaluated against an actual saved MPFB humanoid in Blender. It is deliberately a **limited local direct-name rotation test**, not general BVH/FBX retargeting, permission verification, rendered animation playback inside UCC, or an exported game animation.

## Workflow on Windows

1. Open or generate a real saved MPFB humanoid project and **save any metadata edits**. An existing immutable Blender master is required.
2. Open **Animation library**, select a local **.bvh** motion file and enter its actual Provider, License name, and Source/License URI. BVH is the only executable source format for this increment. FBX, glTF, .uasset and UE-only content must wait for compatible licensed adapters.
3. Read that file's specific license outside UCC. Check the explicit option **I reviewed the actual license and confirm this BVH may be used locally in Blender (not UE-only); no AI/cloud or export**. This is the user's **attestation**, not a legal opinion or an automatic Fab license grant. Changing the source/provider/license/URI clears this consent.
4. Click **Test selected BVH motion on saved MPFB rig...** and choose your installed Blender executable. The app neither discovers nor installs other software.
5. UCC's strict, offline BVH metadata parser verifies all declared motion frames and channels; this first preview accepts 5–240 frames and requires a 64 MiB or smaller regular file.
6. Two separate isolated Blender worker processes get private, SHA-checked copies of the same saved master and chosen BVH. The worker parses motion rotations, locates **one real weighted MPFB deform bone** with an exactly matching name (case-insensitive) and uses **relative rotation deltas** from the BVH starting frame. Source bone names, bone roll and rest-space rotations must not be guessed or automatically aliased.
7. Blender creates a **temporary Action** from all source frames on that existing bone, then evaluates the actual skinned human at five frames. UCC requires real changed evaluated-geometry hashes, at least two substantially moved frames and agreement between two independent Blender processes.
8. The UI displays the source name/hash, direct source-to-target bone name, evaluated frame counts, moved vertices and local displacement. The Action is deleted in memory; the source BVH, original saved master and project JSON are **never overwritten**.

## Compatibility limits

- This v0 supports rotation channels where all X/Y/Z rotations are defined, a real matching weighted deform bone, safe relative rotation differences within 1–45 degrees, and no attempted root translation. Most full-body Fab/Mixamo/UE/Fbx clips will **not** be previewable as-is. Missing names, incompatible bone bases or heavy rotations **fail**, rather than silently producing an inaccurate motion.
- Direct-name relative rotation deltas are not orientation-corrected **retargeting**. Even if Blender moves vertices, the direction/position may be anatomically incorrect. BVH source translations, multiple-bone remapping and complex locomotion are intentionally not supported in this first vertical slice.
- **No cloud, AI inference, generation-model training, clipboard upload, Fab download or source redistribution.** Local Blender work is not AI input. The app blocks UE-only source previews in its license policy and does not grant engine export rights.
- The explicit rights review is a **user statement**. UCC cannot independently verify Fab/Marketplace license contracts. All engine exports and redistribution remain blocked until independently reviewed and validated.
- The original source stays at its selected path, is SHA-256 verified before and after jobs, and is copied to private .ucc-jobs folders that remain excluded from Git. No third-party animation file or generated model is uploaded by CI.
- Actual Windows Blender/MPFB compatibility and high-quality retargeting remain unverified until run on the user's PC. The saved project geometry state is still generated_unverified.

## Acceptance

Synthetic tests under tests/ verify strict BVH rotation parsing, rejected unsupported source data, license checks, and authoritative file preservation. They **do not** prove Blender animation processing.

The real Linux Blender 5.3 + official MPFB integration test creates its **own original 25-frame BVH at runtime**, named head, with a small safe rotating motion. It proves that this real BVH drives the saved MPFB head bone's weighted mesh in Blender, that frame hashes vary, both workers agree, and the original source/master/project bytes remain unchanged. This CI-only original BVH is not shipped or represented as any user's purchased Fab clip.

After this test passes, the next development gate is licensed, user-provided realistic **multiple-bone** motion import with explicit source-to-target rest-space calibration and visual quality review, then animation playback within the UCC viewport and game-engine import.
