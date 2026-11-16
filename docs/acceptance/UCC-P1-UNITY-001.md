# UCC-P1-UNITY-001 — same-human Unity import

Status: in progress; no Unity model integration accepted yet.

Plan: inspect the installed editor and bundled Blender FBX exporter, establish an
isolated package-manager-disabled project, then measure a real export/import of
the saved prepared human. Preserve registered hand, meter scale, axes, all family
bones, up to eight weights, UVs, twelve canonical facial shapes and owned material.
Keep the core independent of Blender and Unity, with versioned adapter contracts.

Dependencies: accepted saved-material preparation/source review, neutral master,
actual Blender export and installed Unity. The 6000.6.4f1 folder has no Unity.exe;
it is not an installed runnable editor. Use actual 6000.4.5f1 binaries, subject to
runtime verification. Blender's existing `io_scene_fbx` exporter is present.

Touched scope: new isolated Unity/export adapters, their source-bound contracts,
verification and tests as feasibility becomes measured. No new desktop control
until behavior, errors and real integration are defined. Stage private working
copies; never overwrite the master, prior output, source proofs or project history.

Acceptance: actual source-derived geometry/rig/weight/UV/morph/material parity,
separate saved-prefab/scene reopening without repair, engine-rendered views and
meaningful fault rejection. Exit status, an FBX file and startup alone are not
model acceptance. Actual body/facial motion require their own complete checks.
No installation, download, package resolution, asset upload or license upgrade.

## Measured private feasibility — not final acceptance

Evidence root: `D:/dev/new Character Creator/evidence/export001`.

- Installed Unity 6000.4.5f1 executed a local editor method in a new asset-free
  project (441), with `-batchmode -nographics -noUpm`. No package dependencies
  were requested; this is startup evidence only. The installed local 6000.4
  reference documents the native mesh/skin APIs used below.
- Actual Blender 5.3.0 / MPFB 2.0.18 exported the existing authored #94603d,
  roughness .65 human with its prepared face and registered shorter hand (442).
  It recorded all 13,380 source vertices, 26,756 triangles, 163 bones and twelve
  morph deltas, UV corners and weights. Original master bytes/state are unchanged.
  Permission is the original authored private Unity test only, retaining NoAI;
  no owner/purchased/catalog/public grant is inferred.
- Actual Unity FBX import and separate saved scene reopening completed (443),
  but audit 444 found 13,184 triangles with different quad diagonals and 568
  imported vertices missing small source influences. The native importer clamps
  `minBoneWeight=0` to approximately .001. Raw candidate weights first need unit
  normalization, as Blender's linear armature does; comparing unnormalized
  serialization ratios was an audit error corrected before reporting skin loss.
  Normalized maximum raw-import error is .0016. These are defects, not acceptance.
- New `blender_bridge/triangulated_export.py` copies the actual source loop
  triangles, UVs, corner normals, material, all keys and groups to a temporary
  admitted bind mesh. It never edits the original or invents geometry. Actual
  Blender export 445 followed by Unity import/reopen 446 and independent audit
  447 yields zero triangle differences and zero UV-corner error. Changing FBX
  forward metadata alone did not change Unity's physical front direction.
- Private prototype 448 uses supported `Mesh.SetBoneWeights` on a clone of the
  imported mesh with exact source correspondence, rather than claiming the FBX
  importer retained discarded data. All 13,380 source points map uniquely across
  14,517 Unity UV-seam vertices; every positive influence is retained, maximum
  eight. The explicit source-bound Unity root maps `(x,y,z)` to `(-x,z,-y)`, with
  +Y up and +Z front. The new private project uses linear color space and Standard
  material with observed linear base color, smoothness .35, metallic 0, no texture.
- Independent audit 449: all 26,756 triangles and UV corners match; position error
  at most 2.736e-7 m, bone-head error 5.616e-7 m, all 163 family bone names/parents
  match, and all twelve morph maximum errors are below 7.738e-9 m. No influence
  is missing. Unity quantizes/renormalizes native mesh weights: maximum observed
  error 3.660e-5, weight-sum error below 4.471e-8. This needs an explicit precision
  policy and actual posed-deformation checks before acceptance. Static rest skin
  alone is insufficient.
- Focused isolated worker payload tests 450: 11 passed in 6.116 s, exit 0.
  A new full suite, graphical Unity render and current frozen packaging have not
  run for this helper. Existing package 439 predates the triangulation helper.

The private saved scene uses the adapted mesh asset. Reopen performs observations
only, without rebuilding weights, roots or materials. Mesh data matches, but the
CPU-baked rest result has small stage/reopen floating-point differences; exact
JSON equality is not claimed. No product Unity workflow or readiness upgrade is
exposed yet. Private probes and failed audits remain available for reproduction.

Single next task: turn the measured source-bound Unity skin/axis adaptation into
a versioned contract with justified precision bounds, independent posed/morph
surface checks and actual graphical rendering, before adding normal export UI.

## Posed and graphical measurements — acceptance still open

Original-source Blender run 452 recorded 178 states: neutral, one 20° local-X
diagnostic rotation for every family bone, each of twelve canonical shapes at .5,
the saved combined expression and neutral again. These are private deformation
diagnostics, not shipping clips or proof of arbitrary animation compatibility.
Every state contains full evaluated source positions and corner normals. Run 457
independently records all actual source bone matrices for those same states.
The original master, project and registered source/proof files remain unchanged.

Actual Unity 454/456 produced Direct3D 11 renders and CPU/GPU observations. The
first graphical key light faced away from the character; 456 corrects diagnostic
lighting without altering the saved material. Those tight editor loops reused a
single GPU skin buffer, despite 178 calls. Audit 458 exposed errors up to .315 m;
those GPU results are invalid, not accepted. Failed helper compilation attempts
453 (`BoneQuality` instead of the actual `SkinQuality` enum) and 460 (generated
event-subscription typo) remain recorded.

Corrected native Player Loop run 461 applies each state across three real engine
frames. It records 178 distinct frame counts (5–536), 161 distinct GPU buffers
and 157 distinct decoded PNG images. All 178 RGBA 512² images are nonblank with
transparent margins; neutral endpoints match exactly. Neutral, arm, head and
expression views were inspected. `QualitySettings.skinWeights=Unlimited` and
renderer quality `Auto` are actual runtime observations, not assumed settings.
All saved model/mesh/prefab/scene assets remain byte-identical after the run.

Independent 463/466 compares every vertex in every state. CPU positions differ
from the original source by at most 2.763e-6 m; actual GPU positions differ by at
most 3.600e-6 m. GPU versus CPU differs by at most 2.657e-6 m. The GPU buffer has
14,517 records, stride 40, position offset zero, and is in renderer root-bone
space; each state's observed root-bone matrix converts it to world coordinates.
No custom replacement geometry, skin kernel or backend-result substitute was used.

These close positions do not close the shading gate: the native deformed normals
can differ greatly from Blender's evaluated geometric normals, up to 178.895°
in this diagnostic set. The saved combined expression also differs. Static rest
normals are much closer. This discrepancy must be addressed rather than omitted
from an acceptance claim.

Source topology inspection 464 confirms 13,378 smooth quads, point-domain normals,
no sharp edges and no custom normals. Follow-up 469 rules out hidden/helper
geometry: masked and unmasked point normals agree exactly. Actual capture 470
records local positions, face normals and vertex normals for all 178 states;
positions are byte-identical to capture 452. The earlier suggestion that world
coordinate precision caused the large reconstruction outliers is disproved.

Actual source check 474 identifies the comparison defect: Blender changes its
quad tessellation in 42 states (up to 34 triangle rows). Its evaluated corner
normal equals the normal of the same vertex exactly in every state. Reusing the
neutral triangle order against those dynamically ordered corner records produced
false outliers in 464/467. Those diagnostics remain historical failures. Compare
stable source vertex identities instead. Corrected 473 still confirms the real
native shading mismatch, up to 178.895°. Its independent float32 Newell/angle
model differs from source vertex normals by at most 0.044° using source positions,
or 0.228° using actual native CPU positions. No source normals feed the adapter.

Private GPU experiments 475/480 attempt direct modification of the native skinned
buffer, including a camera command buffer. Post-render audits 477/479/481/482
fail: the observed normals remain native. Zero process exit codes do not admit
these attempts. Original logs and failed assertions are retained.

Private prototype 483 copies the actual native GPU position/normal/tangent stream
into a separate draw mesh, preserves the original triangles/UV/material, and
reconstructs normals on the GPU from original quad adjacency. Native Unity bones,
weights and facial shapes remain the position source. The adapter receives no
per-pose source positions or normals. It uses first-party mathematical kernels;
no Blender implementation source was copied into the product. The installed
Standard shader and original linear material remain in use.

Independent post-render audit 484 covers every vertex in all 178 states on
Direct3D 11: position bytes before/after are identical; maximum normal angle is
0.190131°, below the declared half-degree diagnostic gate. Actual neutral and
combined-expression renders were inspected. This demonstrates the private draw
prototype only. It does not establish a saved/reopened adapter, runtime cost,
arbitrary-rig support, artist approval, or the product export workflow.

Repeat 485/486 independently records native and adapter rasters for the same
178 states, plus native base/morph inputs and all 163 bone matrices per state.
The post-render normal/position gate repeats the 484 result. All 178 color
rasters change, there are 157 distinct adapter images, and neutral endpoints
match exactly. Alpha differs by at most one pixel between draw paths; do not
claim exact raster equivalence. The proxy is temporary runtime state and the
saved source model/mesh/prefab/scene bytes remain unchanged.

Deliberate real-GPU normal fault 488 forces a constant output normal. The same
independent audit 489 rejects it with exit 2 and a 179.509° maximum angle, while
all native position bytes remain identical. This is a shading-fault diagnostic,
not a completed product fault/rollback test.

`ucc.export.unity_skin_precision` introduces a bounded native-weight proposal:
retain every positive source bone, unit sum, conservative UNORM16 weight-error
budget and source-derived weight-displacement bound. It does not claim an exact
Unity packing algorithm. A nearest-rounding/remainder hypothesis failed on 1,212
vertices and was not adopted. Scalar tests and worker isolation: 17 passed in
6.255 s (465). The actual weight-only deformation guard still fails: 462's worst
margin is approximately -2.418e-7 m, because native bone-matrix transfer and
evaluation error are additional terms. Combined stale-GPU run 459 also fails.
Neither is acceptance. Keep the existing guards; complete the error model with
independently recorded native/source matrices and an arithmetic derivation.
Diagnostic decomposition 487 now uses the actual native base/morph inputs,
bind poses and all 163 native/source operators for all 178 states. Maximum
individual contributions are 2.764e-6 m from weights, 2.661e-7 m from input
transfer, and 9.365e-7 m from operator transfer. Remaining measured source/native
evaluation residuals are at most 3.698e-7/8.309e-7 m. These measured residuals are
not acceptance tolerances: derive the arithmetic bounds before admission.
Full required-Qt regression 476: 1,375 tests in 215.476 s, 1,361 passed and 14
existing Windows symlink-privilege skips, exit 0. No product coordinator/UI,
new frozen build or Unity package acceptance.

Follow-up 491–507 closes the observed numerical gate for the same 178 states:
actual pre-armature operands and local hierarchy factors account for source and
native rounding, including coefficient formation. All 5,168,052 CPU/GPU vertex
comparisons pass both their composed bound and the unchanged 50 µm spatial cap;
maximum observed error is 3.599131 µm. Real 100.076 µm GPU position fault 504/505
rejects even though its numerical bound is wider. Normal audit 507 again passes
with position bytes unchanged. Read the [derivation and limitations](UCC-P1-UNITY-001-NUMERICS.md).
The native implementation source is not proven, and the conservative envelope
does not grant quality acceptance to untested poses.

New generic `ucc.export.f32_bounds` provides outward binary32 operation/matrix
bounds, covers gradual underflow and rejects malformed operands, division through
zero and possible intermediate overflow hidden by cancellation. Focused 508: 24 tests
passed, including existing skin-precision and worker-isolation checks. Current
full regression 509: 1,382 total, 1,368 passed and 14 existing Windows
symlink-privilege skips in 211.755 seconds, exit 0. No new product UI or frozen package.

## Source-bound runtime component and fresh reopening

`UnityExportRequest` binds the project/revision, selected editor hash and every
prepared source to explicit per-use Unity permission. NoAI/source privacy stay
required; preview-only and UE-only permissions cannot become Unity permission.
The existing Godot entry point still checks Godot through the shared explicit
engine check. Closed JSON rejects duplicate/unknown fields, invalid identities,
capability changes and forged readiness flags.

`UnityQuadSource` binds the master, native mesh fingerprint, complete native-to-
source vertex map, original quads and exact family bone/shape identities. It
rejects malformed/repeated faces, missing/loose source vertices, inconsistent
winding, nonmanifold edges and valence over 32. Its small index-only unit fixtures
are nonshipping and are not Blender/engine evidence.

The five first-party files under `engine_adapters/unity` provide native mesh
identity, topology validation, owned GPU normals and a colorless native skin pass.
The runtime has no diagnostic pose inputs or reference source normals. It uses
the current native GPU buffer at camera render time and one opaque command pass;
there is no manual second camera render or CPU bake/readback in the runtime path.

Actual experiment 514/515 validates 178 consecutive automatic frames. Producer
517 serializes the component, topology SHA and shader references into a private
copy of the real saved scene/prefab; the native mesh fingerprint remains
`4885255c6a48bafc75f4ca0e9495250146ddeddbf72197e2108251e3565d7263`.
The real original quad graph passes the core contract. Reopen 518/519 proves
automatic component initialization in a new project/cache with no attachment or
weight/axis/material repair by the observer. Source assets remain byte-identical.

Movement testing found a real bug: old world-space normal reconstruction reaches
38.292° after translation `(100, 2, -50)` m and 35° world Y rotation. Native
positions remain preserved. Failure records 520/527 are retained; 520's position
reference expression was wrong and must not be used as a position result.
The corrected implementation reconstructs normals directly in native root space
and accounts for the profile's reversed handedness. It retains the half-degree
gate rather than increasing tolerances. Candidate 523/524 and final current-code
reopens 525/526 validate the fix.

Audits 528/531 cover every vertex in all 178 consecutive states. Maximum normal
error is 0.224554° at the origin and 0.209565° at the translated/rotated placement.
Native position bytes are exact before/after; maximum source-position difference
is 3.600 µm / 10.202 µm, both below the unchanged 50 µm cap. These are fresh
saved-component observations, not editor repair.

Actual saved-source faults 530 alter the topology identity or one native mesh
vertex in disposable copies. Each rejects the specific mismatch, leaves the
component disabled/uninitialized, restores the original source material and
releases its owned buffer. Scene, prefab and weight sources remain unchanged.
Current-code two-camera run 533 and audits 535/536 check both views independently
over 178 consecutive states each. Both retain position bytes and the 0.225°
normal bound. Lifecycle observations verify exact original material reference /
buffer flags, removal of both cameras' commands, buffer release and re-enabling
the same component without changing its source mesh.

Full required-Qt regression 532: 1,392 total, 1,378 passed, 14 existing Windows
symlink-privilege skips in 217.466 s, exit 0. No install, dependency acquisition,
private asset upload, owner launcher change or new frozen package.

Next single task: connect the closed contracts and runtime to the standalone
Blender-to-Unity export transaction, with timeout/cancellation/rollback and fresh
target verification, then expose and test its desktop workflow. Performance,
player builds, broader lighting/pipelines and imported body-animation clips are
not established by these diagnostic states. Overall Unity integration and the
full blueprint remain incomplete.

### Application source jobs and explicit native importer (540–551)

Production `prepare_unity_source` now stages a SHA-bound FBX, original bind
reference and complete positive source weights through the versioned Blender
job protocol. A fresh Blender process reopens the unchanged saved master and
recomputes the reference/weights; it does not rebuild the FBX or claim engine
verification. The host guards saved-project revision, source closure, worker
code and executable throughout, with cancellation/deadline checks and a private
job journal. No project pointer is published by source preparation.

Actual run 540 used Blender 5.3.0 build `02f0899d78e3`, MPFB 2.0.18, and a private
copy of the previously saved material/registered-hand character. Both source
jobs completed and all authoritative project inputs remained unchanged.

New first-party Unity Editor stages explicitly map every native vertex to the
reviewed source and write its complete influences into an owned native mesh.
They persist coordinate correction, reviewed opaque material, unlimited skin
settings, original-quad topology and runtime shader references. Existing output
assets and missing/ambiguous correspondence reject. This conversion is explicit;
raw FBX import is not accepted as preserving every influence.

Actual import 542 and independent audit 543 used the newly produced 540 FBX,
not the earlier prototype mesh. They account for 13,380 source vertices, 14,517
native vertices, 26,756 triangles, 163 bones and twelve shapes. All triangle
identities and UV corners match exactly. Maximum bind-position difference is
0.241 µm; no positive source influences are missing. Native weight quantization
remains observable (maximum difference 0.000036597), not claimed exact.

Fresh reopen preserves every recorded immutable native field and all 52
protected project files. Run 542's overly broad exact-observation assertion
failed because evaluated `BakeMesh` values vary by up to 0.557 µm across the
processes. Audit 543 separately verifies immutable fields exactly and measures
evaluated rest output against the unchanged 50 µm cap (maximum 0.838 µm).
The failed assertion is retained. Earlier 541 is a retained compiler failure
from an incorrect renderer property, fixed before 542.

Stage 545 attaches topology to this actual native fingerprint, saves, and freshly
reopens without rebinding, repairing or resaving. All 60 protected files remain
unchanged. Fresh graphical run 546 then observes the saved adapter through 178
consecutive diagnostic states with two automatic D3D11 cameras. Independent
audits 547/548 use the new native-to-source mapping: every position byte is
unchanged before/after the adapter, maximum source-position difference is
3.526 µm, and maximum normal error is 0.220184° in both cameras. Existing 50 µm
and 0.5° gates remain unchanged. Disable/re-enable lifecycle checks pass.
These diagnostic states do not establish imported animation clip support.

Real Editor faults 550 reject a wrong source-file hash, wrong request identity
and an existing output asset. The exact source mesh reference/fingerprint and
all protected files remain unchanged. No source asset is replaced.

Full regression 544: 1,394 tests, 1,380 passed, 14 existing Windows symlink skips,
219.437 s, exit 0. Subsequent schema synchronization and its focused validation
551: 26 passed, 6.573 s. The complete suite was not rerun after that schema-only
change; the published worker request/result schemas and isolated worker payload
closure were included in the focused run. No dependency installation, network
asset acquisition, private upload, owner-launcher change or frozen package.

Next single task remains the application export transaction: connect these
stages to guarded Unity subprocesses, source/native evidence validation,
cancellation/deadlines and atomic no-replace publication/rollback. Then validate
the desktop workflow and frozen resources. Overall Unity/blueprint acceptance
remains open.

### Guarded native preparation and independent host admission (554–571)

`src/ucc/jobs/unity_engine.py` now connects actual Editor Stage / Attach / Reopen
jobs to source/native admission in `src/ucc/export/unity_bind_evidence.py`.
The pure validator requires complete uniquely matched source vertices, reflected
triangle winding and multiplicity, exact original UV corners, all positive bone
influences under the existing declared native storage budget, canonical shape
deltas, family bone identities/heads and the reviewed opaque material. Native
data and evaluated `BakeMesh` rest output remain separate checks. This stage
does not verify general bind-pose orientation or posed runtime quality by itself.

The host verifies the reviewed Unity executable hash, source artifact and source
verification hashes, first-party resources, cancellation and total deadline.
It creates an exclusive private project with an empty package dependency
manifest, runs with the package manager disabled, seals Assets / Packages /
ProjectSettings, and reopens a fresh copy without setting or repairing native
fields. A caller guard keeps the authoritative saved source closure under watch.
The receipt explicitly records `runtime_verified=false` and
`export_published=false`; atomic publication and the enclosing application
transaction are still open.

Two real incompatibilities were found by strict admission. Attempt 554 rejected
the raw importer minimum: Unity clamps the requested zero to the float32 value
of 0.001. The declared profile now records that observed value; the owned-mesh
conversion still preserves all original positive influences and is checked
separately. Attempt 556 rejected a fresh scene's matrix-recalculation flag:
`forceMatrixRecalculationPerRender` is not serialized. Earlier statements that
the flag persisted were incorrect. The runtime now enables it while active and
restores its exact original value during cleanup. Editor stage/reopen snapshots
record the original false value; the runtime ownership checks require true
while drawing. Neither failure changed the source or published an export.

Actual production host run 557, repeated with the final host control-flow code
in 570, passed native import, host parity, saved topology attachment and fresh
reopen. Both use the newly produced 540 FBX and the unchanged original master.
All triangles and UV corners match, 13,380 source / 14,517 native vertices,
163 bones and twelve shapes are covered. Maximum bind position difference is
0.241 µm, evaluated rest difference 0.974 µm, bone-head difference 0.588 µm and
facial delta difference 0.006431 µm. The native quantization difference remains
0.000036597. Every sealed saved input and authoritative source stayed unchanged.

Actual graphical run 559 cold-opens production 557's saved project with the
current runtime and observes two automatic D3D11 cameras over all 178 diagnostic
states. Audits 562/563 use production topology's native-to-source identities.
Both retain every native position byte and pass 0.5° normal / 50 µm source
position gates (maximum normal 0.220184°, source position 3.526 µm). Lifecycle
checks additionally prove matrix-recalculation restoration and re-enable.
Attempt 558 failed in private harness folder setup before Unity ran; it is
retained and is not engine evidence.

Readback fault audit 561 independently alters actual native observations:
winding, UV, weight-bone assignment, facial delta, source lineage, forged runtime
approval, NaN position and a 1 mm evaluated-rest fault all reject. This is host
evidence validation, not eight live renderer fault tests. Existing real engine
fault evidence remains separate.

Confirmed-live Unity process tests 566 and final-code 571 cancel their own
disposable jobs and verify process exit, source preservation and no publication.
Real deadline test 567 exposed status ambiguity: the total-budget cancellation
mechanism correctly stopped the process but reported cancellation. Final test
568 passes with explicit total-deadline status and preserved raw process flags.
This changes error classification, not the timeout threshold or stop behavior.

The source payload builder/validator and frozen-resource resolver now include
nine enumerated first-party Unity C#/shader files. Missing or modified files
reject, including a file removed from a rewritten manifest. No private character
data enters that payload. A Windows executable has not yet been rebuilt/tested
with this new resource set.

Full required-Qt regression 560: 1,401 total, 1,387 passed, 14 existing Windows
symlink skips, 219.840 s, exit 0. After the final malformed-index hardening and
deadline classification changes, focused 569 passed 36 tests in 7.881 s. The full
suite was not rerun after those small changes; final host success 570, cancellation
571 and deadline 568 exercise the new control flow in actual Unity processes.

Next single task: add production runtime source sampling and actual graphical
readback admission to this preparation path, then finish the enclosing app
transaction's source/revision checks and atomic no-replace publication/rollback.
The desktop workflow and frozen app acceptance follow that transaction. Broader
animation/pipelines/lighting, performance, player builds and full blueprint
acceptance remain open. No install, download, private upload, commit or push.

### Production runtime source and graphical admission (575–577)

New versioned Blender runtime-source jobs capture the original master with its
actual armature enabled, actual point normals and stable original vertex/quad
identities. The 178 cases cover neutral, every one of the 163 family bones at a
20° local-X diagnostic, every canonical facial shape at 0.5, the saved combined
expression and neutral return. No animation Action/clip is created. The host
guards the saved project/source/worker/executable closure. A separate Blender
process reopens the original master and recomputes every case, matrix and vector
byte without rewriting the staged outputs.

Actual production run 575 passed on the pinned Blender 5.3.0 / MPFB 2.0.18 setup.
Its 57,159,360-byte runtime reference is SHA-bound to the reviewed request, saved
master, original bind reference and saved expression parameters. The original
master, project, material and registered hand sources remain unchanged.

The new Editor-only Unity observer receives pose instructions, not the expected
deformed runtime vectors. It renders through the saved native component and
two automatic D3D11 cameras, checks that each component callback completed the
current frame/camera, reads actual before/after GPU data, and writes decoded
render evidence. The host independently compares all native vertices against
the freshly verified original-source vectors, preserves the existing 50 µm and
0.5° quality caps, checks consecutive complete frames and exact position bytes,
and verifies source restoration/cleanup and unchanged saved project inputs.

Actual production path 576 performs native import/parity/attachment/fresh reopen
and graphical runtime admission. All 178 × 2 camera records pass. Maximum source
position difference is 3.525515 µm and maximum normal difference is 0.220184°.
All 356 512×512 images are decoded, nonblank, unclipped and have sufficient
contrast; neutral endpoints agree and deformations/cameras produce distinct
images. The receipt records private diagnostic verification, no published export,
no shipping animation clip approval, no artist approval and no distribution
license approval. Private source data and renders remain outside the repository.

The source payload now includes eleven first-party Unity files. The observer is
guarded by `UNITY_EDITOR`; no player-build acceptance is implied. Focused tests
577 passed 16 checks in 7.574 s. A full regression is recorded separately before
the user-authorized commit/push. The original-master and graphical operations
are real target-application evidence; logic fixtures are not used as substitutes.

Next: connect the verified source/import/runtime stages into the enclosing app
transaction with atomic no-replace publication/rollback, then its desktop
workflow and frozen package verification. Broader game animation, additional
pipelines/lighting, performance/player builds and Unreal remain open.

Final local regression before this checkpoint commit (578): 1,405 tests in
212.991 s, 1,391 passed and 14 existing Windows symlink-privilege skips, exit 0.
Earlier preflight (579): 3 scanner tests and 12 gate/license-policy tests passed;
syntax checks passed. The reviewed staged set contains first-party text/code
only; private source assets, runtime vector data and renders remain outside Git.
The owner explicitly authorized committing and pushing this checkpoint after
the runtime step. This is a feature-branch checkpoint, not release approval.
