# Readiness and validation status

**As of November 11, 2026 — evidence from proposed PR [#24](https://github.com/DocDamage/newestcharactercreator/pull/24).** This reflects the PR branch and must not be attributed to `main` until the PR is merged. Successful automation is not equivalent to Windows usability or a finished character editor.

| Capability | Observed evidence | Not yet established |
| --- | --- | --- |
| Product requirements | Locked blueprint and `AGENTS.md` | — |
| Core and worker contracts | [PR #24 core CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628189) and preflight [CI](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628138) passed | Actual user-machine integration |
| Blender 5.3.0 on Linux | Real official archive downloaded and SHA-256 verified in [integration run](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064) | User's Windows Blender binary |
| MPFB HumanService on Linux | Real installed **official MPFB extension** created a substantial human and built-in rig; second-process `.blend` reopen passed | User's Windows MPFB compatibility; **exact MPFB extension version is not pinned/recorded by the current installer** |
| Production Blender worker on Linux | Actual `BlenderJobRunner` `create_human` then independent `inspect_character` passed in [run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064): 19,158 generated vertices, 163 bones on reopen, 2,164,606-byte master, SHA-256 `5fd31980ba72298cab4d18010d05295e9c7b121d1b7cbc445a9c6b48b7fe06cf` | Desktop generation transaction, shape changes, skinning quality and Windows execution |
| PySide6 desktop workstation | Project/metadata editing, asset inspection, atlas packing, read-only static local GLB preview; prior Qt and frozen EXE CI | Interactive generation and deformation of a rigged master inside the app |
| Project revision safety | Atomic metadata save, immutable staged `.blend` revisions, rollback tests | Live production-worker-to-project revision promotion |
| Animation sources | Private BVH/glTF metadata intake and Mixamo/UE bone-name mapping candidates | Real retargeting, preview, 100 validated playable clips |
| Local AI | Explicit opt-in local ComfyUI concept API and API capability probes | Real user-owned local model run and mesh synthesis |
| 2D / 2.5D | Existing PNG atlas packing | Rendering sprites from the real humanoid |
| Godot, Unity and Unreal | GLB read-only structural inspection, no certification | Real engine import, rig/deformation and playback |
| License / paid assets | Conservative source rights and NoAI checks | User-specific licensed asset review; no Fab contents uploaded |

**Evidence scope:** [Linux run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064) generated and re-opened an actual Blender master. The CI artifact `mpfb-linux-json-diagnostics` contains JSON-only summaries and expires after its short retention period. No binary model/master, copyrighted third-party character art or asset pack is uploaded.

**P0 remains open for Windows.** Run `Development_Guardrails/scripts/run_stage0.ps1` with the user's actual Blender 5.3 plus enabled MPFB, keep the generated outputs in private local evidence, and require real mesh/rig save/reopen. This Linux pass must not close [UCC-P0-001 / #2](https://github.com/DocDamage/newestcharactercreator/issues/2).

**Next development gate:** validate the same production worker on Windows and design a crash-safe desktop action: generate → independently inspect → stage immutable master → revision-checked metadata save → update preview. Do not claim animation, deformation, or export success until separately demonstrated.
