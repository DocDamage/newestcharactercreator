# Animation intake — read-only, private catalog (pre-retargeting)

This feature **does not animate an MPFB character**. It inspects a single explicitly selected animation source and records immutable identifiers, skeleton names/fingerprints, clip names, timing when available, and an asset-specific reviewed license policy. It does **not** copy purchased files or send them to AI/cloud services. The user has not yet downloaded their Fab animation library.

## Supported inspections

| Input | What is actually inspected | What remains unverified |
| --- | --- | --- |
| `.bvh` | Hierarchy and parent names, declared translation/rotation channels, exact frame rows, finite numeric motion values, FPS, duration | Retarget mappings, mesh deformation, animation quality, target-engine import |
| `.glb` | Bounded glTF 2.0 structure, skin joints, node hierarchy and animation samplers; duration **only if sampler min/max are present** | Rest-pose suitability, morph deformation, texture quality, actual binary motion value semantics |
| `.gltf` | Metadata-only JSON animation tracks and bones; never resolves external URIs | External buffers, actual joint motion, imports |
| `.fbx` | File existence and hash only; marked `REQUIRES_CONVERSION` | Animation contents until verified Blender import |
| `.uasset` | File existence and hash only; marked `REQUIRES_CONVERSION` | Unreal asset contents until licensed Unreal export workflow |

**All records start at metadata status.** Neither `METADATA_EXTRACTED` nor `REQUIRES_CONVERSION` counts toward the 100+ **usable/previewed/retargeted** animation goal. The catalog will never silently treat an FBX, BVH or Unreal animation as transferable to another engine.

## CLI use on Windows (no IDE)

From the Git repository root with Python 3.12+:

```powershell
$env:PYTHONPATH = 'src'
py -3 -m ucc inspect-animation 'D:\MyAnimations\Walk.bvh'
py -3 -m ucc index-animation 'D:\MyAnimations\Walk.bvh' --database "$env:LOCALAPPDATA\UCC\animation_library.db" --asset-id 'walk-source-001' --provider 'Fab' --license-name 'unreviewed' --source-uri 'https://www.fab.com/listings/REPLACE-WITH-ACTUAL-LISTING'
py -3 -m ucc list-animations --database "$env:LOCALAPPDATA\UCC\animation_library.db"
```

**Replace every example path/listing with the actual one**. The default CLI policy is deliberately **unreviewed**: indexing is allowed, but Godot/Unreal/Unity exports, AI input, and repackaging remain denied. A source URL is not proof of a license.

For an asset whose actual license has been reviewed, prepare a private JSON policy file matching the `LicensePolicy` dataclass fields in `src/ucc/library/provenance.py`, and specify `--policy-file`. Its `provider`, `license_name`, and `source_uri` fields must match the explicit CLI arguments. Never set permissions based on a guessed license or because a file exists in a Fab account. The policy file and the SQLite catalog should remain private; they may contain source URLs and paths. No unapproved source assets should be committed to GitHub.

## Safety and idempotence

- A selected source is hashed and validated without executing animation code or resolving remote texture/buffer references.
- The animation metadata must pass strict size, number, and time checks. An invalid BVH frame, malformed glTF, oversized input, or symlink is rejected.
- If an asset ID already exists with different bytes or license flags, indexing fails instead of overwriting the old record.
- A local SQLite catalog stores metadata and references to user-owned original files, not the animation data itself. Existing `AssetLibrary` v1 databases remain readable.
- A content/skeleton fingerprint is only a classification hint. Similar fingerprints do not prove rest-pose, bone orientation, scale, topology, or legal retargeting compatibility.
- A future Blender/Unreal importer must re-check source hash, licenses, and actual playable/retargeted geometry before advancing a clip to `PREVIEW_OK` or `ENGINE_VALIDATED`.

## Acceptance and next boundary

Pure-Python tests cover true BVH file parsing, glTF sampler metadata and index validation, safe refusal of malformed sources, database persistence, policy enforcement, idempotence, and CLI behavior. This can run in CI without any paid assets or Blender installation. The **next stage** requires real downloaded, permitted Fab packs plus working Blender/MPFB and actual engine testing.
