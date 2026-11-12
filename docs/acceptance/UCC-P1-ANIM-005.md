# UCC-P1-ANIM-005 — explicit 3–8-joint BVH mapping and full-frame inspection

**Milestone scope:** reviewed mapping of one *directly connected* 3–8-bone humanoid chain using existing UCC-P1-ANIM-004 mathematical calibration, not general whole-body/Fab retarget acceptance. Test result status is diagnostic only.

| Gate | Acceptance condition | Evidence |
| --- | --- | --- |
| AC-01 | Original local BVH, original SHA-256, explicit license review and permitted local Blender use; reject symlinks, UE-only or unreviewed clips | Local coordinator and negative unit tests |
| AC-02 | User enters 3–8 unique exact source/target bone pairs in parent→child order; unknown aliases/duplicate pairs, missing deform bones or broken source/target parents fail | Pure mapping tests plus real MPFB worker |
| AC-03 | Retain strict BVH parser bounds, explicit up-axis and known rotation channel order, independent rest directions and proper bounded SO(3) source-to-target conversion | Existing calibration matrix tests and reviewed worker |
| AC-04 | Genuine MPFB weighted pose response for every mapped bone, action keys for all 5–240 source frames | Real Blender worker evidence |
| AC-05 | Measure every evaluated skinned frame, reject >80° per-bone quaternion jumps, adjacent >0.8× first-frame mesh diagonal, displacement >1.5×; detect nonfinite, zero/unchanging motion | Worker plus falsified-evidence tests |
| AC-06 | Two separate Blender workers agree on **all frames**, mapped bones, rest transforms and changed/unchanged geometry; reject mismatched evidence | Strict compared review evidence |
| AC-07 | SHA-verified **private** `review_motion.blend` has the Action, can be reopened in another genuine Blender process; remains private and unapproved until a person visually inspects it | Real Blender CI Action reopen and screenshot/manual gate **unrun** |
| AC-08 | Original source, content-addressed master and project metadata byte-for-byte unchanged, revision conflict and cancellation guards retained; never promote Action silently | Existing coordinator and real CI SHA comparisons |
| AC-09 | Desktop editor takes manual map and invalidates prior rights consent on change; older diagnostics still work and Windows frozen package contains new bridge module | Offscreen Qt and portable Windows workflows |
| AC-10 | All five GitHub Actions workflows pass on **exact PR head** before it can be considered ready; no purchased assets/Blender masters/review Action in CI uploads | Linked GitHub Actions runs |

## First verified slice versus unresolved production goal

The first CI acceptance input intentionally uses **original, private, CI-only BVH motion** with different source names, using measured MPFB `neck02 → neck03 → head` rest offsets. It requires physical Blender 5.3/MPFB, an actual 3-bone Action, full 25-frame skinned motion, two workers' agreement and a third-process review-copy reopen. It is **not** representative proof of purchased motion, full-body motion or joint twist quality. No user-owned asset is uploaded.

Still blocked on an actual authorized, representative animation and human visual inspection: independently measured real-world source rest orientations/roll, anatomical full-body motion quality, IK/feet/root-motion, corrections for discontinuities beyond conservative rejection, video/screenshot approval, genuine engine imports, and Windows owner machine runtime. Never set `retargeting_verified` or engine import flags based solely on hash differences. Do not automatically merge PR #34.
