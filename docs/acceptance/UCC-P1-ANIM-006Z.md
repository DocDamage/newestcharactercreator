# UCC-P1-ANIM-006Z — exact process-local anatomical reuse

Dependency: PR #59's three-report complete anatomical guard. This slice makes
required full-sequence body-adaptation QA more practical; remaining animation
contacts and realistic retargeting quality are still separate unfinished work.

Paired complete-anatomical operations now retain freshly computed original
observations within that worker. A fitted observation can reuse them only at
the same source frame with identical actual float32 vertex bytes, triangles,
whole polygon data, world transform, independently selected regions, rig/map
metadata and calculation budgets. Rounded micrometer skin hashes cannot
authorize reuse. Every saved pose, corrected/raw skin and topology is still
freshly evaluated through the original canonical traversal. The fitted
inspector fully computes its first frame to establish its own metadata.

Source-only operations retain the original collector and allocate no memo.
Unique context and raw key data share a 256 MiB bound; misses and exhausted
storage fall back to full computation. Geometry-count bounds precede key
allocation. Both cumulative highlight limits still apply. Nothing persists
between jobs or independent Blender processes. Existing report schemas,
source SHA checks, licensing, cancellation, revision checks and publication
guards remain unchanged. No master or source scene is saved.

The local suite passes 772 tests in 95.161 seconds: 759 pass and thirteen
Windows symlink tests skip. Twenty new tests cover routing, exact identity,
submicron aliases, changed topology/regions/budgets/world, independent fitted
initialization, memory accounting/fallback and both highlight limits.

Actual Windows Blender 5.3.0 private measurements on the same owned 300-frame
saved job reproduce all three complete reports. The unchanged implementation
takes 733.724 seconds and the initial reuse prototype takes 484.011 seconds
with 255 exact hits and 45 full fitted calculations: about 34% shorter for this
local case, including report validation. These are observed timings, not a
promise for other clips or hardware. All 600 poses and raw/corrected skin rows
remain checked. A strict initial raw JSON comparison exposes pre-existing
binding-object key order from a set; every value and canonical serialization
matches. The enclosure and complete-surface files also match raw bytes.

The bounded prototype then reproduces every original report value and rejects
a coherent rehashed invented contact at fitted frame 46, which is confirmed to
use exact reuse. This fresh run takes 598.761 seconds while local unit tests
also run; it is not the controlled timing comparison. Key data including its
unique context uses 225,164,510 bytes. All protected original files are unchanged.

The shipping real-MPFB fault helper passes locally in 7.782 seconds. It
exercises an exact hit on actual evaluated geometry, then changes a real hand
vertex by one float32 step. The old rounded skin hash and triangle hash stay
equal, actual coordinate bytes change, and full geometry is recomputed. A
forced exhausted memo also reproduces complete observations without reuse.
The evaluated vertex is restored; no scene is saved. CI's existing actual
geometry fault gate now includes this helper alongside every prior fault.

The integrated default two-process application API, all five final-head CI
workflows, artifact audits and portable executable acceptance remain pending.
Owned evidence stays private and is not an animation-pack compatibility claim.
No contact/grasp/visual quality or engine import is approved. No dependency,
installation, license permission or cloud upload is introduced.

Reversibility: revert the collector selection and new module. An internal
uncached collector remains available for differential tests; no worker option
or desktop switch can disable physical verification.

Next: finish the integrated two-worker/CI acceptance, then use the faster
complete-sequence checks to continue actual anatomical adaptation.
