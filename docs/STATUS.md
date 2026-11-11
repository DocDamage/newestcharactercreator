# Readiness and validation status

**As of November 11, 2026:** PRs [#24](https://github.com/DocDamage/newestcharactercreator/pull/24) and [#25](https://github.com/DocDamage/newestcharactercreator/pull/25) are merged into `main`. [PR #26](https://github.com/DocDamage/newestcharactercreator/pull/26) introduces saved-master static GLB preview and is pending review. Linux integration and Windows portable-build CI do not establish the owner's local Windows Blender/MPFB compatibility.

## Merged increment: desktop MPFB generation (PR #25)

[Pull request #25](https://github.com/DocDamage/newestcharactercreator/pull/25) adds a genuine opt-in PySide6 humanoid generation action, cooperative cancellation, independent Blender worker inspection, checked SHA-256 master staging, project revision/identity concurrency protection and frozen-app bridge files. The **real Linux Blender-to-project test passed** in [run #43086427807](https://github.com/DocDamage/newestcharactercreator/actions/runs/43086427807): 19,158 new human vertices, 163 reopened armature bones and a safely saved project revision 2. The saved output is **generated_unverified**, not deformation- or export-validated. This feature has been merged into `main`; actual Windows Blender/MPFB execution remains unverified.

**Remaining highest-priority verification:** the owner's actual Windows 11 Blender 5.3 + MPFB installation. No live GUI display, morph deformation, rig animation or Godot/Unity/Unreal import has been certified.

| Capability | Observed evidence | Not yet established |
| --- | --- | --- |
| Product requirements | Locked blueprint and `AGENTS.md` | — |
| Core and worker contracts | [PR #24 core CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628189) and preflight [CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628138) passed | Actual user-machine integration |
| Blender 5.3.0 on Linux | Real official archive downloaded and SHA-256 verified in [integration run](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064) | User's Windows Blender binary |
| MPFB HumanService on Linux | Real installed **official MPFB extension** created a substantial human and built-in rig; second-process `.blend` reopen passed | User's Windows MPFB compatibility; **exact MPFB extension version is not pinned/recorded by the current installer** |
| Production Blender worker on Linux | Real HumanService create/reopen, 19,158 created vertices, 163 reopened rig bones; [live project transaction passed](https://github.com/DocDamage/newestcharactercreator/actions/runs/43087335519) | Windows Blender/MPFB, morph deformation, real rig skinning |
| PySide6 desktop workstation | Real local MPFB humanoid generation action with independent reopen and immutable master save; read-only local GLB preview; [Qt CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43087335600) | Live editable deformation and animation; user's Windows Blender installation |
| Project revision safety | Actual worker-to-project promotion with SHA-256, backups and conflict checks, validated in [real Linux transaction run](https://github.com/DocDamage/newestcharactercreator/actions/runs/43087335519) | Long-running user Windows integration and user edits to real shape geometry |
| Generated-master preview (PR #26) | [Real Blender/MPFB static GLB export and parser run #43089727477](https://github.com/DocDamage/newestcharactercreator/actions/runs/43089727477) passed: 36,972 source triangles, 1,946 sampled triangles, no original-master/project changes; [offscreen Qt CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43089728298) passed | Owner's Windows Blender runtime, bone deformation, animation, materials, engine import |
| Animation sources | Private BVH/glTF metadata intake and Mixamo/UE bone-name mapping candidates | Real retargeting, preview, 100 validated playable clips |
| Local AI | Explicit opt-in local ComfyUI concept API and API capability probes | Real user-owned local model run and mesh synthesis |
| 2D / 2.5D | Existing PNG atlas packing | Rendering sprites from the real humanoid |
| Godot, Unity and Unreal | GLB read-only structural inspection, no certification | Real engine import, rig/deformation and playback |
| License / paid assets | Conservative source rights and NoAI checks | User-specific licensed asset review; no Fab contents uploaded |

## Proposed PR #26: static preview of the saved master

A new Character-tab action converts an existing immutable `.blend` to a **private, temporary, geometry-only GLB** via the installed Blender executable, then shows the real mesh in UCC's existing bounded orbit/pan/zoom viewer. The project master stays immutable; source SHA and saved project ID/revision are rechecked. [Genuine Blender 5.3 + MPFB end-to-end run #43089727477](https://github.com/DocDamage/newestcharactercreator/actions/runs/43089727477) **passed**; all five CI workflows on the initial PR commit passed, including the [frozen Windows alpha test](https://github.com/DocDamage/newestcharactercreator/actions/runs/43089727397). This establishes a static **Linux** conversion and a launchable packaged Windows app, not a verified Windows Blender rendering session. [Usage/limits](integration/saved-master-preview.md).

**Evidence scope:** [Linux run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064) generated and re-opened an actual Blender master. The CI artifact `mpfb-linux-json-diagnostics` contains JSON-only summaries and expires after its short retention period. No binary model/master, copyrighted third-party character art or asset pack is uploaded.

**P0 remains open for Windows.** Run `Development_Guardrails/scripts/run_stage0.ps1` with the user's actual Blender 5.3 plus enabled MPFB, keep the generated outputs in private local evidence, and require real mesh/rig save/reopen. This Linux pass must not close [UCC-P0-001 / #2](https://github.com/DocDamage/newestcharactercreator/issues/2).

**Next development gate:** verify this actual desktop generation workflow with Blender 5.3 + MPFB on the user's Windows PC; visually inspect rig/mesh and validate bone-weight deformation, then map real MPFB morphs. Static GLB preview is not a live deformable viewport. Do not claim animation or engine export until independently demonstrated.
