# UCC-P1-ANIM-006C — SHA-bound per-joint source rest-frame intake

**Scope:** working optional intake and validation, based on merged PR #36 at
`62bda3381b80969722cbdef8c28a3bff025da6bf`. This step accepts declared source
**bone** rest metadata and verifies it against the selected BVH. It does not
reinterpret the BVH rotation channels or claim independent source-roll approval.

## Contract

| Gate | Measurable behavior |
| --- | --- |
| Exact identity | Descriptor names the original BVH's lowercase SHA-256; changing even BVH whitespace invalidates binding. Coordinator hashes descriptor's exact original bytes and sends that SHA only, with fixed staged filename `source_rest_frames.json` |
| Bounded data | Regular selected local UTF-8 JSON, at most 128 KiB; strict version/closed fields, duplicate-key/nonfinite/unsafe-name rejection, bounded vectors and provenance text. No scripts, external references, source-model loading or downloads |
| Complete map | Exactly one frame for each of 3–64 reviewed source pairs, in the same parent-before-child order. Exact names, unique case-insensitive names and actual source parent relationships. No inferred aliases |
| Proper frames | Row-major 3×3 local-bone-to-native-BVH-rest rotation; finite, right-handed SO(3), determinant/orthogonality tolerance 1e-5. No projection or repair of supplied frames. Local Y follows the declared non-degenerate head→tail direction within 1° |
| Actual BVH | Worker independently reconstructs zero-channel rest origins by summing parsed BVH OFFSETs, including root OFFSET. Declared heads must match within 1e-5 source units. Where an End Site exists, declared terminal tail must match it within 1e-5. Nonterminal bone tails have only descriptor/matrix consistency checks; BVH cannot independently establish every bone tail or roll |
| Separate states | Evidence must say `validation_only=true`, `source_channel_interpretation_changed=false`, `source_roll_independently_verified=false`. Every frame's matrix digest, parent and measured residual is checked; unrequested profiles or false application/approval claims reject |
| Immutable jobs | SHA-checked copies in two independent Blender jobs; compare all intake proofs. Reject staged/original file mutation, deletion, cancellation, stale revision and source/license violations. No master/project/profile write or automatic promotion |
| UI | Optional JSON picker in existing mapped-review editor, explicit validation-only description, result SHA/count. Profile/mapping/axes changes clear local rights confirmation; existing diagnostics without sidecar still work |
| Regression | Profiled and unprofiled jobs must produce identical full 25-frame skin/quality timelines. Wrong BVH binding rejects before any worker; structurally valid but shifted source origin rejects inside genuine Blender before master opening or Action creation |
| Packaging/CI | Bundle self-test requires independent worker parser. All five existing workflows must pass on exact final PR head: core/worker, Qt, preflight, real Blender 5.3/MPFB and Windows portable executable |
| Wire capacity | Compact finite JSON keeps the existing 256 KiB response limit. Synthetic boundary test roundtrips 64 maximum-length source/target names, 240 frames and all intake/quality evidence within the cap; no source/frame limits are loosened |

Application preflight is in `src/ucc/animations/source_rest_frames.py`; the worker
independently parses the staged JSON and compares it to actual BVH rest data in
`blender_bridge/source_rest_intake.py`. Application evidence validation stays pure
Python. Neither validator imports Qt or `bpy`. Worker operations remain protocol
v1 with one optional SHA field on `verify_reviewed_bvh_chain`; descriptor schema
is independently versioned. Stale worker request/response schema operation lists
are aligned with actual implemented operations, including reviewed intake.

## Descriptor conventions

See [machine schema](../schemas/source-rest-frames.v1.schema.json). All top-level
fields are required:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `source_bvh_sha256` | Exact original BVH bytes' SHA-256, 64 lowercase hex characters |
| `axis_profile` | The same explicit `Y_UP_TO_Z_UP` or `Z_UP_IDENTITY` selected in UCC |
| `frame_semantics` | Exactly `BONE_REST_AXES_ONLY` |
| `matrix_layout` | Exactly `ROW_MAJOR_LOCAL_TO_BVH_REST` |
| `provenance` | Nonempty `provider`, `method`, `reference` text; declaration only, never fetched or treated as an independent license/authority check |
| `joint_frames` | Ordered records containing exact `source`, `parent` (root null), source-unit `head`, `tail`, and `rotation` |

`head` and `tail` are three numbers in **native BVH zero-channel rest coordinates**
and native source units, before the selected up-axis conversion. `rotation`
contains three rows; its columns are local bone X/Y/Z expressed in those source
coordinates. Its translation is `head`; its positive local Y follows head→tail.
This is bone-frame metadata, not an assertion that BVH channels already use those
bone-local axes. Offsets alone do not prove roll. Obtain frames from an actual
source bind/rest export and record the method; do not fabricate them from names.

Illustrative single record (not a complete profile or a production rig preset):

```json
{
  "source": "SourceHead",
  "parent": "SourceNeck",
  "head": [0, 2, 0],
  "tail": [0, 3, 0],
  "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
}
```

In the Animation library, select the original BVH and review its local-use
rights, choose the explicit axes and source→target pairs, then optionally choose
the descriptor JSON. Reaffirm local-use consent after edits. Use the existing
mapped timeline review. Errors identify binding/schema/hierarchy/rest-position
failures; success reports descriptor SHA and joint count as **validation only**.
No profile is automatically searched for, generated for a user's assets, uploaded,
saved into authoritative project metadata or applied to channel axes.

## Local verification and limitations

- Clean merged-main baseline: **360 tests OK, 11 Windows symlink skips** under
  Python 3.12.10 and existing PySide6 6.11.2 using process-local package paths.
- New local suite: **375 tests OK, 12 Windows symlink skips**, including **26**
  actual Qt widget tests and the new source/worker schema assertion. All **15**
  preflight/guardrail tests pass. No dependency installation was needed.
- Actual Windows Blender **5.3.0** ten-bone **synthetic** contract accepts a
  SHA-bound descriptor, compares two profiled workers, preserves all original
  bytes and matches unprofiled geometry/quality across **all 25 frames**. Wrong
  binding rejects before launch; wrong origin rejects in the worker. Existing
  independent Action reopen, strain/rotation fault tests and partial-Action
  cleanup also still pass.
- Unit/negative tests cover all 64 joints, improper/reflected/sheared frames,
  wrong names/order/parents/conventions, malformed/duplicate/deep/oversized JSON,
  staged tampering, original mutation/deletion, cancellation, permissions, false
  approval claims and worker disagreement. Actual Qt picker/dispatch and JSON
  Schema tests exercise the desktop and public format contract.
- Real MPFB CI authors original ephemeral source BVH and corresponding metadata
  from measured target rest data. This verifies intake plumbing on the genuine
  36-bone MPFB body tree, not independent source-rig or purchased-pack compatibility.
  Only JSON summaries are uploadable. Final-head results belong in the PR.

Reproduce the opt-in Blender contract with an unused output directory:

```powershell
py -3.12 tests/run_branching_blender_contract.py `
  --blender 'C:/Program Files/Blender Foundation/Blender 5.3/blender.exe' `
  --humanoid-names --output "$env:TEMP/ucc-source-rest-contract-new-run"
```

No new dependency/license grant, software/model install, user-asset scan, purchased
file download, cloud asset transfer or engine import is introduced. SHA binding
proves file identity and internal consistency, **not metadata authorship, rights,
correct source exporter behavior or independent bone-roll accuracy**. Existing
retargeting/visual/engine approval flags stay false. Local owner MPFB, actual
licensed clips, source-rig extraction and human visual approval remain separate
unverified gates. Reverting this feature does not require project migration.

**Single next task:** specify and implement an audited source-channel-to-bone-frame
conversion/evaluation convention before applying supplied frames to retargeting,
then verify privately rendered motion. Do not directly substitute these bone
matrices for standard BVH channel axes.
