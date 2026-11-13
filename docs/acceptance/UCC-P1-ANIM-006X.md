# UCC-P1-ANIM-006X — bounded body-shape fitting (in progress)

Dependency: PR #57's accepted two-process anatomical publication guard.
The existing automatic fit leaves late hand/body contact. Actual measurements
show a hand can be entirely buried without a hand/body surface crossing;
source wrist/arm observations do not justify inventing a persistent grasp.

The first vertical slice adds an explicit `BOUNDED_NATIVE_BODY_SHAPE_IK_V3`
policy to both independent policy intakes and saved-Action evidence validation.
Its endpoint displacement is bounded by the smaller of 80 mm and five percent
of measured head-to-foot span. Existing V1/V2 policies retain 30 mm / two
percent. All policies preserve the existing 15-degree arm/hand correction,
velocity, acceleration, whole-sequence angular, hierarchy, helper, root,
first/last-frame and deformation checks. No caller-supplied limit overrides
are allowed. V3 requires complete hand rotation rows and independently
matching saved-Action angular metrics.

Nonshipping unit fixtures exercise both intakes, absolute/relative/norm and
time bounds, fixed endpoints, finger lengths, unrelated bones, forged poses,
schema closure and independently recomputed angular evidence. These fixtures
are not compatibility evidence.

A private measured trajectory on the existing licensed 300-frame owner clip
passes full mathematical path validation. Its time envelope is an experiment,
not a general candidate generator. The actual Blender stage and all 300 saved
Action/skin measurements complete, but the production API rejects hand/arm
crossings in frames 196–200 before starting verification/renders or publication.
Original source/master/project hashes remain unchanged. This is a useful
negative result, not acceptance of the candidate. Selected-frame refinement
finds a smooth orientation change that passes all 300 actual saved-frame
measurements without hand/arm crossing flags. Independent saved-scene
reproduction and private renders remain in progress, as do complete paired
anatomical checks. The complete local suite runs 719 tests in 93.700 seconds:
706 pass and thirteen Windows symlink checks skip.

The real original-source CI gate additionally exercises V3 through the same
saved-Action/skin/render/cache and rehashed Action-fault checks as V2. Its small
endpoint challenge is explicitly not evidence for large body-shape correction;
this new gate still requires actual local and CI execution.

No complete contact clearance,
anatomical quality, general automatic fitting or engine acceptance is claimed.
The desktop action still uses its previously verified V2 policy.

Acceptance requires complete saved-Action/skin reproduction, private rendered
inspection, stable body-contact and enclosed/uncertain polygon checks, original
file immutability, appropriate negative paths, and all five exact-head CI
workflows before PR acceptance. No assets, poses or renders are uploaded.
No dependencies, installation or license permissions change.

Next: measure the complete experimental path on actual skinned MPFB geometry
and reject or refine it using the independent contact evidence.
