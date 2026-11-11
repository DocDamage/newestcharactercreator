# Non-destructive Blender master revisions

The UCC backend can now stage a `.blend` created by an external worker, without claiming its geometry has been verified. This is **not a Blender generator, rigging test, or engine import**.

From the repository root, with Python 3.12+:

```powershell
$env:PYTHONPATH = "src"
py -3 -m ucc new "C:\UCC\Projects\FirstHuman" --name "First Human"
py -3 -m ucc stage-blend "C:\UCC\Projects\FirstHuman" "C:\UCC\Jobs\job-001\human.blend" --worker-output-root "C:\UCC\Jobs\job-001"
py -3 -m ucc info "C:\UCC\Projects\FirstHuman"
```

Only use a real, finished `.blend` file from an authorized worker-output directory. The destination is `project/master/versions/<sha256>.blend`; original project metadata stays backed up in `history/`. The CLI prints `geometry_state=generated_unverified`, a hash, byte size, revision, and a warning that Blender must reopen/inspect the file before any engine export.

**Never** stage a purchased FBX/GLB by renaming it to `.blend`, skip fresh-process validation, publish private `.blend` data into this public repo, or treat the structural unit tests as a Blender integration pass.

If interrupted, reopen the project JSON: it still references the prior complete master unless the pointer write finished. Unreferenced versioned files are safe to retain until a future explicit garbage collector can prove they're unused. No automatic deletion of old character revisions is implemented.

See [ADR 0003](../decisions/0003-immutable-master-revisions.md) and [UCC-P0-001](https://github.com/DocDamage/newestcharactercreator/issues/2).
