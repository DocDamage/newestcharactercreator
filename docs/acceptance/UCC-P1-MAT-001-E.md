# UCC-P1-MAT-001-E — explicit desktop skin material controls

Status: source implementation and private application acceptance complete;
the overall creator goal remains incomplete. Builds and owner launcher are unchanged.

The Character pane now accepts an explicit six-digit sRGB color and roughness.
An unassigned character starts with an empty color; no skin color is silently
selected. Draft changes leave project metadata and its appearance proof untouched.
Apply uses the existing verified Blender transaction and adopts master, material
binding and rebuilt hand as one history item. First assignment has a narrow,
explicit adopter; the existing material-only adopter remains strict by default.
Saved values retain their exact precision until changed, including colors that
cannot be represented exactly by the displayed eight-bit hex value.

Eligibility is limited to prepared MPFB humanoids without source-animation
references and with at most the admitted compatible hand. Pending saved body/face
changes must be applied first. Missing proofs, dirty projects, stale revisions,
invalid colors and unsupported sources stop explicitly. Drafts survive normal
refresh and cancellation. Material metadata used for display is not physical
source approval: actual source and shader verification remain in the job layer.

An unchanged Apply runs normal material preparation, owned-shader validation and
fresh reopening. It requires unchanged master bytes and an actual `changed=false`
stage result. A private shader repair cannot be published as a no-op. No-op checks
share the total transaction deadline and cancellation, and create no history item.

Private evidence is under `D:/dev/new Character Creator/evidence/export001`:

- `skin-ui288`: actual visible MainWindow, normal Qt background job and real
  Blender workers assign `#94603d`, roughness 0.65 to an uncolored source.
- `skin-ui289`: the same actual controls edit an already colored character to
  `#7d513c`, roughness 0.72. Exact existing values load without quantization.
- Both cases check draft-only metadata stability, one publication revision,
  actual Undo + Save and Redo + Save, matching master/appearance/hand triples,
  retained body/face/expression intent and unchanged originals. No backend or
  worker result substitution is used.
- Their initial no-op records precede the later strengthened shader check.
  `skin-noop296` is the current-source acceptance: actual unchanged Apply runs
  owned-shader stage and fresh workers, preserves master bytes and metadata/
  backup/session history, and returns `fresh_owned_shader_verified=true`.
- `skin-ui294`: actual Apply and Cancel observe an owned live Blender child,
  stop it, retain the local draft, and leave metadata and backup history unchanged.
- `skin-export292` / `skin-godot293` and `skin-export297` / `skin-godot298`:
  normal final-master static exports followed by actual Godot import, numeric
  material readback and Vulkan rendering. Both have 163 bones, 12 morphs,
  zero clips/textures, no material override, and maximum sRGB error
  2.98023223876953e-8. Roughness errors are below 3e-8. Both renders and the
  current no-op/cancel application screenshots were visually inspected.

Versions: Python 3.12.10, PySide6 6.11.2, Blender 5.3.0 build `02f0899d78e3`,
MPFB 2.0.18, Godot 4.7.1 stable `a13da4feb8d8aefc283c3763d33a2f170a18d541`,
RTX 3060 12 GB. Exact worker commands, reports, return codes and hashes remain
private. The new controls use no textures, substitute assets or cloud services.

Focused controls/no-op tests 295: 23 passed. Workflow tests 299: 4 passed.
Guardrails 301: 12 passed. Final required-Qt regression 300: 1,312 tests,
1,298 passed, 14 existing Windows symlink-privilege skips, 270.629 seconds.
The complete log and independent acceptance 302 manifest retain the results.
The earlier focused 286 run failed because a seven-character field truncated an
invalid eight-digit color; increasing its capacity preserves invalid input for
explicit rejection. Failed evidence is retained; no assertion was weakened.
Synthetic unit fixtures are not Blender/MPFB integration evidence.

The desktop geometry preview still does not display the material. Godot renders
are separate target-application evidence, not desktop shader or artist approval.
Frozen execution, source-animation material closure, other hand changes,
textures, Unity/Unreal and distribution approval remain unfinished. No dependency,
license, NoAI permission or owner-launcher changes were made.

The next task recorded at this gate was a saved-character desktop material preview
with source-derived PBR values and actual renderer/readback evidence. It now has
separate [preview acceptance](UCC-P1-MAT-001-F.md); the earlier results remain unchanged.
