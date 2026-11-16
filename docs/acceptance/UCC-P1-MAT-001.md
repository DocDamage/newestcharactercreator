# UCC-P1-MAT-001 — Prepared body material candidate

Status: preparation, private-project atomic graph publication and independent
saved-master verification executed. Later backend body/face material preservation
is accepted separately in [UCC-P1-MAT-001-C](UCC-P1-MAT-001-C.md). Desktop behavior
and the full application goal remain incomplete. The original next-step plan
below is retained as dependency context; see that later record for current limits.

The dependency is the accepted real prepared human, expression library, registered
hand, and source UV gates. Inventory 199 proves the source human has no material
slots or textures. The original cube's unrelated material is never reused.

## Implemented slice

`ucc.core.skin_material.SkinMaterialSpec` admits finite explicit sRGB color and
roughness under `UCC_MPFBBODY_PRINCIPLED_COLOR_V1`. The closed recipe binds saved
project metadata, master, expression library and selected part manifests. There
are no external images, texture references, providers, asset downloads or rights
changes. The private acceptance parameters are `(0.58, 0.31, 0.19)` and `0.62`;
these are non-shipping verification inputs, not an approved default skin.

`prepare_skin_material_revision` admits the real source expression/hand chain,
then runs separate stage and fresh reopen Blender workers. The latter reconstructs
the expected material from the original, checks the actual exported GLB, and
opens the saved material master without repairing it. Full nonmaterial fingerprints
preserve geometry, all keys, UVs, rig and unrelated scene data. Unknown, shared,
multi-material or altered shaders reject. A total deadline, cancellation, source
identity/hash guards and retention rollback protect the private candidate.

The material worker exports a static rigged GLB with dense canonical morphs.
Existing animation export defaults are preserved. The first real attempt 214
failed because Blender's static exporter emitted sparse morph positions; no
candidate or project pointer was published. Attempt 217 explicitly disables
sparse morphs and passes both real workers. No numeric acceptance limit was relaxed.

## Real evidence

Private root: `D:/dev/new Character Creator/evidence/export001`.

- `skin-material217/receipt.json`: normal API succeeds; stage
  `7ea7c184-65cc-46a4-a438-e95547df4799`, fresh reopen
  `1f987b1f-79ee-45af-94bc-d0abdb863406`.
- Retained candidate `3ae6b230-5109-4bfd-a247-b7c3ae62e276`, material master SHA256
  `2480d112a28fdf1cf437a1b4699eb117f8893f807bf108ef46506837c8de5bd9`;
  verification SHA256
  `a95d96aeec03baaa8a4888399190e6a9110100cf54e0cc5a0dc00a002dcbae4e`.
- `skin-material-godot218`: actual Godot 4.7.1 official
  `a13da4feb8d8aefc283c3763d33a2f170a18d541`, Vulkan Mobile, RTX 3060.
  Separate actual import and readback/render commands return 0. Imported
  standard material sRGB maximum error `5.96046447753906e-8`, roughness
  `0.620000004768372`, metallic 0, opaque, back-face culling, no textures.
  All 163 bones and 12 morphs remain; no animation clips are added.
  `actual-imported-material.png` is an actual 512x512 lit standard-material
  render without material override. Visually inspected: human visible and
  unclipped. This does not establish artist approval or Blender/engine render parity.
- Godot stores the imported linear glTF color through `linear_to_srgb` in its
  [exact engine source](https://github.com/godotengine/godot/blob/a13da4feb8d8aefc283c3763d33a2f170a18d541/modules/gltf/gltf_document.cpp#L2885).
  The readback compares sRGB to explicit sRGB inputs; GLB checks compare linear
  values. The two color spaces are not conflated.
- `skin-material-faults219/receipt.json`: three actual fresh Blender workers
  reject modified saved shader roughness, modified saved vertex coordinates,
  and modified GLB base color, despite coherently rebound file/stage hashes.
  Positive candidate and original project/source hashes remain unchanged.
- `skin-material-cancel223/receipt.json`: normal source admission completes,
  then a real owned Blender child is observed alive and cancelled. The API
  rejects, terminates the child, and leaves project metadata, original files
  and the retained candidate set unchanged. The launch observer returns the
  actual process; it does not substitute a worker result.
- Final full required-Qt regression 220: 1,273 tests, 1,259 passed, 14 existing
  skips. This run follows the dense-morph correction and exporter regression
  test. Guardrails 222: 12 passed. Pure core/export/coordinator imports load no
  Blender, Qt, NumPy or model runtime. `git diff --check` passes.

## Limits and next acceptance

The original project remains unchanged. The later `skin-material-graph226`
normal API operates on an admitted private copy. `apply_skin_material_revision`
resets the selected hand privately, prepares and independently inspects the new
material master, publishes its expression ancestry, builds a new hand library,
and reapplies the original selection with the original part instance ID.
Immutable proofs and masters are installed before one atomic metadata save
advances both master and appearance. The appearance value is a SHA256 binding
under `ucc.body_material.v1`; it identifies a closed material manifest, not a
render approval or arbitrary texture path. Original unrelated appearance values
and facial strengths remain intact. A separate normal saved-expression/hand
verification passed after the API returned.

Graph 226 final master SHA256 is
`216093e5de41bb35d544aa7369fd727a2b692fda0bac7d908f26295b9108dd4f`.
The graph receipt retains all intermediate identities and the two final independent
inspection jobs. The original project and every original master on the private
copy remain byte-identical. The source master and selected-hand recipe are never
silently replaced or reinterpreted.

`skin-material-final-export231` runs the normal material preparation API on the
published rebuilt-hand master with the same material spec. Its real stage and
fresh worker return a verified no-op: the saved material master is byte-identical
to the published master, the project revision stays unchanged, and the static
GLB contains the final hand. `skin-material-godot232` imports and renders that
GLB with the actual standard PBR material; numeric readback retains the selected
color and roughness, 163 bones and 12 morphs. The 512x512 render was visually
inspected for visibility and clipping. Render parity and artist approval remain
unproven.

`skin-material-second238` performs a second normal graph edit on an admitted
copy of the published first character, choosing sRGB `(0.35, 0.22, 0.14)` and
roughness `0.74`. It copies the old material proof closure explicitly, extends
the expression/material ancestry, rebuilds the compatible hand again, and
passes a separate saved-master verification after its one metadata commit.
Final master SHA256:
`e283d63b78d2c7dad3914aabbfb38cb6c9e9ff09d3d1e3d3892226f83ad8c5da`.
The first published project stays unchanged. Both edited characters retain
exactly the same inspected expression-key hash. These are private test choices;
neither color is installed as a shipping default.

`skin-material-second-export240` also returns a verified same-spec no-op on the
second final rebuilt-hand master. `skin-material-godot241` imports and renders
that exported master with sRGB maximum error `2.98023223876953e-8`, roughness
`0.740000009536743`, metallic 0, no material override or textures, 163 bones and
12 morphs. Its render was visually inspected for visibility and clipping and has
a different pixel hash from the first material render. This confirms the revised
material reaches the final export; it does not approve artistic skin quality.
An initial private audit's arbitrary unique-RGB-count check failed on this darker
8-bit render (671 colors versus 1,449 in the first). That failed audit is retained.
The corrected image audit compares opaque silhouettes exactly: both have the
same 33,043 foreground pixels and bounds `[115, 33, 396, 478]`, without clipping.
The existing material, geometry and source numeric limits are unchanged.

Final graph-source regression 237: 1,282 tests, 1,268 passed, 14 existing skips,
263.174 seconds. This follows strict material recipe/source and expression/hand
ancestry checks. Earlier run 233 passed but predates those last checks. Guardrails
234: 12 passed; pure graph imports contain no Blender, Qt, NumPy or model runtime.
Synthetic transaction tests cover failed final save, failed hand rebuilding,
concurrent source mutation, stale/pre-cancelled requests, altered appearance
bindings, wrong hand variants, and the temporary body/face preservation guards.

`skin-material-graph-fault235` changes the actual saved shader roughness on a
separate disposable copy. It recomputes the master hash, material manifest,
appearance pointer and hand receipt coherently. The immutable original material
proofs remain readable, but a real fresh Blender hand worker rejects the changed
master against original reconstruction. The positive published project remains
unchanged. Structural proof admission alone is not counted as fresh deformation
or shader verification.

Body generation, body refit, face edits and a different hand selection currently
reject material-bound projects explicitly. Their next implementation must retain
or deliberately reapply the chosen material and extend its binding atomically.
Source-animation references are also rejected before graph publication until
their fresh license/source closure is integrated. These are temporary limitations,
not completion of the full requested editing workflow. No new UI is exposed.

The single next task is `UCC-P1-MAT-001-C`, material preservation through body/face
editing. It depends on this graph and must inspect `expression_mutation`, the
existing body/face workers, hand reconstruction, and reference-aware editing
before changing them. Resolve the admitted old material spec before making a
private projection; perform the requested real body/face edit there, retain or
reapply the shader against the new geometry, independently inspect canonical
keys, rebuild the compatible hand, then extend material and expression ancestry
before one outer metadata commit. Keep the current explicit guards until the
replacement paths are verified. Do not clear the authoritative appearance or
source-animation references to make a lower-level API accept an edit.

Acceptance requires actual changed body dimensions or facial geometry together
with the same chosen material parameters, original hand selection and part ID,
unchanged facial strengths, fresh save/reopen and final-master Godot import.
Exercise body regeneration as well as refit, coherent shader corruption,
cancellation/source mutation and final-commit rollback. Prior masters and undo
metadata must remain usable. No new dependency, asset or UI is required for that
slice. The private projection makes the work reversible; the public appearance
and master pointers must advance together only after verification.

Pending body/face intent may differ from the physical hand recipe. As in the
existing reference-aware editor, admit and verify a private projection of the
old physical intent before applying the new desired parameters. Copy the old
material proof closure explicitly into that projection; never rewrite the
outer project to make its existing hand recipe appear current. Both the body
revision receipt and any later material reapplication receipt must be installed
before the new hand/material binding can become authoritative.

Frozen host execution, Unity/Unreal import,
textured skin, tangent/normal maps, moving native material rendering and matched
Blender/Godot visual comparison have not been executed. Previous archive 198
predates this code. Original NoAI, asset privacy and distribution restrictions
remain in force. No dependency or license changes were made.
