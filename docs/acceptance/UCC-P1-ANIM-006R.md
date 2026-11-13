# UCC-P1-ANIM-006R — stable body-contact areas and automatic fitting guard

## Problem and scope

The owned clip's bounded arm candidate reduces opposite-arm crossing frames from
26 to zero and central-body crossing frames from 193 to 172. Those aggregate
improvements do not show whether the correction moves crossings to new areas.
Furthermore, Blender changes triangulation of posed mesh quads: comparing global
triangle numbers across original/fitted buffers can invent contact migration.

This slice audits stable evaluated polygon vertex membership on every frame,
resolves actual highlighted cache triangles through those stable faces, and
rejects automatic candidates that involve new contact faces or increase either
hand's pair count at any source frame. It does not approve contact intent, solid
containment, grasp, visual quality or engine portability.

## Contracts and implementation

- `STATIC_EVALUATED_POLYGON_CONTACT_AREAS_V1` wraps the complete unchanged V1
  hand/head-and-torso report with actual evaluated polygon vertices and their
  exact ordered topology SHA-256. The original V1 operations/API remain supported.
- Four new closed worker operations cover source-only/paired measurement and
  independent reproduction with six/seven/nine/ten exact SHA bindings. Every
  existing source-FK, raw/corrected skin, helper/rest, neutral/master strain, hip,
  canonical fitted Action, topology and original-file check still executes.
- Static polygon topology must match all evaluated original/fitted frames. Face,
  loop, report and inherited body-query budgets remain bounded. Unavailable or
  changing topology has an explicit unavailable result with no partial area list.
- The core independently validates the nested contact report and both receipts,
  bounded face vertices, duplicate/ambiguous face identity, polygon SHA and every
  highlighted triangle through its actual immutable cached vertex indices.
  Changing a quad diagonal or global triangle number does not imply a new face.
- The immutable comparison records per-frame newly involved stable faces and
  pair-count increases for **either** hand. A decrease on one hand cannot conceal
  an increase on the other.
- `NO_NEW_CENTRAL_BODY_POLYGONS_V1` binds the guard to the private reproduced
  report and complete clip. It rejects unavailable, partial, stale or changed
  comparisons and never equates fewer crossings with contact clearance.
- Automatic fitting now needs seven real Blender jobs: candidate, three saved-fit
  stages, full fitted cache and two body-area stages. It returns a comparison only
  after the guard passes. Rejection keeps original playable motion and exposes a
  plain reason plus complete local details. Source FK/master/revision/cancellation
  and licensing guards remain unchanged.
- Successful automatic publication requires the guard again before changing the
  viewer, then publishes the body annotations. A subsequent body-publication
  failure clears the partial comparison. Previously prepared manual comparisons
  remain reviewable without representing them as automatically contact-approved.
- The existing body-review button uses stable-area intake and reports newly
  involved face frames separately from aggregate pair-count changes.

## Actual execution

On the private owned 300-frame/59-role clip, actual source/fitted polygon topology
is static across all 600 observations: 13,378 evaluated faces, SHA-256
`4ebc50c6e074a3ea4a699fd927468213f2769c2c550f0672999256e082554a31`.
An independently executed actual-mesh probe reproduces the complete prior body
report and finds newly involved stable faces in source frames 16–23. This confirms
the migration independently of changed quad triangulation. Neither hand gains
pair count; relying on that count alone would miss this trade.

The production project-bound area API passes fresh measurement
`49611503-2257-499b-a600-922f1e7369b5` and independent reproduction
`0e5c073f-e640-4899-83ea-46005a788cee`. The private report SHA-256 is
`8cc882460cb518a148423952889eb409e647696399f428c338b0a54494bb4fe5`.
Core intake resolves all actual cached highlighted triangles to stable faces and
the guard rejects the existing arm candidate at frames 16–23. Original source,
authoritative master, source review, saved fit and project bytes remain unchanged.
This is evidence of correct rejection, not successful body-contact repair.

The preceding Q implementation also passes the actual Python 3.12 desktop fitting
button through all five earlier Blender stages in approximately 661 seconds,
without false watcher invalidation. Thirty additional private CPU clay views at
frames 1, 16, 23, 218 and 300 are independently decoded and skin-hash-bound.
These show remaining contact issues and remain local; no visual approval follows.

The final Python 3.12 suite runs 626 tests (613 pass, 13 Windows symlink skips),
alongside all 15 earlier preflight/guardrail cases, compilation and whitespace
checks. Tests cover changed quad diagonals/global triangle numbers without false
migration, ambiguous/missing/duplicate face identity, budgets, per-hand increases
hidden by aggregate decreases, unavailable/partial/stale reports, immutable
publication, licensing and cancellation. Mandatory Qt tests verify guard-first
publication, plain rejection and clearing a partially published comparison if
subsequent body annotation validation fails.

The separately generated original source on actual MPFB passes source-only and
paired two-process area intake. Its existing small saved target correction passes
the guard over all 300 frames with zero new contact areas or per-hand increases.
Two additional real Blender workers reject an independently rehashed false body
observation and a rehashed polygon-order claim. Source/master/project, original
review, fitted scene and policy hashes remain unchanged. These are original test
sources, not a claim of owned animation-pack compatibility.

The actual Python 3.12 desktop fitting button passes all seven real Blender jobs
in approximately 1,079 seconds, then rejects new contact areas in frames 16–23.
The unsafe comparison never reaches the viewer; the exact original GPU cache and
frame remain available. The real Qt rejection dialog has a plain explanation and
full details. Original inputs remain unchanged. Private screenshots were inspected.
The final two area jobs are `a3ddc061-5f5e-4ff2-9b82-33cdd976d60d` and
`07a37f3f-76d9-4efa-892a-5a948c2776c9`. All five remote workflows remain required
before review acceptance; unexecuted checks are not represented as passed.

## CI, permissions and limits

The existing original-source fitting suite adds source-only and paired two-process
stable-area intake, a positive guard, and two real rehashed false-report negatives.
No previous integration assertion is removed. Its prior complete workload took
about 41 minutes; the additional full-sequence workers receive bounded headroom
at 65 minutes. Other suites retain their existing limits. Only aggregate original
test diagnostics are retained; purchased assets, raw geometry/poses, scenes,
images and caches remain private.

No new dependency, install, model, download or license-right changes.
The current bounded candidate is now correctly unsupported by automatic fitting;
its older manually reviewable comparison remains available. The guard does not
claim exact pair-set containment or penetration depth. Existing intersections can
remain on previously involved faces, so passing it is not collision clearance.

Next: include the stable-face guard inside the bounded candidate search, so unsafe
area trades are rejected before saving and alternative trajectories can be tested
without relaxing the 30 mm, joint, strain, correction or pose-evaluation bounds.
