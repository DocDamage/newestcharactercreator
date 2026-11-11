# Readiness and validation status

| Capability | Status | Proof needed |
| --- | --- | --- |
| Product specification | Defined | Full blueprint and locked choices |
| Preflight/guardrail code | Locally unit-tested (15 tests) | CI run on this pull request |
| Blender 5.3 executable | **Unverified on user's PC** | Version probe |
| MPFB enabled and compatible | **Unverified** | Real create/save/reopen smoke |
| One complete rigged humanoid | **Not implemented** | Native editor + Blender proof |
| Godot import | **Not tested** | Real project import/playback |
| Unity import | **Not tested** | Real project import/playback |
| Unreal import | **Not tested** | Real project import/playback |
| ComfyUI/WebUI workflows | **Not integrated** | Explicit local API smoke |
| Fab animation library | **Not imported** | Files not yet downloaded |
| Character creator UI | **Not implemented** | Milestone 1 |

**Policy:** A test file or generated report is not evidence of functionality until a real application executed it, saved artifacts were checked, and the gate confirmed its required values. Do not mark P0 complete from CI alone.
