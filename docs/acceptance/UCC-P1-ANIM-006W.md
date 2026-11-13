# UCC-P1-ANIM-006W — guarded central-body enclosure (in progress)

Dependency: #55's working bounded hand fit and #56's finding that whole-skin
winding can cancel through connected hand/wrist folds. This task measures the
actual torso/head skin separately before strengthening automatic publication.
It does not approve animation quality or replace the existing surface guards.

## Implemented primitives

`central_regions` derives four actual limb roots from the bound native mapping
and complete target hierarchy. The mapped hand/lower-arm/upper-arm/clavicle
chain is required; helper joints are preserved and no suffix aliases are used.
The trunk complement retains jaw, facial, breast, pelvis and other actual
helper deform bones that the older head/spine-chain surface policy excludes.

`central_geometry` selects complete weighted polygons and preserves their
actual pose-specific triangle splits. Boundary identity does not depend on a
quad's current diagonal. Four oriented limb boundaries must close into the
supported connected, oriented sphere-topology chain with positive volume.
Actual local skin is recentered before the linear world transform; large world
translations never enter BVH float32 arithmetic. No measured skin vertex moves.

`central_cap` fills each boundary as a bounded mathematical chain. These are
diagnostic closures, not physical character parts. Every closure lies inside
its boundary's bounding box. Two such closures differ by a closed cycle inside
that box, whose winding outside the box is zero. Every query in an expanded
closure box is unknown. Three rays are selected from a bounded deterministic
direction set only when they avoid all closure boxes; their BVH contains only
the measured body triangles. Artificial closure faces cannot affect a ray hit.

Initial planar-projection/ear triangulation experiments rejected the actual
non-planar, jagged polygon boundaries. They were retired in favor of the
protected-chain construction above; failed scripts/logs remain private. Tests
independently demonstrate that different closures agree outside their box but
can disagree inside it, where a definite classification is forbidden.

`central_self` bounds each transient BVH overlap list to 262,144 potential pairs
and the complete frame to 1,000,000 candidates. It rejects nonadjacent body
crossings or unavailable work without a partial zero verdict. Shared-vertex/
edge contacts are excluded explicitly; this is not full adjacent-fold or
physical skin-quality approval. Source/candidate pose budgets are unchanged.

## Executed evidence

The complete local suite runs 701 tests: 688 pass, 13 Windows symlink skips
(90.399 seconds), including 29 new primitive cases. All fifteen earlier
preflight/guardrail tests, compilation and whitespace checks pass.

Actual Blender 5.3.0 geometry experiments open SHA-checked, previously verified
private original/fitted scenes and compare every evaluated skin/triangle hash.
The current recentered, bounded kernel measures all 300 original and all 300
fitted frames in 155.545 / 156.606 seconds. Original animation, authoritative
master, project metadata, staged inputs and reviewed license remain unchanged.
The maximum actual BVH candidate count is 4,508; no nonadjacent body crossings
are observed. The stored #55 correction introduces no newly enclosed or newly
uncertain stable hand polygons for either hand. The later issue remains: at
frame 211, 2,959 right-hand probes are inside and one is uncertain.

Earlier complete cap-free prototypes reproduce every classification hash and
stable polygon set in a second fresh process for both original and fitted
variants. These geometry experiments are not yet new worker-protocol or fresh
saved-Action acceptance gates for this milestone.

The new actual MPFB fault fixture separately reopens all 300 canonical source
frames before testing. On both the owned character and original CI character,
an actual hand is moved in diagnostic memory into an independently checked
interior torso ball. There are zero hand/body triangle intersections, while
all 3,166 hand probes classify inside. Independent double-precision solid angles
confirm every probe. A real copied-body intersection is rejected, a forced work
budget returns no partial verdict, and all closure interiors remain unknown.
No mesh datablock, animation, source or master is overwritten or saved.

## Remaining acceptance work

The production sampler, SHA-bound worker operations, strict core intake and
automatic-publication guard are not yet connected. Integrate area and enclosure
collection in the existing final two-process review, retaining the current
nine-job fitting action, immutable inputs, cancellation, revision checks,
licensing and both source/fitted cache bindings. Preserve all earlier operations.

Require no newly enclosed or newly uncertain stable hand polygons, alongside
the existing body-area/per-hand growth guard, before publication. Unknown is
never clear. Add rehashed-report, malformed/provenance, cancellation, watcher
and actual saved-scene negatives; rerun the complete desktop action and GPU
playback. Before PR acceptance, all five exact-head workflows and all three
real Linux suites must pass with independently checked artifacts.

No dependency, installation, model, license-right or asset-upload changes.
The independent nonshipping oracle uses NumPy already bundled with Blender.
Paid geometry, poses, scenes, caches, renders and diagnostic IDs stay private.
The remaining contact interval, grasp intent and engine imports are unverified.

Next: connect the paired enclosure guard to the final review and publication
path, then address the remaining late body-contact interval.
