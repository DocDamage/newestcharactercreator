# UCC-P1-ANIM-006F — native body motion on private MPFB copies

Stacked on PR #39 (native FBX intake), never a replacement for the existing BVH
contracts. This implements a measured body FK preview and private Blender review;
it does not certify arbitrary full-body retargeting or animation quality.

## Working vertical slice

- Native source intake preserves the unanimated bind transform, real bone rest
  matrices, every animated pose and armature-object motion. No frame-one rest
  substitution, BVH-channel guessing, source overwrite or timeline cropping.
- Strict profile schema binds source, full native snapshot and immutable target
  master SHA-256. Explicit mappings support 15–64 joints. The optional automatic
  adapter recognizes one exact 76-bone name/parent topology, measured locally;
  unknown families require an explicit profile. No fuzzy aliases or source
  transforms/animation content are distributed with the adapter.
- The current automatic map applies 21 body roles: root, spine, neck, head,
  clavicles, upper/lower arms, wrists, upper/lower legs and feet. It reports all
  56 omitted native bones. Finger, face and toe animation are not applied.
- Source and target nearest **mapped** ancestors must agree. Anatomical tips
  must be actual descendants on the same branch. Neutral target helper bones
  remain in the hierarchy; Blender `convert_local_to_pose` compensates their
  parent/rest transforms rather than requiring identical rigs.
- Common anatomical frames use actual joint-head segments and explicit secondary
  directions. Imported FBX bone-tail axes are not assumed to describe anatomical
  limbs. Source T pose and target A pose are aligned while retaining actual target
  bind roll. Body landmark handedness, height, sidedness and foot-forward tests
  reject incompatible inputs. Near-parallel segment/secondary axes reject.
- Convention `NATIVE_ANATOMICAL_REFERENCE_V1` computes world orientation
  `C * (S_pose * S_bind.T) * C.T * target_reference`. The app independently
  recomputes calibration and every resulting target pose from original source
  matrices. Nonzero initial motion is preserved. Actual MPFB target matrices need
  bounded numerical SO(3) projection (maximum allowed 0.0005, measured locally
  around 0.000012); source rotations remain subject to strict original checks.
- Root translation is scaled from measured body height, including multi-root
  sources with animated armature objects. Whole-character rotation may exceed
  360 degrees; adjacent quaternion discontinuities still reject. Joint rotations
  retain existing swing/twist/step bounds. Animated joint translation, animated
  scale, reflected/sheared transforms and excessive workload reject explicitly.
- Every nonroot mapped target must deform at least 16 actual weighted vertices
  in an independent 12-degree probe and restore the exact neutral mesh hash.
  Every source frame is keyed and evaluated. Independent FK residual, all-pose
  digest, skin digest, vertex count, bind-relative/first-frame edge strain,
  root-relative deformation, adjacent mesh jumps and root speed are checked.
  Rigid world travel is separated from deformation so walking is not rejected
  merely for moving farther than a body width.
- Two independent target workers must agree on all measured poses, geometry,
  calibration and quality values. Saved review copies have separately checked
  hashes. Master, source, profile, snapshot, project revision/metadata and staged
  input hashes are verified across the operation. Cancellation/timeouts, partial
  Action cleanup and neutral pose restoration preserve original files.
- A private saved Action and 15 actual Cycles CPU clay images cover five frames
  in front, quarter and side views. Camera/lights follow measured root translation;
  geometry hashes retain actual world motion. The app independently checks image
  bytes/pixels, clipping, frame/skin provenance, root offsets and all input hashes.
  Review creation leaves every retargeting/visual/engine approval flag false.

## Desktop and CLI

Animation library → select local FBX → review provider/license/source and local
preview rights → **Test selected FBX on saved character**. Automatic mapping is
the default for the measured family. The optional map field is an advanced
explicit override. The operation freezes character edits and supports Cancel.
**Open private animation** opens the SHA-bound copy in installed Blender for
scrubbing/playback. **Open sampled views** opens the private local HTML index.
Changing source/map invalidates results and rights confirmation. The animation
pane scrolls on smaller screens. The UCC geometry viewport remains static.

Developer equivalent:

```powershell
$env:PYTHONPATH='src'
python -m ucc preview-fbx 'selected.fbx' --project 'character-project' `
  --blender 'installed-blender.exe' --policy-file 'reviewed-local-policy.json'
# Other skeletons: add --mapping 'source-snapshot-master-bound-map.json'
```

## Executed verification

- Baseline before this slice: 402 unit/worker/Qt tests, 12 Windows symlink
  privilege skips; all 15 preflight/guardrail tests. All five PR #39 workflows
  passed its exact head. These results do not imply this slice's CI has passed.
- Real local Windows Blender 5.3.0 / official MPFB 2.0.18: original non-shipping
  CI FBX authored from measured real MPFB geometry, with independently authored
  T-pose limbs/bone rolls, three bone roots, nonzero initial limb motion, 300
  frames, 4.0168 m root travel and a complete 400-degree turn. The real
  19,158-vertex, 163-bone target passed 20 independent skin probes, two-worker
  complete-timeline agreement and 15 image checks. Maximum actual FK residual
  0.00001397; target numerical projection 0.00001142. A third Blender process
  reopened the saved Action and independently reproduced all 300 pose/skin
  hashes and bind-relative strain. Source/profile/master/project bytes unchanged.
- Actual worker negative tests mutate translation/scale at frame 20, after
  partial Action creation: both reject, remove the partial Action, restore exact
  neutral skin and rig fingerprints, create no review copy and preserve master.
- Actual owner desktop preview of a licensed local 300-frame breathing animation
  succeeded with automatic 21-role mapping, all 20 weighted skin probes, two
  workers, 15 private images and unchanged originals. Owner source content,
  transforms, renders, policies, paths and screenshots remain outside Git.
- The same actual owner breathing Action was independently reopened in another
  Blender process: all 300 pose/skin hashes and bind-relative strain reproduced.
  Front/start, quarter/midpoint and side/end views were inspected for obvious
  flips/tears/framing problems; this is sampled engineering inspection, not full
  visual acceptance. Two additional actual clips **rejected**: a walking clip at
  frame 82 stretched a pelvis/spine/upper-leg blended edge from 5.343 mm to
  21.428 mm (4.010741× bind length); a kneeling clip at frame 64 exceeded the
  generic knee swing guard (153.911° > 150°). Private Blender investigation
  independently reproduced the pelvis-edge measurement without disabling the
  guard. All originals remained unchanged. These clips are not compatible or
  approved merely because source intake previously passed.
- Final local unit/worker/Qt suite: 429 tests run, success with 12 Windows symlink
  privilege skips; 32 actual Qt cases included. All 15 preflight/guardrail tests
  pass; syntax and whitespace checks pass. Exact-head CI outcomes are recorded
  in the PR after execution. Synthetic contract fixtures test rejection/math
  only and never establish owner/Fab compatibility.

## Limits and next gate

FK body preview has no foot planting, ground-contact solver, IK, finger/face/toe
motion, source prop transfer, live UCC skin playback, motion editing or engine
export. Bone-roll anatomy is constrained by measured segments/secondary axes;
it is not an independent producer-exporter certification. General skeletons,
arbitrary proportions, other packs and visual quality need separate verification.
Full sequence evaluation detects numerical/deformation hazards; 15 sampled images
do not prove that every intermediate pose looks good. Existing geometry approval
state is unchanged. No asset/model/runtime dependency is added or distributed.
Local-preview license permission does not grant AI, export or redistribution rights.

Next: investigate pelvis/helper deformation on the rejected actual walking clip
and deep-knee motion on the rejected kneeling clip, preserving current guards.
Then address foot contact with independent full-frame skin/root validation and
private visual comparison. Keep main stable; never merge without owner approval.
