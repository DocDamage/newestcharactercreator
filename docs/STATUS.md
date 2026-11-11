# UCC development status — November 11, 2026

**Target:** Windows 11 + Blender 5.3 + installed MPFB, PySide6 desktop, optional local ComfyUI/WebUI and future Godot/Unity/Unreal workflows.

**Merged:** PRs [#24–#28](https://github.com/DocDamage/newestcharactercreator/pulls?q=is%3Apr+is%3Amerged). **Current review:** [PR #29 — real rig-pose test and evaluated static GLB fix](https://github.com/DocDamage/newestcharactercreator/pull/29). The PR #29 behavior is **not in main** until merged.

## Verified capabilities and remaining gates

| Capability | Actual verification | Outstanding |
| --- | --- | --- |
| Real MPFB humanoid generation | [Linux Blender 5.3 + official MPFB integration](https://github.com/DocDamage/newestcharactercreator/actions/runs/43093757960) generated and reopened a 19,158-vertex human, default 163-bone rig | User Windows Blender/MPFB and asset/rig visual inspection |
| Saved normalized Height/Muscle/Weight controls | [Real Blender run #43093757960](https://github.com/DocDamage/newestcharactercreator/actions/runs/43093757960) applied 0.82/0.22/0.88 and independently measured a different mesh from the neutral 0.5 baseline | Live slider editing and physical dimension calibration |
| Existing-master MPFB body refit | [PR #29 real integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) passed real TargetService/HumanService refit, preserved 163-bone rig and 19,158 weighted vertices, retained prior master | Owner Windows runtime; visual fit and source asset variants |
| Static GLB viewer | Qt orbit/pan/zoom and bounded geometry reader tested on Windows/Linux | Textures, GPU rendering, rig animation and full viewport editing |
| **Refitted** shape-baked GLB preview (PR #29) | [Real integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) baked evaluated MPFB morphs into private static GLB (26,756 source triangles; 1,912 sampled) and detected changed geometry | Windows Blender visual review, PBR materials, engine imports |
| **Saved-master skin pose response (PR #29)** | [Real integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245): rotated weighted head bone by 20°, 4,451 mesh vertices moved (max 0.0549627 Blender local units); two independent subprocesses agreed and restored the pose | Actual animation clip playback, skinning quality, IK and retargeting |
| Crash-safe project revisions | Immutable SHA-addressed masters, revision-checked atomic metadata save/backup, cancellation, stale-project checks and content hash validation | User-machine durability testing with large/custom assets |
| PySide6 and Windows portable app | [PR #29 source/Qt/Windows CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713379) passed frozen EXE startup, bundled worker checks and metadata roundtrip | Owner Windows display/DPI, GPU interaction, real Blender installation |
| Animation catalog / bone name matching | Private BVH/glTF metadata intake, named mapping candidates | Rig retargeter, frame-by-frame playback, 100 tested clips |
| Local AI / sprite support | Opt-in localhost ComfyUI concept handling; PNG atlas generation and validation | Local model runtime, AI mesh synthesis, 2D rendering from current 3D human |
| Godot / Unity / Unreal | GLB structural inspections and export blockers | Actual engine import, skinning, animation playback, export rights |

**Important distinction:** A Blender subprocess reporting **real mesh movement** from one temporary bone rotation demonstrates a single static skinning response, **not** general high-quality deformation, animation, retargeting, or game-engine compatibility. The saved project's geometry state remains generated_unverified. Neither PR #29 nor any prior verified Linux smoke establishes Windows success on the owner's PC.

## Regression discovered after PR #28 merge

The [merged main Linux smoke #43099005719](https://github.com/DocDamage/newestcharactercreator/actions/runs/43099005719) found that an MPFB refit's evaluated geometry changed but the static GLB exported unchanged Basis positions. The [merged main desktop test #43099005745](https://github.com/DocDamage/newestcharactercreator/actions/runs/43099005745) also expected obsolete UI wording, blocking Windows packaging. PR #29 now **bakes evaluated Blender meshes into private GLB preview copies**, and updates the historical test assertion. Both fixes passed in its [real integration #43101713245](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713245) and [desktop Qt CI #43101713184](https://github.com/DocDamage/newestcharactercreator/actions/runs/43101713184).

## Security, reproducibility and license bounds

- The user selects their installed Blender executable. No background drive scan, automatic Blender/MPFB installation, Fab library download, AI checkpoint, cloud generation or unreviewed asset transfer.
- Worker jobs use isolated private copies under .ucc-jobs/ and run with --disable-autoexec, bounded timeouts and cancellation. Project and source master SHA-256 are checked before/after.
- CI uses an official SHA-256-checked Blender 5.3.0 archive on Linux and downloads MPFB from Blender's official extension registry into ephemeral runner folders. **MPFB's exact extension release is not yet pinned by version/hash**.
- Only JSON diagnostic summaries are uploaded. Generated Blender files, GLB models, third-party artwork and purchased Fab assets remain private.
- The Windows EXE is an unsigned **internal testing** artifact, not a public release. Distribution licensing for bundled libraries and any paid assets requires review.

## Single next gate

Verify the latest PR #29 commit's complete CI matrix, merge only after passing, then perform a real Blender deformation and preview run on the owner's Windows system. The next functional milestone is **frame-by-frame, source-licensed animation clip playback with measurable skinning**, followed by actual reimport into Godot/Unity/Unreal.
