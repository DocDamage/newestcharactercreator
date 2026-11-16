# Godot candidate skin adapter

Development integration for Godot 4.7, used by the private staged-candidate job;
not yet bundled in or exposed by the desktop export workflow. No engine, dependency or asset installation is needed
to read these files.

`ucc.export.godot_skin_plan.build_skin_plan(candidate_path)` reads a bounded,
self-contained dense GLB and produces the V1 skin plan. It matches vertices
using float32 position bytes and named positive imported bone/weight codes,
independently of vertex ordering and UV channels. Duplicate signatures may
share a plan only when they require identical final codes. Ambiguity, positive
influence loss, unsupported extensions and malformed accessors reject.

Write the plan as finite JSON, hash the exact bytes and bind that SHA-256 to
the candidate job. The Godot call is:

```gdscript
var result = load("res://ucc_skin_adapter.gd").apply(
    imported_mesh, "res://character.glb", "res://skin_plan.json", bound_plan_sha256)
```

The adapter checks contract versions, hashes, named binds, full correspondence
multiplicities and the actual eight-slot skin-buffer layout. It changes a copy
of the mesh only after validation, preserves original attributes, morphs and
material, and checks exact integer-code readback before replacing the instance
resource. Reapplying the same bound plan is idempotent. Failures return a
structured rejection and preserve the original instance resource. The dummy
headless rendering backend does not support the required buffer readback;
real graphics-backend execution is required.

The skin policy apportions codes with largest remainders so each vertex sums
to exactly 65,535, retaining all positive contributions. It does not change
GLB weight serialization tolerances. Skin encoding alone does not validate
animation, rendering, rights or the complete engine profile.

## Required animation import settings

The combined 24 FPS diagnostic needs `animation/fps=24` and, under
`_subresources.nodes["PATH:AnimationPlayer"]`, `optimizer/enabled=false` and
`compression/enabled=false`. Configure these in the staged candidate's
`character.glb.import` and reimport before verification. Preserve any existing
project's settings; the private export job operates in an isolated staging
directory. Other frame rates and AnimationPlayer import identities require
their own bound settings and actual verification.

The default optimizer reduced 25 skeletal samples to three or four keys and
shifted some peaks in actual testing. Both default import and FPS-only
correction failed full-surface checks. Disabling optimization retained the
required motion and passed the original fixed geometric tolerance. Do not
assume these settings succeeded from a successful importer exit alone.

Actual local evidence and outstanding production gates are described in
[UCC-P1-007](../../docs/acceptance/UCC-P1-007.md). The adapter is not yet bundled
with the desktop package. The private `verify_staged_godot_candidate` API now
provides canonical input admission, explicit permissions, four bounded Godot
phases, independent image/deformation evidence and atomic private retention.
The bounded `produce_private_godot_candidate` API also runs the production
Blender stage and fresh reopen operations against an authoritative saved master
and a separately selected compatible Action. Its complete 25-frame / 24 FPS
profile has actual original diagnostic verification. The derived review scene
is separately bound to its original Action source. Private Blender evidence is
retained under `.ucc-source-evidence/.gdignore`, preventing automatic Blender
imports inside the engine verification project. Broader native-motion lineage,
packaged resources and public desktop dispatch remain unfinished.
Blender-only corrective smoothing and
dual-quaternion candidates require explicit rejection or independently
verified exact baking. Never silently discard those effects.
