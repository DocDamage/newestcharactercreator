# Failure and Recovery Playbook

| Failure | Expected behavior | Proof |
|---|---|---|
| MPFB operator missing | Stop; show addon/extension installation and enablement instructions; no substitute cube | Actual Blender operator list + error log |
| MPFB in headless mode fails | Record incompatibility; test authorized alternative context/worker route | Repeatable Blender job and reopen report |
| Blender worker crashes mid-save | Keep prior master intact; stage dir quarantined/cleaned only after log capture | Prior master hash unchanged |
| Cancel, timeout or forced kill | Idempotent cancellation, no dangling child, one terminal job state | Logs + master hash and re-run |
| Invalid, missing or untrusted asset | Quarantine metadata, do not execute embedded scripts or import without provenance | Rejection reason and URI |
| AI OOM on 12 GB VRAM | Free GPU queue, lower resolution/tiles or use CPU/manual route | OOM log, alternative successful test |
| Multiple skeleton families | Classification, explicit mapping and retarget preview; do not silently merge | Rest pose/retarget review |
| Export wrong scale/axes | Fail that engine profile, preserve source | Engine screenshots and measured height |
| Unsupported morph targets | Report named target and mapping gap, not fake facial support | Engine importer log and face comparison |
| Model checkpoint unknown | Mark unknown model family/license; do not run risky workflow or upload | Inventory report and user selection |
| NoAI/UE-only restriction | Block prohibited AI input or non-Unreal export | Asset ID + policy checker output |

## Atomic save algorithm

1. Resolve project location inside approved workspace; reject traversal and unsafe symlink substitution.
2. Lock project revision; make a recoverable snapshot/hash of `master/character.blend`.
3. Run Blender on a **temporary copy** or produce a staged output in a distinct directory.
4. Validate staged `.blend` can reopen in a fresh process; validate sidecar JSON and references.
5. Atomically replace authorized project files on the same volume and advance revision; preserve rollback snapshot for the whole transaction (geometry + metadata).
6. On failure, leave last good revision active, log full job output and make an error visible in UI.

Never build 'undo' by rewriting the authoritative `.blend` in-place and assuming it can be reconstructed after a crash.
