# Limited multi-bone BVH → MPFB rest/axis compatibility gate (PR #32)

This follows merged PR #31's verified single-bone local BVH probe. It supports **2–4 directly connected joints** from one explicitly selected, locally permission-reviewed BVH file. Every source joint must have an exactly matching, substantially weighted MPFB deform bone and a compatible parent link. The operation uses the existing saved MPFB master only through temporary copies.

This is **not full skeleton retargeting**, rest-bone orientation calibration, a license audit, interactive UCC animation playback or export to Godot, Unity or Unreal.

## Windows steps

1. Save and open an existing MPFB humanoid master in UCC.
2. On the **Animation library** tab choose a local .bvh file and enter its real provider, license and source URI. Explicitly confirm that its reviewed rights permit **local Blender use outside Unreal**. Changing source/provider/license/URI clears consent.
3. Choose an **explicit source up-axis profile** from the new selector: **BVH Y-up → Blender Z-up**, or **BVH Z-up (same axes as Blender)**. There is no auto-guessing or hidden arbitrary transform matrix.
4. Click **Test 2–4 bone BVH chain against saved MPFB rig...**. Select the locally installed Blender executable when asked.
5. UCC checks every BVH frame/channel with its independent safe metadata parser, verifies source/master SHA-256, and runs two isolated Blender workers. Each worker checks real MPFB deform bones, exact names, direct parent links, source Euler XYZ rotation-channel order, nonzero joint offsets, and the source rest-vector direction under the explicitly chosen axis conversion.
6. The worker requires a **0.90 or greater cosine alignment** between each converted source joint-rest offset and the corresponding target parent→child rest direction. It measures the relative source/target bone-length scale. **For 3–4-joint chains**, two or more bone segments also allow scale consistency to be checked within 25%; a 2-bone chain has only one segment, so uniform scale consistency is **not** certified. Each joint must move at least 16 real weighted mesh vertices under a temporary fixed pose.
7. Blender creates a private Action with all source frames keyed on all selected bones. Five timeline frames are evaluated. Two independent subprocesses must agree on bone names, per-bone movement evidence, actual frame hashes and preserved rig binding.
8. The source BVH, current SHA-addressed Blender master and project metadata remain unchanged. The UI reports matched bones, their real parent links, rest-direction cosine and measured mesh movement. All results remain local, with JSON-only diagnostic summaries in CI.

## Strict limits

- This increment accepts 2–4 bones, exactly one source root and an unbroken source parent chain. If names/parents/axis directions are incompatible, it reports a failure instead of silently dropping a bone or guessing a replacement.
- It uses **local Euler rotation deltas** for all selected bones, at most 45 degrees per joint, and requires XYZ rotation order. Source root translations and source offsets are **not** used to move/scale the character.
- A matching parent, a cosine direction check, and a uniform source/target length ratio **do not** calibrate the BVH bone-roll axes or solve source-to-target rest-space rotation. Source motion may be anatomically incorrect even when the mesh moves. The operation always reports **bone_roll_calibrated=false**, **source_orientation_calibrated=false**, **retargeting_verified=false** and **engine_import_verified=false**.
- Complex Mixamo, UE mannequin, FAB animation clips, FBX and UE-only sources remain unsupported here unless the file genuinely contains a directly compatible, reviewed BVH sub-chain. The user supplies assets; no third-party source data is downloaded or sent to GitHub/AI/cloud.
- This is a read-only diagnostic, not an editor action that adds an animation to the saved character. The MPFB saved master remains generated_unverified.
- The user's actual Windows Blender/MPFB session is still a separate acceptance gate, as are visual deformation quality, interactive UCC playback and Godot/Unity/Unreal reimport.

## Real MPFB integration evidence — November 11, 2026

[Real Linux Blender 5.3.0 / MPFB run #43116913629](https://github.com/DocDamage/newestcharactercreator/actions/runs/43116913629) **PASSED** with a self-authored 25-frame source BVH containing `neck03 → head` (not from Fab or the user's library). The actual Blender MPFB armature contained both named bones in the corresponding parent/child hierarchy, and the Y-up-to-Z-up converted child rest offset aligned at a measured cosine of **0.9948647**. Temporary independent 12-degree poses moved **4,451 actual evaluated vertices from neck03** and **4,451 from head**. The multi-bone action produced three distinct evaluated skinned geometry states across the five selected timeline frames; two separate Blender processes reported matching bone, source/rig and frame evidence. All original source/master/project SHA-256 checks remained unchanged.

This verifies physical **multi-bone animation response and a rest-direction preflight**, not target bone roll, full BVH retargeting, visual quality, the user's purchased clips or engine import. Final CI still must pass on the latest PR commit after any documentation/source changes.

## Verification boundary
## Verification boundary

Contract tests validate BVH hierarchy/order/offset parsing, wrong up-axis rejection, bad parent/skin weights, and fabricated multi-bone evidence. The genuine Linux Blender 5.3/official MPFB test authors a private **two-bone neck03→head original BVH** at runtime using reference MPFB default rest vectors. The real target's rest-direction alignment is independently inspected; real neck/head deformation, two-worker agreement, static frame hashes and byte-for-byte source/master preservation are required to pass.

**No paid/user assets, BVH source files, Blender masters, GLBs or motion Actions are uploaded by CI.** Only JSON evidence is retained.

**Next milestone:** controlled source-to-target **bone-roll/rest-space rotation calibration** and a realistic, explicitly licensed multi-bone user motion selected from the owner's actual library, with visual review before any retargeting claim.
