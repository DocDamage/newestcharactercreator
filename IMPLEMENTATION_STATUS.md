> Current development: **UCC-P1-ANIM-006 branching hierarchy slice**, additive to merged PR #34. Implementation, acceptance checks, measured local results and unresolved gates: [ANIM-006](docs/acceptance/UCC-P1-ANIM-006.md). The historical table below is not current acceptance evidence.

# UCC implementation status (v0.1 alpha backend — historical)

> **Historical v0.1 backend snapshot — not the current feature inventory.** After this snapshot, the PySide6 desktop, static GLB preview, and Windows portable alpha were merged. The actual Linux Blender 5.3 + official MPFB generation and production worker save/reopen also passed in [PR #24](https://github.com/DocDamage/newestcharactercreator/pull/24), [run #43082628064](https://github.com/DocDamage/newestcharactercreator/actions/runs/43082628064). For current, evidence-linked status and the still-unverified Windows gate, use [docs/STATUS.md](docs/STATUS.md). The following table is retained for implementation history.\n\nThis file reports **code verified outside the user's Windows installation**. It does not assert Blender 5.3, MPFB, Godot, Unreal, or Unity have been tested.

| Feature | Implemented | Verified proof | Remaining boundary |
| --- | --- | --- | --- |
| Project v1 schema, immutable data model | Yes | Unit roundtrip, malformed input and future-schema rejection | Bind shape values to actual MPFB APIs |
| Humanoid semantic slots | Yes (metadata) | Slot catalog includes facial parts, fingers, toes, wings, tail and cape | Mesh connectivity, attachment fitting, skinning |
| Proposed part attachment | Yes (metadata) | Socket, family, rig-profile and reviewed-source checks | Validate geometry/deformation in Blender before marking approved |
| Undo/redo | Yes (session memory) | Revision increments, bounded stack, redo | Persist history and Blender geometry transactions |
| Atomic project metadata save | Yes | Conflict, backup, disk failure, symlink tests | Real `.blend` creation/reopen required |
| Immutable Blender master revision staging | Yes (UNVERIFIED files only) | SHA-addressed master, source confinement, concurrent edit, failure recovery and preservation tests | Actual Blender/MPFB geometry validation gate remains blocked |
| Asset ledger and conservative licenses | Yes | SQLite persistence, SHA256, Fab-like restrictions, duplicate detection | Per-product manual review and verified licenses |
| Sprite camera/frame planning and PNG atlas packing | Yes | Directions, custom angles, frame limits, alpha PNG validation, atlas PNGs, rollback and deterministic metadata | Blender-generated frames, layered Aseprite output and engine import |
| Blender worker JSON contract | Yes | Request validation, mismatch rejection, timeouts and cancellation | Real Blender 5.3/MPFB smoke on user's machine |
| Blender worker bpy entrypoint | Written, **untested in Blender** | Python syntax compiles outside Blender | Run P0-001; correct actual MPFB context if needed |
| Python CLI | Yes (metadata/diagnostics) | Create, inspect, morph edit and render-plan tests | GUI application and actual 3D editing |
| Local AI API connectivity probe | Yes (read-only) | Loopback HTTP tests with mock ComfyUI/WebUI server and URL/credential rejection | Actual local installations, authorized generation workflows |
| Automated testing | Yes | 118 local tests across core + preflight; GitHub Windows/Linux CI for prior branch commits passed | Re-run CI for this increment, target-engine validation |
| PySide6 UI / Three.js viewport | Not started | — | Evaluate only once MPFB foundation is proven |
| Animation intake (BVH, GLB/glTF metadata) | Yes (source and clip catalog only) | Real metadata parser tests, private SQLite and license enforcement | No verified preview or retarget; FBX/uasset conversion pending |
| Actual animation imports / retarget | Not started for animation playback | — | Wait for permitted files and rig evidence |
| Godot, Unreal and Unity import | Not tested | — | Real game-engine import/playback |

**No placeholders or demo geometry are committed.** Synthetic byte strings in unit tests are explicitly used to test structural validation, never accepted as real Blender evidence.

## Desktop workstation increment (pending PR review)

The PySide6 desktop workstation adds real versioned metadata editing, input inspection, private animation cataloging and pixel atlas creation. A successful Qt offscreen CI run verifies widget startup and event handling, not a character viewport or MPFB/engine integration.

## Next blocker

Run [UCC-P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2) on a Windows system with Blender 5.3 + MPFB enabled. Do not change the gate status based on CI unit-test results. A result file only proves the contract was followed; real mesh creation and fresh-process reopen are independently necessary.
