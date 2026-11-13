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
complete suite rerun. The new project-bound paired API and original-source CI
gate are being executed. Required actual negative tests rehash a plausible
observation and require fresh reproduction to reject it. A read-only actual
MPFB geometry fault shrinks/translates the real hand fully into a ray-checked
torso interior: central-body triangle crossings must be zero while most hand
faces retain nonzero signed winding. Open/inverted actual skin must reject.
The actual owned-source fault passes: zero central-body surface pairs, with
3,138 / 3,166 hand faces showing nonzero winding. Open and inverted actual skin
reject at their declared topology/positive-volume checks. Original inputs remain
unchanged. No original or diagnostic scene is saved during geometry faults.

The existing body-contact CI suite runs these additional full source workers;
its timeout increases to 60 minutes, preserving every existing assertion and
the other suites. Only aggregate original-source JSON is retained by CI. Final
acceptance requires all five exact-head workflows and downloaded artifact
verification. Real engine imports, grasps and production visual quality remain
unverified. No dependency, install, model, license-right or asset-upload change.

Next: display independently verified inclusion/unknown observations during
original/fitted playback before attempting the remaining body-contact interval.
