# UCC-P1-ANIM-006V — closed-skin hand inclusion observations

Task: expose a blind spot before attempting further body-contact corrections.
A hand entirely inside a body can have no hand/body surface-triangle crossings.
The existing Q/R contact-area guards retain their exact policies and meaning.

## Implemented slice

Four separately dispatched, SHA-bound operations inspect/reproduce original or
paired fitted saved Actions under `CLOSED_SKIN_HAND_OUTWARD_WINDING_V1`. The
project-bound `review_skin_inclusion` API reuses the existing license, immutable
input staging, cancellation, project revision, source hash and saved-Action
reproduction checks. It returns a separate immutable observation object. It
does not modify an animation or approve an automatic correction. No UI control
or new fit-acceptance rule is introduced.

Every actual posed frame must have a bounded closed, consistently oriented,
connected sphere-topology visible mesh, manifold vertex links, nondegenerate
faces and positive signed volume. Unsupported topology produces `UNAVAILABLE`
for the entire variant, clearing every earlier partial face verdict. It never
becomes a zero-inclusion success. Actual Blender triangle splits may vary;
every frame remains bound to its own complete skin and triangle hashes.

Each completely hand-weighted triangle is sampled at its centroid offset along
its actual outward face normal by `1e-6 * world bounding-box diagonal`. Three
fixed normalized ray directions independently sum oriented exits minus entries.
Agreement at a nonzero integer is a nonzero winding observation. Conflicting,
tangent, near-hit, nonfinite or exhausted-ray results are explicitly ambiguous.
Signed counts preserve overlapping coverage of two; even-parity tests could
incorrectly call this zero. Three agreed zero counts are only a local,
resolution-limited observation, never contact/animation-quality approval.

The closed skin includes other fingers, both arms and all body regions. These
observations do not assign the cause to the central torso, distinguish intended
grasps or identify one enclosing anatomical region. The outward-centroid probe
does not cover every point of a face or resolve sub-offset/coincident surfaces.
Winding of self-intersecting skin is an observation, not a valid-solid claim.

Limits are 50,000 vertices, 100,000 triangles, 10,000 selected faces per hand,
128 hits per ray and 1,000,000 total ray queries per frame. The complete private
report is limited to 64 MiB; it is never silently truncated. World transforms,
actual hierarchy and selected hand regions remain fixed and bound. A fresh
Blender process must reproduce the complete report, including unknowns, from
the saved Actions. The host independently checks closed topology, signed volume
and scale/offset from the verified cache bytes, plus every frame's identities,
disjoint hand selection, per-hand vertex bounds and observation/query limits.

## Verification evidence

Initial unit cases cover closed/open/inverted/duplicate/degenerate/disconnected
and pinched topology; scaled/translated geometry; enclosure without surface
crossings; overlapping coverage; uncertain, grazing, near-hit and capped rays;
and cancellation. Intake tests use original, nonshipping cube/cache metadata,
explicitly not humanoid or animation evidence. Rehashed wrong scope, approval,
frame/skin/topology, world matrix, hierarchy, regions, geometry metrics,
selection, overlap, partial/unavailable and budget claims reject. The schema
and desktop/worker dispatch contracts include all four operations.

Before protocol integration, two fresh actual Blender 5.3.0 processes reproduce
the owned original 300-frame bandaging skin observations exactly as parsed
records (257.429 / 263.369 seconds). Each process independently reopens and
verifies the complete canonical source first. Every observed skin/topology hash
matches that saved source. Original source, master, project metadata and bound
review inputs remain unchanged. Both hands have 3,166 selected triangles. The
right hand reaches 2,933 nonzero observations at frame 211; ambiguous faces
remain separate. This is a diagnostic observation, not pack compatibility or
visual approval. All raw geometry, scenes, caches and images remain private.

The complete local regression runs 672 tests: 659 pass, 13 Windows symlink skips
(final run: 102.390 seconds). All fifteen earlier preflight/guardrail tests, compilation and
whitespace checks pass. The initial regression caught the expected schema-file
inventory increase from fifteen to sixteen; the inventory is updated and the
complete suite rerun. The project-bound paired API passes in 1,296.250 seconds:
both complete original/fitted saved Actions reproduce across two fresh workers,
followed by host geometry/topology intake for all 600 frames. Original source,
master and project bytes remain unchanged. Early right-hand nonzero observations
fall from 1,028 to 254 at frame 20; later observations remain unchanged (2,933 at
frame 211). Seven fitted frames have 1–4 additional nonzero face observations,
with unknowns separate. These results do not introduce an acceptance rule.

Fifteen new actual CPU clay renders cover frames 1/57/193/211/300. Every PNG
decodes, has its recorded byte hash and matches canonical original/fitted skin
hashes at those unchanged frames. Front/side/quarter views at frame 211 were
inspected; the hand enters the torso. No scene is saved or visual approval
granted. Required actual negative tests rehash a plausible
observation and require fresh reproduction to reject it. A read-only actual
MPFB geometry fault shrinks/translates the real hand fully into a ray-checked
torso interior: central-body triangle crossings must be zero while skin winding
is checked against an independent solid-angle oracle at every selected hand
probe. Open/inverted actual skin must reject.
The actual owned-source fault passes: zero central-body surface pairs, with
3,138 / 3,166 hand faces showing nonzero winding. Open and inverted actual skin
reject at their declared topology/positive-volume checks. Original inputs remain
unchanged. No original or diagnostic scene is saved during geometry faults.

The first combined original-source run completes both fresh 300-frame workers,
host cache intake and rehashed-observation rejection, then fails an incorrect
fault-test assumption that 90% of all anatomically enclosed hand faces must have
nonzero winding. An independent double-precision solid-angle sum proves that
self-intersecting connected skin can cancel winding: the exact reference has
2,089 nonzero probes, not 3,166. Ray observations report 2,063, with 41 unknowns;
there are zero definite false-zero/false-nonzero classifications. The corrected
test requires exact independent agreement at every definite probe and at least
90% coverage of the mathematically nonzero reference. It retains the zero
surface-crossing, topology, immutability and no-quality-approval assertions.
The updated actual original-source fault passes, including whole-variant
invalidation after an earlier checked frame and a later otherwise valid frame.
Failed logs remain private. Successful unchanged measurement/verification and
tamper stages are rebound and current core intake rerun after the test fix;
the unified final remote gate remains required. NumPy 2.3.4 is already bundled
with the actual Blender runtime and is used only by the nonshipping independent
verification oracle; it is not added to the application or installed.

This distinction is a material limitation: zero skin winding is not anatomical
body clearance. A separately validated anatomical enclosure is required before
using any inclusion observation to approve further automatic corrections.

The existing body-contact CI suite runs these additional full source workers;
its timeout increases to 60 minutes, preserving every existing assertion and
the other suites. Only aggregate original-source JSON is retained by CI. Final
acceptance requires all five exact-head workflows and downloaded artifact
verification. Real engine imports, grasps and production visual quality remain
unverified. No dependency, install, model, license-right or asset-upload change.

Next: independently validated anatomical body-volume observations that do not
confuse connected-skin fold cancellation with clearance, before further fitting.


## Updated unified Linux body gate

The complete updated original-source gate passes in actual Linux job
[131840552513](https://github.com/DocDamage/newestcharactercreator/actions/runs/43412032000).
Its independent exact reference again has 2,089 nonzero probes; the Linux
worker reports 2,060 definite observations and 44 unknowns, with zero definite
false classifications. Rehashed fabrication rejection and whole-variant clearing
pass in the unified gate. Body/regression ZIP digests and all ten contained JSON
records are checked. All five workflows and all three Linux suites now pass at
`f96ee6bd5f1da7477d7224305c20da9c8015a7b3`. All three ZIP digests and all fifteen
JSON records/domain assertions are independently verified. PR #56 is ready for
review and remains unmerged. Zero skin winding still does not prove anatomical
clearance.
