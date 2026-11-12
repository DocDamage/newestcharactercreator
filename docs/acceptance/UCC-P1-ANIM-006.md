# UCC-P1-ANIM-006 — first branching hierarchy slice

**Scope:** replace the reviewed single-chain restriction with a bounded connected
tree. This is an incremental prerequisite for full-body motion, not acceptance
of natural animation, arbitrary rigs, Fab packs, or engine compatibility.
The legacy exact-name 2–4-bone diagnostics keep their chain restrictions.

## Contract and implementation

| Gate | Required behavior | Verification |
| --- | --- | --- |
| Tree mapping | 3–64 unique safe source/target pairs; one source root first; every subsequent source direct parent already mapped; actual target direct parent must be the mapped source parent | Core, worker, Qt and genuine Blender negative path |
| Rest evidence | Every mapped parent/child offset and **every** terminal leaf End Site measured against real target coordinates; 2–126 vectors; all residuals ≤5°; retain proper SO(3), target rest matrices and bounded numerical projection | Pure math including late outlier and upper bound; real Blender |
| Genuine skin | Every mapped deform bone still needs ≥16 substantially weighted vertices and an independent real skin response; static source joints are permitted in reviewed mode and still independently probed | Unit and real Blender |
| Complete motion | Existing ordered-channel quaternion math, ≤45° source component change, ≤80° adjacent quaternion step, full 5–240-frame skin evaluation and existing mesh displacement limits retained | Core plus existing and branching integration |
| Independent evidence | Compare actual tree parents rather than flattening to a fictional chain; account for `links + leaves` rest landmarks; all frames must agree across two workers and a separately reopened private Action | Evidence rejection tests, three real Blender processes |
| Immutability | Original source, SHA-addressed master and project metadata unchanged after success **and** crossed-parent rejection; retain rights, cancellation, stale-revision and rollback checks | Existing coordinator tests and byte comparisons |
| UI | Existing map editor accepts 64 rows, explains branching order, invalidates local rights confirmation on edit; no additional consent grants | Actual offscreen Qt |
| CI | Five existing workflows required on final PR head; real MPFB scenario must exercise ≥9 weighted bones, a branch, and complete connected paths through head, both hands and both feet | [PR #35 checks](https://github.com/DocDamage/newestcharactercreator/pull/35/checks) |

Touched modules: reviewed map validation, Blender selection/calibration/entrypoint,
shared calibrated/reviewed evidence, existing map editor, focused unit/Qt tests,
and additive CI fixture/coordinator helpers. No project format migration or new
dependency. Reversibility: diagnostic Actions remain private copies; no master
promotion. Reverting the feature commits restores the earlier input limits.

## Baseline and locally executed evidence

Inspected clean `main` at `84d5ff89a4174b53b7059a0d63e558e762f8258d`, fetched
GitHub and reviewed merged PRs #31–#34 (including their patches). Baseline:

- Python 3.12.10: `python -m unittest discover -s tests -v`: **343 tests,
  OK, 42 skips** (optional modules/Windows symlink support).
- Stage0 preflight: **3 tests passed**; guardrails: **12 passed**.
- Installed Python 3.10.11 + PySide6 6.11.2: **24 actual Qt widget tests passed**.
  This is supplemental local evidence outside the package's supported Python
  ≥3.12 requirement; supported Python/Qt must also pass CI. No dependency install.

Actual local environment, read only: Blender **5.3.0**, build `02f0899d78e3`,
bundled Python 3.13.13; `blender.cmd` misleadingly points to installed **4.5**.
Use `C:/Program Files/Blender Foundation/Blender 5.3/blender.exe` explicitly.
Python launcher also lists 3.13/3.14/3.15; 3.12 and 3.13 lack PySide6.
GPU: RTX 3060, **12,288 MiB**, driver **610.88**. Godot executable reports
**4.7.1**. Unity editor directories 6000.4.5f1/6000.6.4f1 and Unreal directories
UE_5.7/UE_5.9 exist; neither engine was launched or validated for imports.

Local MPFB smoke was actually attempted using the existing Stage0 runner.
**Blocked:** `MpfbServiceError: Expected exactly one enabled MPFB extension
package in Blender; found 0.` No MPFB package was found in standard configured
version-specific add-on locations checked. No installation, asset scan, model
download or private asset transmission was performed.

Local genuine Blender **synthetic contract only**: ten weighted bones, three
terminal leaves, twelve measured rest landmarks, 25 frames. Two workers agree
and a third process reopens **every** frame with identical skin hashes. Maximum
rest residual **0°**; maximum adjacent skin displacement **0.02658522282** in
fixture-local units. Crossed target parents are rejected by a genuine worker.
Original source/master/project bytes remain identical. Generated fixture and
logs stay in the user's temporary folder and are not repository assets.

Post-change local suite: **350 tests, OK, 11 skips**, under Python **3.12.10**
with existing PySide6 **6.11.2** abi3 binaries made visible through process-local
`PYTHONPATH` (3.12 site-packages first, existing 3.10 site-packages afterward).
This includes all **25** actual Qt widget tests. Python 3.12 without that path
also passes, with 43 optional skips. An exploratory full-suite run under Python
3.10 failed on the existing `hashlib.file_digest` requirement; 3.10 is outside
the supported package range and was not used to claim full-suite acceptance.
The 15 preflight/guardrail tests pass; example acceptance evidence correctly
fails. Actual executable metadata confirms Unity **6000.4.5f1** and Unreal
**5.9**; the 6000.6.4f1 directory lacks an editor executable.

First genuine MPFB CI on `da43e7d3c466b27c0c9aab91fb64a364df7e4b03` passed
[all five workflows](https://github.com/DocDamage/newestcharactercreator/pull/35/checks).
[Blender run 43142556899](https://github.com/DocDamage/newestcharactercreator/actions/runs/43142556899)
created 19,158 vertices / 163 bones, measured a 48-bone branching subtree and
62 rest landmarks, reproduced all 25 frames in a third process, rejected crossed
parents and preserved original bytes. Maximum rest residual was 0.000003416°.
That breadth-first fixture omitted hands/head, so the subsequent fixture now
**requires** their complete paths plus both feet; it must pass again on the final
head. The initial pass is not final-head acceptance. See PR #35 for final evidence.
The first strict endpoint attempt correctly failed because MPFB uses **wrist.L/R**
as hand-base bones, not `hand.L/R`; names were corrected from the actual 163-bone
inventory, keeping the coverage assertion intact. The local opt-in runner's
`--humanoid-names` variant executes the same endpoint-selection branch with
explicitly synthetic labels and passes all frame, hierarchy and byte checks.

Reproduce without installing or downloading anything:

```powershell
py -3.12 -m unittest discover -s tests -v
py -3.12 tests/run_branching_blender_contract.py `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --output "$env:TEMP/ucc-branching-contract-new-run"
```

The output directory must be unused. The synthetic skin fixture is isolated
under `tests/fixtures`, labeled non-shipping, and proves no MPFB/Fab compatibility.
The real MPFB CI adds its own ephemeral tree from the generated human's actual
weighted skeleton, runs two workers, rejects a deliberately crossed mapping,
and independently reopens all frames. Only JSON summaries may be uploaded.

## Unresolved ANIM-006 acceptance

This first slice retains a shared anatomical frame and strict direct-parent
correspondence. It cannot infer arbitrary independent source joint roll from BVH
OFFSETs, bridge unmapped helper joints, automatically align A/T poses, handle
unweighted mapped connectors, root translation, IK/foot locking or FBX/uasset
motion. A map larger than 64 bones, a non-XYZ source, missing End Sites,
inconsistent rest proportions, non-neutral target poses and incompatible trees
remain explicit rejection cases. Motion and mesh thresholds are conservative
guards, **not anatomical twist limits, self-intersection detection or visual
quality approval**. Full hands/fingers may exceed this slice's bounded map.

Open only the private `review_motion.blend` to scrub the Action in Blender;
inspect front/side views, shoulders, wrists, hips, knees and feet throughout
the sequence. Save screenshots privately with frame, view and clip SHA; never
overwrite the immutable master. No human visual approval or rendered animation
quality is claimed here. `retargeting_verified`, `animation_visual_quality_verified`,
`bone_roll_independently_verified` and `engine_import_verified` remain false.

**Next task:** independent per-joint source rest frames and anatomical twist /
deformation diagnostics, followed by private rendered full-body inspection.
Actual licensed clips are not needed to finish those implementation steps.
Afterward, representative local BVH (5–240 frames, XYZ channels, complete rest
hierarchy/End Sites), original source skeleton/rest-pose data and specific pack
license/provider/product URL plus confirmed non-Unreal local Blender permission
will be needed for real compatibility acceptance. Ownership alone is insufficient.
