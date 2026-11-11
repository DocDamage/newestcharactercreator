# UCC-P1-ANIM-001 — Keyframed Blender timeline verification

**Development PR #30** extends the real rig pose test from one temporary rotation to a genuine short Blender **Action** with keyframes and interpolated timeline evaluation.

This is a diagnostic motion created by UCC during a controlled test. It is NOT a user animation clip, an imported Fab/Mixamo/BVH/FBX asset, a retargeting pipeline, a usable game animation or animated viewport playback.

## Using the new action

1. Open a UCC project with a saved, content-addressed MPFB humanoid master. Save any metadata changes.
2. Select **Validate one-second Blender keyframe timeline...** in the Character tab.
3. If prompted, explicitly select the already-installed Blender executable. The app does not install Blender, MPFB, animations or assets.
4. Two isolated Blender processes receive byte-identical **private** copies of the saved master.
5. Each process checks for an existing weighted, non-root deform bone. It chooses a safe real bone/axis using the previously validated transient pose test, then creates three actual Blender keyframes on the rig at frames **1, 13 and 25** (24 frames per second). Existing saved rig Actions and NLA tracks are not replaced.
6. Blender evaluates the timeline at frames **1, 7, 13, 19 and 25** using scene.frame_set(), with no manual bone changes between samples.
7. UCC checks that the peak and intermediate frames move actual skinned mesh vertices, the neutral first and last frames match, and **two independent worker processes agree** on the bone, frame hashes and movement counts.
8. After validation, the temporary Action is removed in memory, the original pose and scene timing restored, and the worker exits without saving a Blender master. The result is displayed as **local JSON diagnostics**, not promoted to the project.

The project version, saved master SHA-256, and local/worker copied master bytes are checked before and after the test. Failed Blender work, cancellation, changed projects, symlink redirection, missing or incompatible rig weights and insufficient/interpolated motion fail closed.

## What passing proves

A real Blender Action was inserted and evaluated, and a real existing bound humanoid mesh changed across intermediate and peak timeline frames in a reproducible way. This extends the previous single-pose skin test to **time-based keyframe interpolation**.

It does **not** prove correct joint bending, cloth collision, retargeting, movement capture, animation clip playback in UCC, user-selected assets or import/playback in Godot, Unity or Unreal.

The original saved master and project geometry state remain untouched and **generated_unverified**. Do not describe this diagnostic as a shippable animation pack.

## Observed real Blender evidence — November 11, 2026

[Real Blender 5.3 + official MPFB integration #43105088396](https://github.com/DocDamage/newestcharactercreator/actions/runs/43105088396) **passed** the original diagnostic Action with three keyframes. Blender evaluated frames 1, 7, 13, 19 and 25. The real weighted head bone moved **4,451 evaluated mesh vertices** at frames 7, 13 and 19; the first and final frame fingerprints were identical. The intermediate geometry hashes differed from both baseline and peak, demonstrating interpolated frame sampling rather than a manually applied one-off pose. Two independent Blender processes agreed on the exact bone, frame hashes and moved-vertex counts. The source .blend and UCC metadata were unchanged.

The core/preflight and desktop Qt tests also passed on that PR revision; the Windows frozen startup test is separate. This evidence is **for a diagnostic original motion only**, not a user-selected clip, visual playback quality, retargeting or engine import.

## Acceptance gates

- Synthetic contract tests for the fixed worker operation, no arbitrary script/angle/clip options, frame/sample validation, Action guards and restoration, cancellation, stale metadata, and worker disagreement.
- Real Linux Blender 5.3 plus official installed MPFB extension creates/refits the existing human, passes its immutable-master/skin pose checks, then executes the new 5-frame timeline test **twice in separate Blender subprocesses**.
- The actual CI integration outputs only JSON counts, frame numbers and hashes; no character/model/master or generated Action is uploaded to GitHub.
- Windows CI checks the frozen desktop launcher and bundled first-party Blender worker files. This **does not** verify Blender/MPFB on the owner's actual Windows PC.

**Next milestone after CI succeeds:** implement a permission-aware, user-selected animation source intake for **one** real clip and a specific source-to-MPFB bone mapping, validate actual animation playback and skinning on the saved rig, and only then work toward full retargeting and engine import.
