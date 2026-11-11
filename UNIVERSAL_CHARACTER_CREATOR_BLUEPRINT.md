# UNIVERSAL AI CHARACTER CREATOR
## Game Design-Adjacent Product Specification, Technical Development Blueprint & Coding-Agent Execution Plan

**Specification:** UCC-TECH-1.0  
**Baseline date:** 2026-11-11  
**Status:** Architecture approved from 39 user decisions; implementation has **not** been claimed complete.  
**Target:** Windows 11, NVIDIA RTX 3060 12 GB, Blender 5.3, Aseprite, ComfyUI, Stable Diffusion WebUI.  
**Primary output:** One editable 3D master per character, reusable for 3D, 2.5D, and 2D games.  
**Initial validation targets:** Godot, Unreal Engine, Unity. RPG Maker MZ and Lumina are future export adapters.

> **Non-negotiable:** Do not build a second all-purpose Blender. Build an accessible character-creation desktop app that orchestrates Blender/MPFB, stores a rigorously defined character format, and validates exports. Do not claim AI automatically produces production-ready, clean, separated, rigged meshes. Review and repair gates are part of the design.

---

# 1. DECISION RECORD — LOCKED USER REQUIREMENTS

The decision record is authoritative. Preserve it in `docs/decisions/ADR-0001-requirements.md` and change only via a deliberate architecture decision record (ADR).

| Domain | Locked requirement |
|---|---|
| Desktop | **Standalone Windows app**; optional direct Blender editing when needed. |
| Core creation methods | Text prompts; uploaded reference artwork; interactive modular part selection. |
| Foundation | MPFB (MakeHuman Plugin For Blender) **as the initial humanoid foundation**, not our own replacement body generator. |
| Anatomical coverage | Humans, races, monsters, animals, quadrupeds, dragons, robots, unusual anatomy; **humanoid first**. |
| Modularity | Maximal: heads, eyes, ears, noses, mouths, torsos, arms, hands, individual fingers, legs, feet, toes; optional wings, tails, capes, horns and other attachments. |
| Shape editing | Presets, precise sliders, direct manipulation, text-driven edits. |
| Visuals | Pixel-art first; both low-poly/pixel-textured 3D and smooth 3D rendered as pixel-art sprites; high-detail and SNES-like pixel styles. |
| 2D | Sprite sheets, high-res RGBA exports, separated character-part layers, sprite metadata; configurable grid and custom camera angles; multiple resolutions. |
| 2.5D | True 3D in side-scrolling plane, sprites in 3D, orthographic full-3D. |
| 3D | Fully rigged characters, engine-specific exports. |
| AI | Local and cloud backends supported, **user explicitly chooses**; never auto-send local content to remote services. |
| AI parts | Standardized compatible body bases; procedural mesh modification and image-guided new part construction; no expectation of arbitrary reliable one-click generation. |
| Animation | Prebuilt library, AI-driven workflows, external imports, retargeting, manual timeline editing; **100+ eventually**. |
| Fab | Owned Fab animations presently **in the account library, not locally downloaded**; mixed skeleton families expected. |
| Animation priority | First get the working creator; then fill out/retarget 100+ animations. |
| Facial | Shape keys/blendshapes, eye controls, expressions, lip-sync via phonemes, plus 2D facial layers. |
| Secondary motion | Skeletal animation, physics and baked/AI-assisted variations where appropriate. |
| Engine tests | Godot + Unreal + Unity, all required for initial export acceptance. |
| Native format | `.blend` plus sidecar JSON schema, source metadata, and non-destructive working project. |
| Interface | Friendly creative mode + advanced professional workstation mode. |
| Discovery | Selected folders, selected drives and permissioned whole-PC scan; with exclusions, previews and progress reports. |
| Distribution | Preserve private, asset sale and eventual public application options; legal review prior to shipping. |
| First prototype | Fully functional customizable humanoid **before** choosing a custom hero or visual identity. |

**Scope correction:** A 100+ animation library is a target for a subsequent milestone, not a dependency to complete the first character. Body-family support beyond the humanoid is a plug-in design constraint, not a claim that MPFB can generate a dragon.

## 1.1 Definition of success

A non-artist can open the desktop app, create a neutral humanoid using MPFB, adjust body and face proportions, swap a compatible modular part, preview working facial and body animations, save and reopen the editable project without losing state, export a validated 3D character to **each of Godot, Unreal, and Unity**, and render sample 2D sprite output. Blender may be called in the background without the user modeling anything manually. A failed operation must report an actionable error and must not corrupt the saved project.

---

# 2. REALITY CHECK / ARCHITECTURAL BOUNDARIES

1. **MPFB is only the initial humanoid system.** It produces a flexible base, but it does not automatically solve topology-safe replacement of every single body part. A custom anatomical compatibility layer is required.
2. **Separate geometry vs independent controls:** For a finger to be independently movable, separate geometry is not always necessary. We will store part-level IDs and optional separate meshes, plus bone and shape-key controls. For interchangeable extremities, export multiple skinned meshes bound to a common skeleton where suitable. Splitting arbitrary MPFB surfaces without edge repair will produce seams; do not automate this blindly.
3. **Character families are adapters.** `HumanoidV1`, `QuadrupedV1`, `DragonV1`, `MechanicalV1` each get distinct base topology, skeleton capability maps, attachment types, retarget rules and exporter tests. No universal skeleton is required.
4. **Art conversion is not magical.** Pixelation can produce good mechanical baseline frames, but SNES-grade animation may require hand-cleanup in Aseprite. Preserve a layered and editable pipeline for cleanup and re-render.
5. **AI-produced reference images are not meshes.** Converting images into riggable parts needs topology selection, fitting, UVs, skin weights, collision checks, and deformation tests. Phase these separately.
6. **Fab licenses vary.** A Fab listing may use the Standard License, legacy UE Marketplace License, UE-only restrictions, or a special designation. The importer must not treat all owned animations as freely redistributable. Do not package purchased third-party animations with the released creator.
7. **GPU budget:** RTX 3060 12 GB cannot be presumed to run large 3D-generation and image-generation models simultaneously. Gate GPU tasks, include VRAM presets, and use a reliable CPU/Blender fallback.
8. **Cloud privacy:** No remote API requests or uploads without explicit provider and job consent; generation artifacts need identifiable source/provider records.
9. **Shipping license:** MPFB software GPL-3.0-or-later, core data CC0; PySide6 LGPL/GPL/commercial conditions; user art and third-party assets each need license records. A separate Blender subprocess is a sensible engineering isolation boundary, **not** a legal guarantee that all code can be proprietary.

---

# 3. TECH STACK AND WHY

| Layer | Preferred stack | Reason / fallback |
|---|---|---|
| GUI | Python 3.12+ (version validated with current PySide6); PySide6 / Qt Widgets | Practical Windows editor, docks, model/view, asynchronous tasks. Evaluate required Qt license obligations before distribution. |
| 3D viewport | Bundled **Three.js** in Qt WebEngine (local, offline frontend) | glTF preview, rig animation, picking, orbit, transform gizmos. If Qt WebEngine creates licensing or packaging issues, consider standalone localhost view or alternate viewport. Never depend on CDN at runtime. |
| Geometry authoring | Blender 5.3 background worker or controlled interactive Blender session | Actual geometry, rigs, morphs, materials, animation transforms, sprite renders and exports. |
| Human generation | MPFB 2.0.18 initially; version-pin after smoke tests | Parametric humanoid base, asset support, rig systems. Adapter must handle Blender/MPFB API changes. |
| Render/edit | Blender EEVEE/Workbench; Aseprite external CLI and user editing | Reproducible RGBA renders followed by controlled pixel-art pipeline. |
| AI primary | Existing ComfyUI through local HTTP/WebSocket | JSON workflow graph, modular checkpoint selection. |
| AI secondary | Existing AUTOMATIC1111 Stable Diffusion WebUI (`--api`) | Direct prompt/image generation when preferred. |
| Job/IPC | JSON files + subprocess exit/status + per-job logs initially | No fragile custom sockets in Blender. Add a persistent worker only if process launch becomes a proven bottleneck. |
| DB | SQLite WAL; content-addressable asset store | Reliable metadata, dependencies, provenance and deduplication. Keep assets as files, not large SQLite blobs. |
| Core geometry preview | GLB generated by Blender, loaded offline in Three.js | One preview exchange format for app, independent of game-engine-specific artifacts. |
| Schema/tests | JSON Schema, Python dataclasses or Pydantic, pytest | Strict contracts, migrations and regressions. |
| Packaging | Windows native installer via managed Python build / PyInstaller validation | Bundled UI app; Blender and Aseprite remain external user-configured tools initially. |
| Source control | Git; Git LFS only for distributable, license-cleared test assets | Do not commit Fab downloads, AI checkpoints or large user model libraries. |

**Versions are targets, not blind assumptions.** At startup, detect actual Python, Blender, MPFB, ComfyUI, WebUI, Aseprite and target engine versions. Record versions in a reproducibility manifest, then test support via capability checks.

---

# 4. HIGH-LEVEL SYSTEM DESIGN

```
Desktop App (PySide6 + embedded Three.js, offline)
  |-- Project Workspace / Save/Load / Autosave / History
  |-- Beginner Creator / Advanced Editor
  |-- Asset Browser / Model Discovery / Provenance
  |-- Animation Library / Timeline / Retarget UI
  |-- 2D Render / Pixel Processing / Layer View
  |-- Job Queue / Resource Monitor / Error Inspector
  |
  +-- Domain Services (pure Python)
      |-- Character Graph / Part & Socket Rules
      |-- Rig Profiles & Retarget Maps
      |-- Asset Catalog & License Gates
      |-- Export Profiles / Compatibility Validator
      |-- AI Provider Interface + Workflow Templates
      |-- Job State Machine, Scheduling & Logs
      |
      +-- Blender Worker Adapter (local process)
      |     |-- MPFB specific operations
      |     |-- Shape target application, attach/weight
      |     |-- Animation import/bake, preview GLB
      |     |-- RGBA rendering, GLB/FBX export
      |
      +-- AI Backends (opt-in)
      |     |-- ComfyUI (local)
      |     |-- Stable Diffusion WebUI (local)
      |     +-- future explicit cloud providers
      |
      +-- External Tool Adapters
            |-- Aseprite CLI
            |-- Fab downloads *already acquired by user*
            +-- Godot / Unreal / Unity import validators
```

## 4.1 Core boundaries

- `ucc-core` **must not import** `bpy`, PySide6 or any AI libraries. Reusable/testable logic remains independent.
- `ucc-desktop` depends on `ucc-core`, never on private MPFB internals.
- `ucc-blender-bridge` runs *inside Blender* and provides a versioned JSON job contract. This is the only service allowed to use `bpy` and call `bpy.ops.mpfb` or documented MPFB internals.
- `ucc-ai-*` implements a `GenerationProvider` interface; app does not embed ComfyUI custom nodes as trusted code.
- `ucc-export-*` transforms a verified character into independently validated targets.
- `ucc-library` owns immutable source copies, license records and dependency tracing.

## 4.2 Why use process isolation

Blender and Qt use their own event loops and 3D rendering contexts. Running Blender Python directly in the desktop application's Python process is not supported as a practical embedded architecture. Running Blender externally lets us restart a crashed operation without losing the GUI. An optional interactive Blender session can open the saved `.blend` when advanced manual work is needed.

**Worker transaction:** create a temporary working copy of the project, execute Blender, write result JSON and staged exports, validate staged artifacts, then atomically replace approved output. Never mutate the authoritative `.blend` without a snapshot.

---

# 5. FILE FORMAT, DATA MODEL AND VERSIONING

## 5.1 Workspace

```
CharacterProjects/
  DemoHumanoid/
    project.ucc.json              # sole user-facing project descriptor
    master/
      character.blend             # authoritative geometry/rig/material/anim
      character.mhmeta.json       # MPFB recipe/targets, not MPFB implementation
    library/
      parts/                      # project-local part references if modified
      animations/                 # imported, license-cleared working clips
      expressions/
    references/
      images/                     # image generation references
    preview/
      current.glb                 # regenerate on demand; not authoritative
      thumbnail.png
    render_jobs/
    exports/
      godot/
      unreal/
      unity/
      sprites/
    history/
      snapshots/
    provenance/
      manifest.json
    logs/
```

Globally installed/user-owned content lives in an indexed **user asset library**, not in every character folder. A project references assets using stable IDs/hashes with optional project-local snapshots. This avoids copying 100 animation files to each character.

## 5.2 Required schema contracts

### CharacterProject v1

```json
{
  "schema_version": 1,
  "project_id": "demo-humanoid-001",
  "name": "Demo Humanoid",
  "family": "humanoid.v1",
  "base_provider": {"kind":"mpfb", "version":"2.0.18"},
  "master_blend": "master/character.blend",
  "scale": {"unit":"meter", "height_m":1.75},
  "parameters": {"height":0.5, "muscle":0.4, "weight":0.5},
  "rig_profile": "humanoid.v1.mpfb.rigify",
  "parts": [
    {"id":"part-head-001", "part_asset_id":"mpfb-head-base", "slot":"head", "visible":true},
    {"id":"part-hand-l-001", "part_asset_id":"hand-standard-l", "slot":"hand.L", "visible":true}
  ],
  "animations": ["clip-idle-001", "clip-walk-001"],
  "appearance": {"palette_id":"snes-inspired-01", "material_profile":"pixel-cel"},
  "source_manifest": "provenance/manifest.json",
  "created_with": {"app_version":"0.1.0", "blender":"5.3"},
  "revision": 1
}
```

The sample values are **schema examples**: they do not indicate that a working MPFB/Rigify conversion was performed. Parameter ranges, target names and rig IDs must be mapped to MPFB after integration tests.

### PartAsset v1

```json
{
  "id":"hand-standard-l",
  "family_compatibility":["humanoid.v1"],
  "kind":"skinned_mesh",
  "slot":"hand.L",
  "socket":"wrist.L",
  "mesh":"mesh/hand-left.glb",
  "bone_profile":"humanoid.v1",
  "bind_pose_fingerprint":"sha256:...",
  "topology_fingerprint":"sha256:...",
  "unit":"meter",
  "orientation":"configured-by-family",
  "attachment": {
    "mode":"socket-plus-skin",
    "expected_parent_bones":["forearm.L", "hand.L"],
    "fit_rule":"wrist-diameter-range"
  },
  "capabilities":["finger_curl", "thumb_opposition"],
  "license_asset_id":"license-record-001"
}
```

`PartAsset` must additionally store: side/mirroring rules, material slot maps, rest transforms, LOD variants, seam landmarks, weight-transfer policy, max allowed deformation, face/hand optional collision meshes, and parameterized variants. For a horn, cape, or wing, `kind` and `attachment.mode` differ; do not pretend everything is a skin mesh.

### AnimationAsset v1

```json
{
  "id":"clip-run-001",
  "title":"Run Forward",
  "source_uri":"user-library://animations/run-forward.fbx",
  "source_hash":"sha256:...",
  "source_skeleton":"unreal-manny.v1",
  "target_skeleton":"humanoid.v1",
  "fps":30,
  "duration_sec":1.0,
  "loop":true,
  "root_motion":"in_place",
  "translation_scale_mode":"height-normalized",
  "retarget_map":"manny-to-humanoid.v1",
  "tags":["locomotion", "run", "forward"],
  "license_asset_id":"license-record-002",
  "export_policy":"project-use-only"
}
```

## 5.3 Invariants (enforce in code)

- Every slot declares a compatible family; no cross-family swap without an explicit adapter.
- Every deformation part either shares the rig reference or has an approved bone map.
- A replaced part must be positioned in **rest pose** before animation validation.
- Character height and other morph controls must be clamped to tested ranges, including asymmetrical sliders.
- A rigged part's vertex weights must sum to approximately 1 for skinned vertices after normalization; flag missing influences or unexpected bones.
- A part cannot reference a license record that does not exist.
- A public export cannot include raw restricted/licensed third-party content unless its license expressly permits it.
- Project saves, migrations and staged exports must be crash-safe and reversible.
- Unknown schema versions open **read-only** with a migration prompt, never silently rewrite.

## 5.4 SQLite catalog tables

`assets`, `asset_files`, `licenses`, `asset_sources`, `parts`, `part_slots`, `characters`, `character_versions`, `skeleton_profiles`, `retarget_maps`, `animations`, `animation_tags`, `ai_models`, `ai_jobs`, `render_jobs`, `export_jobs`, `job_events`, `external_apps`, `schema_migrations`.

Store metadata columns as indexed fields for queries and flexible JSON for versioned details. Use `UNIQUE(source_uri, content_hash)` or comparable stable identity; hash large files asynchronously. Migrations must be reversible where possible and backed by database snapshots.

---
# 6. CHARACTER / MODULAR ANATOMY ENGINE

## 6.1 Family definition

A `CharacterFamilyDefinition` owns:

- `family_id` and minimum/maximum compatible height/body proportions;
- canonical rest pose (`A_POSE`, optional `T_POSE` conversion), coordinate system and units;
- versioned bone semantics (not hardcoded exact MPFB bone names);
- attachment slot tree (a parent/child graph, not one flat string list);
- part-category constraints, mirroring, asymmetry, topological requirements;
- morph parameter schema and legal ranges;
- render profiles and animation capability tags;
- known exporter compatibility and tests.

**Humanoid v1 slot tree:**

```
character
  pelvis / root
    torso
      neck -> head
        eye.L / eye.R, ear.L / ear.R, nose, mouth, jaw, teeth,
        brows, eyelashes, hair, horn sockets
      shoulder.L -> upper_arm.L -> forearm.L -> hand.L
        finger.thumb.L, index.L, middle.L, ring.L, little.L
          optional finger segments / claws / nails
      shoulder.R -> upper_arm.R -> forearm.R -> hand.R
        mirrored fingers
      back_upper -> cape, backpack, wings.L/R (future skeleton adapter)
      tail_root -> tail (future adapter)
    hip.L -> thigh.L -> calf.L -> foot.L -> toes.L (each digit optional)
    hip.R -> thigh.R -> calf.R -> foot.R -> toes.R
  equipment_sockets -> weapon.L/R, shield, accessories
```

Geometry may remain joined for deformation while the *editor* exposes components separately. This is essential for preventing visible elbow/neck/knuckle seams. True detachable replacement parts have pre-defined cut boundaries and transition meshes (cuffs/neck seams) or a topology-aware welding process.

## 6.2 Slot attachment algorithm

1. Resolve `family_id`, `part.slot`, side (`L/R/C`), skeleton profile, and parent slot.
2. Inspect part bounding box, seam markers, bind pose matrix, expected parent bone semantics, UV/material slots.
3. Reject if family unsupported or no explicit adapter exists.
4. Compute a rest-pose transform from canonical socket coordinates and verify unit scale and determinant; prohibit mirrored negative-scale meshes unless transforms are explicitly baked.
5. Fit geometry: limited nonuniform scale or known morph targets first; for arbitrary new meshes use landmarks and a constrained cage wrap/transfer step.
6. Transfer/normalize skin weights only for compatible attachment topology; inspect min/max bone influences; preserve user-authored weights when valid.
7. Run penetration, seam gap, normal continuity, skeleton influence and 20-pose deformation tests. Store warnings with images.
8. Stage changes, display before/after preview, commit with undo checkpoint.

**Do not** decimate, remesh or retarget without preserving an original. Every action is reversible and logged.

## 6.3 Partial mesh replacement and joint topology

For head, ears, nose, eyes and clothing, meshes may attach as independent skinned geometry. For torso, full arms and legs, automatically slicing MPFB topology is risky. Stage the algorithm:

- **v1:** approved modular variants that preserve reference border loops; seam-concealing clothing or transitional geometry.
- **v1.5:** binding-preserving proxy meshes and skin-weight transfer with boundary matching.
- **v2:** AI-assisted image-to-mesh conversion with artist-review-level mesh fitting and retopology.

Individual fingers, toes and facial features are separately selectable and editable in all cases. They do not each have to be exported as completely unconnected meshes unless necessary for the target 2D-layer or swapping workflow.

## 6.4 Character graph editing commands

Use immutable commands with undo/redo:

```
CreateHuman(base_profile)
SetMorphTarget(parameter_id, value)
AttachPart(slot_id, part_asset_id)
DetachPart(slot_id)
SetMaterial(part_id, material_id)
SetBoneOffset(bone_semantic, matrix)
AddExpression(expression_id, deltas)
AssignClip(animation_id)
ApplyAnimationRetarget(clip_id, profile_id)
CommitVersion(message)
```

Each command validates input preconditions. The Blender worker receives commands in ordered batches and outputs an actual resulting `.blend`, GLB preview, transform report, and warnings. Commands are **not** arbitrary Python strings generated from prompts. Natural-language edits map to a constrained command schema and request review for destructive/unsupported operations.

---

# 7. MPFB + BLENDER WORKER IMPLEMENTATION

## 7.1 Integrate MPFB as a version-pinned dependency

Verified MPFB 2.0.18 documentation identifies `bpy.ops.mpfb.create_human` as the operator for creating a human. Its panel provides configurable phenotype and scale settings. **This does not prove that the operator executes headlessly in Blender 5.3**, so the very first spike must test actual installation, registration and context requirements.

Official MPFB operator documentation:  
https://github.com/makehumancommunity/mpfb2/blob/master/docs/ui/new_human/newhuman.md

### Required spike workflow

1. Ask the user to install MPFB 2.0.18 through Blender Extensions (or use a verified source package).
2. With Blender 5.3 GUI, confirm MPFB panel opens and creates the default human.
3. Record the installed extension module ID, active version, operator availability, scene properties and add-on data locations.
4. Start a **background Blender** job and test `bpy.ops.mpfb.create_human()` with a compatible context. If context-sensitive, use documented service methods and an adapter in a controlled Blender process; do not fabricate an MPFB API.
5. Save `.blend`; reopen in a fresh process; verify humanoid geometry, shape keys, rig state, materials, no missing dependencies.
6. Apply an extreme but permitted height/weight morph; recheck mesh bounds and rig pose.
7. Stage `character.glb` and reimport to test skeleton, skin weights and shape-key data.
8. Only then make the desktop UI depend on MPFB operations.

## 7.2 Blender process contract

### Host invocation (real Python pattern)

```python
import json
import subprocess
from pathlib import Path


def invoke_blender(blender_exe: Path, worker_script: Path, job_file: Path,
                   result_file: Path, timeout_seconds: int = 240) -> dict:
    # Never pass user text as Python source or shell command.
    cmd = [str(blender_exe), "--background", "--python", str(worker_script),
           "--", "--job", str(job_file), "--result", str(result_file)]
    completed = subprocess.run(cmd, shell=False, capture_output=True,
                               text=True, errors="replace",
                               timeout=timeout_seconds)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Blender failed ({completed.returncode}): "
            f"{completed.stderr[-5000:]} {completed.stdout[-2000:]}")
    if not result_file.is_file():
        raise RuntimeError("Blender reported success but no result file exists")
    result = json.loads(result_file.read_text(encoding="utf-8"))
    if result.get("status") != "ok":
        raise RuntimeError(result.get("error", "Unknown worker error"))
    return result
```

Important: `shell=False`, explicit executable path, validated staging directory, per-job locks, process-tree cleanup on cancellation, nonzero exit handling, timeouts by workload class, no unrestricted user scripts, and captured version information. If Blender exit-code reporting proves unreliable in a specific operation, require both valid result JSON and the expected files.

### Worker request/response

```json
{
  "protocol_version": 1,
  "job_id": "9b5c8b93-37c0-4fa3-a1cd-859746ace000",
  "operation": "inspect_environment",
  "input_project": null,
  "output_dir": "C:/UCC/Temp/jobs/9b5c8b93",
  "options": {},
  "expected": {"blender_major_minor": "5.3", "mpfb_min": "2.0.18"}
}
```

```json
{
  "protocol_version": 1,
  "job_id": "9b5c8b93-37c0-4fa3-a1cd-859746ace000",
  "status": "ok",
  "outputs": {"blender_version": "5.3.0", "mpfb_detected": true},
  "warnings": [],
  "elapsed_ms": 1678
}
```

The result is a **contract example**, not evidence of a successful local execution.

### Worker operations, ordered by implementation

| Operation | Description | Phase |
|---|---|---|
| `inspect_environment` | Blender/MPFB versions, registered ops, asset paths | P0 |
| `create_human` | Human from MPFB; save editable `.blend` | P0 |
| `set_human_targets` | Map UI sliders to tested MPFB phenotype/targets | P0 |
| `generate_preview_glb` | Non-destructive viewport transfer file | P0 |
| `inspect_character` | Bone graph, shape keys, mesh/material/bounds reports | P0 |
| `apply_test_part` | Fit/attach an approved interchangeable mesh | P1 |
| `rig_validation` | Check bone semantics, skins and posed integrity | P1 |
| `import_animation` | External FBX/GLB/BVH as supported | P1/P2 |
| `retarget_animation` | Source rig to target rig, bake action | P2 |
| `render_frames` | Camera-angle/frame/pass rendering to staged PNGs | P1/P2 |
| `export_character` | Profile-driven GLB/FBX + manifest | P1 |
| `bake_secondary_motion` | Tail/cape/hair physics to reusable clips | Later |

**Do not** call `--factory-startup` blindly: it can disable an installed MPFB extension in background mode. Verify activation using an isolated test and explicit extension configuration, not only whether a module can be imported.

## 7.3 Determinism and asset safety

Every geometry-changing job captures: Blender version, MPFB version, app protocol version, input project hash, referenced asset hashes, parameter values, timestamps, output hashes, deterministic random seed where available, render settings, and warnings. Cache based on these inputs. Restore the last committed master if any job fails.

---

# 8. AI PROVIDERS AND MODEL DISCOVERY

## 8.1 Provider interface

```python
from typing import Protocol, Any

class GenerationProvider(Protocol):
    def probe(self) -> dict[str, Any]: ...
    def list_models(self) -> list[dict[str, Any]]: ...
    def validate_job(self, spec: dict[str, Any]) -> None: ...
    def submit(self, spec: dict[str, Any]) -> str: ...
    def poll(self, job_id: str) -> dict[str, Any]: ...
    def cancel(self, job_id: str) -> None: ...
```

Different capabilities must be declared: `text_to_image`, `image_to_image`, `inpaint`, `control_image`, `texture_generation`, `multi_view_concept`, `image_to_3d` (future), and `pose_estimation` (future). Never falsely mark a backend as having a capability because it can output images.

## 8.2 ComfyUI (preferred local backend)

The official ComfyUI server supports:

- `GET /system_stats` — availability, devices, VRAM overview.
- `GET /object_info` — discover installed workflow node classes.
- `GET /models` and `GET /models/{folder}` — available model categories and files.
- `POST /prompt` — queue a **validated API-format workflow graph**; returns `prompt_id` or error details.
- `WS /ws?clientId=<uuid>` — execution progress; filter messages by `prompt_id` to isolate user jobs.
- `GET /history/{prompt_id}` — authoritative job outputs; `GET /view` — retrieve generated images.
- `GET /queue` and `POST /interrupt` — queue monitoring/cancel semantics (only interrupt jobs UCC owns or has explicit operator permission to interrupt).

Official docs: https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx

### Submission pattern

```python
import json
from urllib.request import Request, urlopen


def queue_comfyui_workflow(base_url: str, client_id: str,
                            graph: dict) -> str:
    # Validate base_url against configured local or explicitly allowed endpoints.
    body = json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8")
    req = Request(f"{base_url.rstrip('/')}/prompt", data=body,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=15) as response:
        answer = json.load(response)
    if "prompt_id" not in answer:
        raise RuntimeError(f"ComfyUI rejected workflow: {answer}")
    return str(answer["prompt_id"])
```

**This snippet only submits a pre-existing compatible API-format graph.** It is not an image-generation workflow by itself. The app must ship tested workflow templates and check that their nodes and chosen model names exist before submission. Never mutate unrelated graph nodes or assume node IDs remain constant across user-edited workflows.

## 8.3 AUTOMATIC1111 Stable Diffusion WebUI

Only enable when running with API access. Detect supported features using `GET /sdapi/v1/sd-models`, `GET /sdapi/v1/samplers`, `GET /sdapi/v1/options`; generate via `POST /sdapi/v1/txt2img` or `POST /sdapi/v1/img2img`. Use `GET /sdapi/v1/progress` for progress and `POST /sdapi/v1/interrupt` cautiously. Validate model choice; do not change a user's global checkpoint without confirmation or restore it afterward.

Default local endpoint is often `http://127.0.0.1:7860`, but must be discovered/configured. ComfyUI is commonly `http://127.0.0.1:8188`. These are **conventions, not guaranteed configuration**.

## 8.4 Discovery and scan engine

Support three modes specified by the user:

1. Selected folders (safe default).
2. Entire selected drives (show exclusions and resource estimate).
3. Whole PC (explicit consent, scoped drives, user-visible progress, cancellation).

Common file signatures: `.safetensors`, `.ckpt`, `.pt`, `.pth`, `.onnx`, `.gguf`, `.bin`; **extension alone does not prove the model is an image model**. Identify actual model type by metadata/config, known directory structure, available backend listings and safe header inspection. Reject arbitrary pickle model deserialization as a scanner technique; checkpoint formats may execute code if loaded unsafely.

Suggested exclusions: OS folders, recycle bins, package caches, temp files, system reparse points, mount loops, symlink traversal, network drives unless selected, giant known non-model archives. Report permissions denied instead of retrying as administrator. Never move/delete scanned models automatically.

Scanner output must include: absolute path (stored only locally), inferred family, format, size, model hash if computed, backend compatibility, source/license known/unknown, and a **confidence field**. If unclassified, show it as `unknown`, not an invented SDXL/Flux model.

### GPU scheduling on RTX 3060 12 GB

- One active GPU-heavy AI job at a time by default.
- Release/unload image models before expensive Blender Cycles/3D generation as needed.
- Prefer half-precision or supported low-memory modes based on backend/model, but do not auto-force switches that change output semantics or break installed nodes.
- Prefer lower-resolution concept generation followed by refinement; preserve reference linework and consistency settings.
- Reserve CPU/RAM and disk space; check free capacity and fail early with actionable warning.
- Model licenses and ability to run locally must be evaluated individually before suggesting automatic downloads.

## 8.5 AI workflow templates

```
concept_from_text
reference_image_variation
character_turnaround_reference
isolated_eyes_nose_ears
outfit_or_material_variation
texture_reference
normal_or_mask_assistance
background_removal_or_segmentation
facial_expression_reference
```

Workflow output should be stored with prompt/negative prompt, seed, model IDs/hashes, scheduler, image size, source file links, and optional manual edits. AI-generated artworks can be used as references without ever changing the Blender master until a controlled **Apply** action occurs.

---

# 9. ANIMATION SYSTEM: LIBRARY, IMPORT, RETARGET, EDIT

## 9.1 Staged development

**First character:** minimal validated actions: idle, walk, run, jump, attack, hit reaction, death, plus at least basic facial expression preview. These may be authored/test-permitted examples, not automatically sourced from the Fab account. **Later:** import/catalog/retarget 100+ animation clips.

## 9.2 Fab acquisition workflow

Your Fab animations are **not downloaded**. They must be acquired through your Epic/Fab account using supported export or Add-to-Project flows. Many products offer FBX or other exchange formats; Unreal-only `.uasset` assets do **not** expose a direct Fab export option and need Unreal-specific import/processing. The UCC scanner will index *local files* after download; it will not log into your Fab account, scrape paid files, bypass license controls, or treat unavailable cloud inventory as on-disk files.

Fab Launcher export guidance: https://dev.epicgames.com/documentation/en-us/fab/exporting-assets-from-fab-in-launcher

### Import order

1. Scan `.fbx`, `.glb`, `.gltf`, `.bvh` (supported conversion), and licensed source packages.
2. For `.uasset` animation clips: import into a matching Unreal project with required skeleton, then use Unreal Editor's supported animation export or a documented bake workflow (only if compatible with the asset license).
3. Store source product URL/ID, format, acquisition metadata, source skeleton fingerprint, reference pose and licensing status. Do not copy or expose proprietary files in a public repository.
4. Preview imported motion on a standard source skeleton before mapping.
5. Generate a human-reviewed source-to-target mapping; bake to destination rest pose; check feet/hands/root.
6. Separate source clip and retargeted derivative in the catalog; flag export policy.

## 9.3 Skeleton families

- MPFB default and MPFB+Rigify (verify generated bone names from actual installed release).
- Unreal 5 Manny/Quinn, Unreal 4 mannequin.
- Mixamo/Humanoid variants.
- GLTF canonical humanoid where declared.
- Dragon/quadruped/mechanical profiles later.

### Semantic bone map (illustrative)

```
humanoid/root
humanoid/pelvis
humanoid/spine_01 / spine_02 / chest / neck / head
humanoid/clavicle.L/R
humanoid/upper_arm.L/R / forearm.L/R / hand.L/R
humanoid/thigh.L/R / calf.L/R / foot.L/R / toe.L/R
humanoid/finger_{thumb,index,middle,ring,pinky}.{L,R}.{01,02,03}
```

Map actual rig bone names to **semantic IDs**. Bone hierarchy, rotation basis and bind matrices must be preserved as explicit metadata; matching names alone is insufficient.

## 9.4 Retargeting procedure

1. Evaluate source/target rest-pose difference; normalize unit scale and coordinate axes.
2. Build semantic map (including optional missing fingers); select `A→A`, `T→A`, etc. rest-pose correction.
3. For each frame, extract source local or global rotation quaternions, adjust into corresponding target bone rest frame, preserve translation only for configured root/pelvis channels.
4. Normalize translation by leg length or character height where appropriate; clamp known extreme proportions.
5. Apply FK motion; optionally solve IK feet/hands, floor contacts and root trajectory; do not blanket-use IK for all clips.
6. Bake to keyframes in a new action; evaluate quaternion discontinuity, foot slide, knee popping, hand drift and joint penetration.
7. Classify motion as `IN_PLACE` or `ROOT_MOTION`; ensure output settings match engine profile.
8. Preview, approve, tag, cache; preserve original imported animation.

### Clips and metadata

Organize by `locomotion`, `combat_unarmed`, `combat_melee`, `combat_ranged`, `spellcast`, `traversal`, `swimming`, `climbing`, `interactions`, `emotes`, `facial`, `hit_reactions`, `death`, and `secondary`. Attach usable-direction, loop, root-motion, motion speed, weapon hand, body type, source provider, and redistribution policy tags.

## 9.5 Editable timeline

- Clip selection, speed, reverse (when valid), trim, layer/mask blending, transition preview.
- Pose key editor, bones UI, root-motion visualization, onion-skin ghost pose.
- Bone groups with per-joint animation override; facial curve timeline.
- Non-destructive retarget bake; new action per edit, hash-based preview cache.
- Interaction checks for cloak/wings/tails, especially in 2D layer rendering.

## 9.6 Lip-sync

Define neutral face and viseme morphs (e.g. `AA`, `EE`, `IH`, `OH`, `OU`, `FV`, `MBP`, `L`, `rest`). Use audio timing or text phoneme alignment as a later provider, but ensure **facial mesh actually has working shape keys**; phoneme labels alone do not make a mouth animation. Export only morph targets that the destination supports, with a 2D facial-layer fallback. Include blink/gaze controls.

---
# 10. 2D / 2.5D / PIXEL-ART RENDERING

## 10.1 Reproducible camera profiles

A `SpriteCameraProfile` defines projection, yaw, pitch, roll, lens/orthographic scale, target anchor, framing margins, floor/ground shadow mode, alpha background, render engine, lighting and pixel rules.

Stock presets: side-facing left/right, 4-direction cardinal, 8-direction isometric/overhead, 16-direction, custom keyed camera orbit and perspective. All cameras may use custom angles, and presets are independently saved per character/export profile. Mirror-flipping should be *optional*: asymmetric equipment, hair and hand-held weapons may require real left and right renders.

## 10.2 Sample sprite export manifest

```json
{
  "schema_version": 1,
  "character_id": "demo-humanoid-001",
  "camera_profile": "isometric-8dir.v1",
  "resolution": {"width":128, "height":128},
  "render_fps": 12,
  "render_mode": "pixel-quantized",
  "alpha": true,
  "animations": [
    {"name":"idle", "direction":"S", "frames":8, "loop":true},
    {"name":"walk", "direction":"SE", "frames":8, "loop":true}
  ],
  "sheet": "sprite_sheet.png",
  "json": "sprite_sheet.json",
  "layers": ["torso", "head", "arms", "hands", "legs", "feet", "cape"],
  "anchor": {"x":64, "y":116},
  "color_profile": "sRGB"
}
```

## 10.3 Render steps

1. Load last approved `.blend`; apply game/character material and animation action.
2. Set frame range and exact frame sampling. FPS metadata and frame count must not be guessed from a GIF.
3. For each direction, render to a consistent fixed viewport and named path. Preserve camera-space floor/pivot anchoring across frames and proportional variants.
4. Generate transparent RGBA in linear->sRGB workflow; avoid colored matte fringes by using correct alpha convention.
5. At optional 2D-layer mode, render **each target part/mask separately** and generate per-frame draw-order information. Account for occlusion; independent part layers are not necessarily visually identical to a flattened beauty render.
6. Downsample using deliberately selected pixel-grid rules; quantize palette; optional ordered dithering and nearest-neighbor export; no bilinear smoothing after pixelation.
7. Crop/pad to cell size; preserve anchor and hitbox metadata; pack deterministic sheet positions.
8. Run sprite integrity tests; import into Godot/Unity/Unreal sample animation scene; send to Aseprite only if configured.
9. Keep intermediate high-resolution RGBA layers so the user can rerender or hand-correct without losing source.

### Rendering quality checks

- No blank/transparent frames where visibility is expected.
- Correct hands and feet in all cardinal directions; frame matching, limb occlusion and layering.
- No sheet overflow/overlap; exact frame count and stable animation pivot.
- Aseprite exporter metadata aligns with the PNG coordinates.
- Pixel grid constant across the entire sequence (avoid subpixel flicker).
- Palette is deterministic, with actual palette source recorded.
- Bounding boxes account for wings/capes/swords and extreme poses.
- Native resolution examples: 32, 64, 128, 256 pixels; additional values custom.

## 10.4 SNES-style vs high-detail presets

Both are *styles*, not exact copies of copyrighted game sprites:

- **SNES-inspired:** restrained palette, limited outlines, controlled anti-aliasing, crisp edges, pronounced keyposes, 12–24 fps source sampling as needed. Test 64–128 px tall character presentation depending on game camera.
- **High-detail pixel art:** bigger target canvas, more shades, richer texture detail; same stable-pixel-grid requirement.
- **Pixel-textured 3D:** nearest-neighbor texture filtering, constrained pixel density, stable UV layout; still uses fully rigged source model.

Rendering at low resolution alone is not sufficient for quality. Manual review and Aseprite retouching remain supported.

## 10.5 Aseprite external adapter

Official CLI supports batch execution (`-b`), sheet export (`--sheet`), metadata (`--data`, `--format json-array`), palette/color mode, layers and scripted Lua workflows. Aseprite can also read/edit generated PNG frames.

Example **for an existing `.aseprite` file**:

```powershell
& "C:\Tools\Aseprite\aseprite.exe" -b "C:\UCC\sprite_source.aseprite" `
  --sheet "C:\UCC\sprite_sheet.png" `
  --data "C:\UCC\sprite_sheet.json" --format json-array
```

This example does not build an `.aseprite` file from arbitrary layered PNGs by itself. A separate tested Lua/import extension or user-editing workflow is required for layered project generation. Avoid claiming native `.aseprite` writing from Blender alone.

Reference: https://www.aseprite.org/docs/cli/

---

# 11. ENGINE EXPORT PROFILES & ACCEPTANCE MATRIX

## 11.1 Canonical export stage

Canonical internal: `.blend` plus UCC project JSON; preview transfer: `.glb`. For each game engine, create profile-specific staged exports and an importer-side test project. No exporter is successful merely because its file exists.

| Check | Godot | Unreal | Unity |
|---|---|---|---|
| Preferred asset exchange | `.glb` / glTF 2.0 | `.fbx` skeletal mesh and clips | `.fbx` first, glTF adapter optional |
| Skeleton test | `Skeleton3D` bones + rest poses | SkeletalMesh skeleton hierarchy | Humanoid Avatar; Generic fallback |
| Animation test | `AnimationLibrary`/AnimationPlayer | AnimSequence; one clip per FBX when required | AnimationClip + Avatar / Animator |
| Face test | Blend shapes / morph animation | Morph targets | BlendShapes |
| Parts | Multiple skinned MeshInstance3D | Multiple skeletal mesh sections/attachments | SkinnedMeshRenderer/attachments |
| Root motion | explicit in-place or root tracks | root motion settings + pelvis audit | Avatar/root transform clips |
| Materials | PBR supported subset, variants baked | profile-specific materials/textures | URP/Built-in compatibility test |
| Units | meter scale + actual rendered height | Unreal scale normalization | Unity meter scale + root transform |
| Output proof | Godot smoke-test scene | Unreal import/PIE scene | Unity import/play-mode scene |

## 11.2 Godot adapter

- Export with Blender glTF 2.0 (GLB). Godot officially recommends glTF and supports animations, skeletons and morph targets. When exporting shape keys, review deformation-bones-only setting per current Godot guidance.
- In test project, inspect `Skeleton3D`, bone count/names, `MeshInstance3D` presence, animation clips and blend shapes; play idle/walk/attack. Validate no materials missing, no upside-down/root offset issue, no disappearing rig.
- Produce a simple `.tscn` character preview scene and a scene-import validation report if supported via local editor tools.
- For 2D, validate `AnimatedSprite2D` or `AnimationPlayer` with imported sheet and manifest, and `Sprite3D` for 2.5D.

Official documentation: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html

## 11.3 Unreal Engine adapter

- Export FBX from Blender using tested bone orientation, armature and scale profile. Bake independent animation actions to separate files when necessary.
- Engine FBX skeletal pipeline supports multiple UV sets, materials/textures, animations and morph targets; official docs note only one animation per SkeletalMesh file in the described workflow, so build **one-clip-per-file** as default.
- Import into a test project; inspect skeleton, morph targets, material references, bounding boxes, and AnimSequences; verify movement in Preview Scene/PIE.
- Add Manny/Quinn source skeleton import profiles and UE5 IK Rig/IK Retargeter compatibility later, after canonical MPFB retarget works.
- Do not assume Unreal-only Fab `.uasset` clips can be batch-converted externally without Unreal and license review.

Official: https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine

## 11.4 Unity adapter

- Prefer FBX for a robust Unity humanoid pipeline. Validate the imported mesh, Avatar's valid bone assignments, root transforms, animation clips, blend shapes and scale factor.
- If Avatar mapping fails due to missing anatomy, select Generic rig rather than silently discarding bones or motion.
- Support URP reference materials first, with a Built-in render pipeline fallback. HDRP can be an explicit later target.
- Test on a Unity import/play-mode scene with skeleton and facial morph controls.

**Exact Unity version:** detect installed release; pin supported major/minor only after practical testing.

## 11.5 Other formats

- **RPG Maker MZ:** 2D export of character/walk/damage/battler sheets with preset-specific naming, direction and frame layouts; 8/16 directions require compatible game plugins or custom runtime importer. Do not advertise eight-direction movement as built-in MZ behavior.
- **Lumina:** future explicit adapter once its asset/animation schema is provided; meanwhile UCC's JSON+GLB+spritesheet exports offer an engine-neutral handoff.
- **Spine-like layered animation:** export ordered PNG parts, per-bone/transforms and stable pivots; a true Spine `.spine` project requires an appropriately licensed writer/tool and is **not** a promised native output of v1.

## 11.6 Export gate

A profile is `PASSED` only when a deterministic import test checks geometry, skeleton, representative animation, at least one facial morph, texture presence, scale/orientation and successful playback in the target engine. If the engine isn't installed, status is `NOT_TESTED`, never `PASSED`. Distinguish `FILE_GENERATED`, `VALIDATED_OFFLINE`, `VALIDATED_IN_ENGINE`.

---

# 12. DESKTOP UI / UX SPECIFICATION

## 12.1 Main window

```
+-----------------------------------------------------------------------+
| Project | Create | Customize | Animate | AI | Render 2D | Export | Help|
+------------------+------------------------------------+---------------+
| Asset Browser    |                                    | Properties    |
| - Bases          |       INTERACTIVE 3D VIEWPORT      | - Body        |
| - Heads          |       orbit / pan / zoom           | - Face        |
| - Faces          |       pose / mesh gizmos           | - Material    |
| - Hands/Feet     |       overlays / rig debug         | - Part Fit    |
| - Clothes        |                                    | - Physics     |
| - Animations     |                                    | - Animation   |
| - AI Models      |                                    | - Export      |
+------------------+------------------------------------+---------------+
| Timeline / Animation Browser / Undo / Job Log / Errors / Progress      |
+-----------------------------------------------------------------------+
| Active: HumanoidV1 | MPFB: OK | Blender: OK | GPU Queue: idle          |
+-----------------------------------------------------------------------+
```

### Beginner mode

A guided row of tasks: **Base → Body → Face → Parts → Outfit → Animate → Export**. Labels should describe outcomes (“Make hands bigger”) rather than expose Blender target IDs. Provide presets, one-click camera view, Reset, Before/After and undo. AI generation remains opt-in and each application of AI output has a preview.

### Advanced mode

Dockable panels, mesh/object selection tree, bone/morph explorer, precise transforms, topology/weight diagnostics, rig mapping, camera profile, sheets and crop preview, asset source/provenance and job telemetry. Allow **Open in Blender** for editing when UI lacks a feature.

### Accessibility and reliability

- UI scalable at 100/125/150/200% DPI; keyboard shortcuts, readable labels and focus order.
- Progress bars for long jobs, cancel/retry and last-known-good preview.
- Explicit warnings for unsaved manual Blender changes before overwriting generated previews.
- Offline-first: missing AI server does not block human generation, manual assembly or exports.
- No inert buttons or fake modules. Features not implemented are hidden or visibly unavailable; never silently substitute a placeholder mesh.
- Save layouts per display profile; restored dock layout must not position windows off-screen.

## 12.2 3D viewport requirements

Use local bundled Three.js with glTF loader and animation playback. Picking meshes must map back to stable UCC part IDs. Transform gizmos modify constraints/commands, not arbitrary GLB node transforms that disappear on regeneration. Provide skeletal/bone overlay, symmetry toggle, A-pose, T-pose, animated preview, material preview and screenshot.

Qt WebEngine should load only bundled/local trusted UI content with a strict bridge API. Do not expose unrestricted Python method execution from JavaScript; use a typed message bridge that whitelists character-edit commands. Avoid navigation to untrusted URLs inside the privileged editor webview.

---

# 13. SECURITY, RELIABILITY AND LICENSING

## 13.1 Plugin and model safety

- Restrict AI servers to loopback unless a user explicitly authorizes remote access and configures authentication/TLS.
- Treat ComfyUI workflow JSON and custom nodes as code-adjacent untrusted inputs: scan dependencies and require explicit installation approval. Do not automatically install arbitrary third-party custom nodes.
- Avoid `pickle.load`, arbitrary `torch.load` and any executable parsing in the asset scanner. For unknown formats report metadata only.
- Do not evaluate user text prompts as Python/JS/Blender expressions or shell arguments.
- Validate all file paths under explicit scan/write roots; prevent directory traversal in model download zip extraction, job output naming and export profiles.
- Free-download installer must show provenance, license, expected file size/hash if published, destination, confirmation, and no replacement of existing executable without backup.
- Isolate subprocess working directories and sanitize temporary files after successful approval.

## 13.2 Third-party asset provenance

A `LicenseRecord` includes:

```
provider, product_id/url, creator, license_name, license_url,
acquired_by, acquired_at, original_filename, original_sha256,
allowed_use_flags, no_ai_training, ue_only_or_legacy,
can_repackage_source, public_export_classification, notes
```

Unknown license defaults to **non-distributable** until reviewed. Do not confuse *permitted use inside a game* with *permission to distribute an editable animation pack or character creator library*. Do not train generative AI on Fab NoAI assets or treat a renamed/baked copy as automatically exempt. Internal private use, publishing game binaries, selling characters and shipping the creator have different license gates.

Reference: Fab Standard License https://www.fab.com/eula?lang=en ; Fab documentation https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab

## 13.3 Open source licensing

- **MPFB** code is GPL-3.0-or-later, bundled core assets CC0. Third-party MakeHuman asset downloads can have their own licenses. Keep full license notices; maintain a code boundary, but conduct expert license review before shipping a closed-source app integrating GPL functionality.
- **Blender** is GPL software and remains an external tool; user-generated files are not automatically GPL solely because Blender created them.
- **PySide6** community bindings and Qt modules have LGPL/GPL obligations; some Qt modules differ. Evaluate dynamic linking, notices and redistribution obligations; a commercial license is an option if unable to comply.
- **Aseprite** may be built from source for personal use; do not bundle or redistribute a self-compiled executable contrary to its license. Keep integration user-configured.
- **AI model licenses** and cloud terms vary. Track checkpoint/source usage rights; no auto-public redistribution of user models.

This section is an engineering compliance checklist, not legal advice.

## 13.4 Failure and edge-case matrix

| Failure/edge case | Expected behavior |
|---|---|
| Blender missing or wrong version | Clear diagnostics; continue project browsing/offline reference operations; disable Blender-dependent actions. |
| MPFB installed but not enabled in background | Report attempted registration, module/extension identifier, relevant operator check and log; fallback to guided GUI test. |
| MPFB operator requires 3D VIEW context | Do not pretend operation succeeded; create documented UI context or use verified service API, with regression test. |
| Blender crashes during geometry change | Preserve previous master and staged snapshot; show worker log; allow retry. |
| Incompatible hand/arm rig | Reject attachment or require explicit mapping; do not silently attach unskinned mesh. |
| Extra bones from imported animation | Map supported semantics, preserve or explicitly omit with warnings; preview deformation. |
| Different skeleton rest poses | Compute rest-pose correction before baking; no simple filename-based matching. |
| Missing face morphs in export | Mark capability failure; provide fallback face bake/2D layer export. |
| GPU OOM | Free model cache and retry lower-memory workflow if user approves; do not crash desktop app. |
| ComfyUI offline | User may work with existing presets, Blender, sprites; provider status = offline. |
| Unsupported ComfyUI node in workflow | Fail preflight and list node dependencies; never silently replace nodes. |
| User scans C:\ or whole system | Estimate, exclude system/reparse paths, show progress, cancel, avoid privilege escalation. |
| Windows drive removed mid-scan | Mark inaccessible paths and continue remaining roots; don't delete index metadata blindly. |
| Duplicate checkpoints under differing names | Content hash when feasible; retain per-path records and warn on duplicates. |
| Cloud AI enabled without consent | Block upload; require per-provider approval and clear destination. |
| Fab asset says UE Only / legacy | Restrict compatible export workflows; log exact source license and manual review. |
| Unknown license | Private project use only if authorized; no public export packaging until classified. |
| Renders have transparent pixels at boundaries | Use straight-alpha consistent output and inspect edge tests to prevent halos. |
| Sprite overflow due to cape/weapon | Auto fit camera to max pose envelope, or warn user instead of clipping. |
| Negative scale / mirrored hand | Apply verified transforms or regenerate handed mesh; detect inverted normals. |
| Shape key lost due to topology-changing modifier | Reject destructive modifier or bake morph variants before topology changes. |
| User upgrades Blender/MPFB | Run compatibility migration tests, preserve prior worker profile and projects. |
| Export `SUCCESS` but game import broken | Mark `FILE_GENERATED`, not `VALIDATED_IN_ENGINE`. |
| Project saved on OneDrive/network path | Use local staged writes, retry atomic move semantics with warnings, avoid corrupting master. |

---
# 14. REPOSITORY LAYOUT — IMPLEMENTATION CONTRACT

```
universal-character-creator/
  README.md
  LICENSES.md
  CONTRIBUTING.md
  pyproject.toml
  uv.lock                           # if uv chosen; lock real resolved versions
  .gitignore
  .gitattributes
  docs/
    UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md
    decisions/
      ADR-0001-requirements.md
      ADR-0002-blender-worker.md
      ADR-0003-character-and-rig-schema.md
    schemas/
      character-project.v1.schema.json
      part-asset.v1.schema.json
      animation-asset.v1.schema.json
      worker-job.v1.schema.json
      sprite-export.v1.schema.json
    integration/
      mpfb-compatibility.md
      comfyui.md
      automatic1111.md
      fab-import.md
      aseprite.md
      godot.md
      unreal.md
      unity.md
  src/ucc/
    __init__.py
    desktop/
      app.py
      main_window.py
      beginner_mode.py
      advanced_mode.py
      docks/
      controls/
    core/
      character.py
      anatomy.py
      part_slots.py
      morphs.py
      rig_semantics.py
      validation.py
      commands.py
      undo.py
      project_io.py
      schema_migrations.py
    database/
      schema.py
      migrations/
      repository.py
    library/
      indexer.py
      model_discovery.py
      signatures.py
      provenance.py
      licensing.py
    jobs/
      scheduler.py
      resource_gate.py
      worker_dispatch.py
      persisted_state.py
    blender/
      subprocess_client.py
      contracts.py
    ai/
      providers.py
      comfyui_client.py
      webui_client.py
      prompts.py
      graph_validator.py
      workflow_registry.py
    animations/
      catalog.py
      semantic_bones.py
      rest_pose.py
      retarget.py
      curve_baker.py
      validation.py
    sprites/
      cameras.py
      render_plan.py
      frame_postprocess.py
      packing.py
      layer_manifest.py
    export/
      profiles.py
      godot.py
      unreal.py
      unity.py
      common.py
      report.py
    settings.py
    logging_setup.py
  blender_bridge/
    entrypoint.py
    runtime_info.py
    op_create_human.py
    op_set_targets.py
    op_attachments.py
    op_rig.py
    op_animation.py
    op_preview.py
    op_export.py
    op_render.py
  ui_web/
    package.json
    package-lock.json
    src/
      app.ts
      viewport.ts
      selection.ts
      orbit.ts
      gizmos.ts
      bridge.ts
    public/
    dist/                            # bundled offline build, not CDN
  tools/
    audit_local.py
    mpfb_smoke.py
    export_verify.py
    collect_diagnostics.py
  tests/
    unit/
    schema/
    contracts/
    integration/
      test_blender_mpfb.py
      test_comfyui.py
      test_webui.py
      test_aseprite.py
    engine/
      godot/
      unreal/
      unity/
    snapshots/
  test_assets/
    README.md                       # source/license manifest for all fixtures
  scripts/
    windows/
      setup-dev.ps1
      run-dev.ps1
      check-tools.ps1
  packaging/
    windows/
  .github/workflows/
    ci.yml
```

`pyproject.toml` should enforce `ruff` (lint/format), `mypy` or Pyright (critical typed areas), `pytest`, JSON schema validation, and reasonable dependency pinning. Keep modules focused; target ~300–500 LOC per file and split earlier if responsibilities diverge. UI, domain services, Blender and AI adapters must not be blended into one giant file.

---

# 15. IMPLEMENTATION ROADMAP — STRICT ORDER, WITH EXIT CRITERIA

No parallelism before shared contracts are pinned. These are **dependency stages**, not promises that each stage takes a particular number of hours.

## Stage 0 — Preflight and dependency smoke tests (P0, blocking)

**Deliverables:** `tools/audit_local.py`, pinned compatibility document, clean Git repo, first environment snapshot.

Tasks:

- [ ] Detect Blender 5.3 executable; confirm CLI startup and Python version.
- [ ] Confirm MPFB 2.0.18 installation in GUI; test headless `mpfb.create_human` or verified service call.
- [ ] Test create/save/reopen `.blend` and inspect mesh/bone/shape-key presence.
- [ ] Detect Aseprite binary and version; do **not** update source automatically in initial scan.
- [ ] Probe ComfyUI and SD WebUI at configured addresses without altering their settings.
- [ ] Scan only selected folders for AI models; produce JSON inventory.
- [ ] Check GPU VRAM and local disk capacity; log without sharing exact local paths by default.
- [ ] Document licenses for every installed dependency.
- [ ] Create `test_assets/README.md` with allowable source assets and restrictions.

**Exit:** one actual MPFB human generated and saved/reopened under Blender 5.3; machine-readable report; no unsupported assumptions. If MPFB GUI works but background mode fails, build a temporary verified foreground worker bridge *within Stage 0*, not a whole new human generator.

## Stage 1 — Core data model and desktop shell

**Deliverables:** `CharacterProject`, `PartAsset`, `AnimationAsset`, `LicenseRecord`, command stack, file manager, SQLite migration, basic Qt GUI.

Tasks:

- [ ] Implement validation schemas, versioning and migrations.
- [ ] Implement save/load/autosave with atomic transaction and rollback.
- [ ] Build simple desktop shell with navigation, status/docks and logs.
- [ ] Implement Blender worker dispatch and stable request/result protocol.
- [ ] Implement viewport GLB load, orbit, selection map and screenshot.
- [ ] Add beginner and advanced workspaces.
- [ ] Implement cancellable job queue; progress, result, retry and log inspection.

**Exit:** open a *real MPFB character*, preview GLB, save, close, reopen with identical state, run Blender inspection without UI freezing; induced worker failure does not damage project.

## Stage 2 — Working humanoid creator (first full character experience)

**Deliverables:** MPFB human creation, body/face slider mapping, safe part variants, rig, preview and basic actions.

Tasks:

- [ ] Generate human via tested MPFB adapter; persist MPFB source recipe.
- [ ] Register and test height, build, age-related shape controls where appropriate and legal by available MPFB targets.
- [ ] Build anatomy slot UI including independent face, finger/toe and optional slot definitions.
- [ ] Create at least one **real, compatible** interchangeable part category beyond default MPFB base (e.g. eyes/ears or hand variants); require fit/pose checks.
- [ ] Add symmetry/asymmetry, reset and undo.
- [ ] Generate/choose tested humanoid rig; inspect bone semantics and weights.
- [ ] Load working idle/walk/run/jump/attack/hurt/death clips from authorized test sources.
- [ ] Implement basic facial expression preview (where the actual mesh supports shape keys).
- [ ] Add reference-image import; wire at least one verified ComfyUI concept-generation flow when compatible models exist; AI backend absence must not block completion.

**Exit:** a user who cannot model can create, change, pose, animate, save and reopen a unique, properly skinned humanoid; no shipping placeholders.

## Stage 3 — Complete first-milestone exports (required)

**Deliverables:** Godot, Unreal and Unity profiles with actual engine-side smoke tests; elementary 2D output.

Tasks:

- [ ] GLB export and in-engine Godot test scene.
- [ ] FBX rigged export and in-engine Unreal test scene.
- [ ] FBX humanoid/generic import, Avatar check and play-mode Unity test scene.
- [ ] Record bone scale, axis, root-motion, material and shape-key tests.
- [ ] Render transparent sprites for at least one motion, minimum two camera angles, two resolutions.
- [ ] Export sprite sheet + JSON and verify metadata vs image dimensions.
- [ ] Produce export quality/compatibility report visible in GUI.

**Exit:** the same source character plays and visually deforms correctly in Godot, Unreal and Unity; produces reproducible PNG frames/spritesheet; failures reported accurately.

**MILESTONE 1 COMPLETE:** Creator working; one tested customizable humanoid; three engine checks; initial sprite workflow; basic animations. No forced 100+ clips, nonhuman mesh generation, or fictional AI retopology pipeline.

## Stage 4 — Animation catalog + 100+ clip goal

**Deliverables:** indexer for downloaded Fab/source animations; semantic profiles, retarget, clip categories, searchable animation preview.

Tasks:

- [ ] Build permitted Fab acquisition instructions; record license per pack and format.
- [ ] Index local FBX/GLB/BVH and Unreal extraction outputs; parse duration/FPS/bone names and tags.
- [ ] Skeleton-type identification plus confidence/warnings.
- [ ] Build MPFB⇔UE5 mannequin/Manny, UE4 and Mixamo mapping profiles as actual rigs permit.
- [ ] Add rest-pose correction, scale, IK foot stabilization, root-motion in-place/baked support.
- [ ] Bake retargeted clips, validate and batch-import with cancellation.
- [ ] Reach **100+ licensed, usable, indexed clips** as available, but count `RENDER_PREVIEW_OK`, `RETARGETED`, and `ENGINE_VALIDATED` separately.
- [ ] Add timeline blending, preview comparisons, basic manual fixes and tags.

**Exit:** importing different skeleton families produces real retargeted clips rather than only files in a catalog. The catalog states accurately how many passed target-rig and target-engine checks.

## Stage 5 — Complete sprite and pixel-art system

**Deliverables:** adjustable orthographic/custom cameras; 4/8/16-direction rendering, multi-resolution, alpha, sheet packing, per-part layers, Aseprite roundtrip.

Tasks:

- [ ] Render angle matrices and deterministic frame sampling.
- [ ] Implement pixel palettes/dithering, crisp-cell registration and motion pivot lock.
- [ ] Build per-part masks, occlusion/order metadata and editable layer exports.
- [ ] Test Aseprite CLI from existing install and hand-edit roundtrip.
- [ ] Add Godot/Unity/Unreal sprite usage examples and RPG Maker MZ preset.

**Exit:** stable 2D/2.5D assets match source motion, with a correctly indexed sheet, consistent camera/pivots and reusable edit layers.

## Stage 6 — AI modular art and part creation

**Deliverables:** local/opt-in cloud AI concept tools, high-quality texture/reference workflows, topology-checked AI-assisted part proposal.

Tasks:

- [ ] Model discovery with folders/drive/global modes; dependency and license assessment.
- [ ] ComfyUI workflow gallery; model compatibility and VRAM preflight.
- [ ] Prompt-to-reference, reference-to-variant, multiview concept and texture options.
- [ ] Create a **review-only** image-to-mesh adapter if a suitable free/local model is viable; never auto-commit bad topology.
- [ ] Implement fit/weight/seam quality scores and human-approval preview.
- [ ] Add cloud provider plugins only with explicit per-provider consent.

**Exit:** AI-derived parts can be generated as proposals, converted with validated geometry operations where possible, inspected and attached without silently breaking rig or saved project.

## Stage 7 — Character family expansion and public-release hardening

**Deliverables:** quadruped/dragon/mechanical adapters, additional facial/motion systems, license compliance, installer and stable/beta channels.

- [ ] Separate family definitions, species-specific joints, slots and movement types.
- [ ] Wings, tails, capes, secondary animation rigs and physics bake.
- [ ] Different skeletal structures/retarget constraints; nonhuman animation library.
- [ ] Model-quality automation and lower-LOD variants.
- [ ] License review for packaged software, third-party content and model packs.
- [ ] Create installer/updater, signed builds if distributing, recovery and crash reporting (opt-in diagnostics).
- [ ] Complete UX/accessibility and broad hardware compatibility testing.

---

# 16. TEST STRATEGY, QUALITY GATES AND RELEASE CRITERIA

## 16.1 Test classes

1. **Pure unit:** schema, dependency resolver, socket rules, math, provenance, licensing gates, render-frame packing.
2. **Property-based / fuzz:** odd Unicode paths, very long names, empty parts, duplicate IDs, NaN morph values, illegal graph cycles, malformed animation keyframes.
3. **Integration:** Blender/MPFB creation, morph generation, save/reopen, part swap, GLB export and Blender reimport.
4. **AI mock + live opt-in:** ComfyUI endpoint error, invalid graph, workflow progress/outcomes, offline recovery, model discovery.
5. **Engine smoke:** Godot headless/editor import + scene playback if possible; Unity batch-mode import/Avatar checks where available; Unreal editor automation; screenshots and reports. Engine UI/manual inspection remains required where headless APIs cannot verify deformation quality.
6. **Golden visual regression:** selected views at idle, full stride, shoulders, knees, fingers, mouth morph and cape overlap. Store only license-cleared images; compare with tolerances.
7. **Safety:** malicious paths, model metadata, workflow JSON, zip entries, remote endpoints, subprocess injection, cancellation, timeouts and resource limits.
8. **Regression:** 39 locked requirements tracked as functional tests or future-stage acceptance items.

## 16.2 Required smoke matrix

| Test | Scene / specimen | Pass check |
|---|---|---|
| MPFB generate | Neutral body | Real geometry, a stable project, editable morphs |
| Morph | Short/tall, slender/heavy | No self-intersecting catastrophic deformation; rig stays usable |
| Modular swap | Tested hand/face part | Correct socket, deform weights, geometry remains stable |
| Rig | A-pose, T-pose, 20 selected motions | No bone mismatch or broken skin |
| Facial | Blink/viseme sample | Named morphs present, usable at runtime |
| Animation | Idle/walk/attack | Correct root behavior, loop and foot contacts |
| Godot | Imported character scene | Skeleton present, motion and morph play |
| Unreal | Skeletal Mesh + animation | Imports, plays, correct scale and morphs |
| Unity | Humanoid / Generic | Avatar valid or explicit Generic; clips play |
| 2D | Eight-direction walk, 64 and 128 px | Sheet frames/angles/pivots stable |
| Restart | Save and reopen after all edits | No lost parts, keyframes, provenance or settings |
| Failure | Kill Blender mid-export | Master intact; failed staged output not committed |
| Offline AI | Stop ComfyUI | Manual creator remains functional |

A test may be `SKIPPED` only with an explicit reason (e.g. engine not installed). Never present skipped engine checks as successful compatibility.

## 16.3 CI expectations

GitHub Actions or equivalent can run lint, type check, schema validation and core tests on every PR. Blender integration tests may run in a dedicated licensed/test-clean self-hosted worker or local runner; exclude user-owned Fab files and checkpoint models. Engine jobs may be nightly/manual on an appropriately provisioned Windows machine. CI shouldn't download multi-gigabyte unlicensed models just to satisfy a commit check.

## 16.4 Measurable UX targets (targets, not measured facts)

- No UI freeze on long Blender or AI jobs; progress/control responsive throughout.
- Save/reopen tests preserve all character IDs and source links, excluding deliberately regenerated cache IDs.
- 100% of engine exports visibly distinguish file-generation success from successful in-engine validation.
- Each Blender/AI operation produces structured diagnostics and actionable failure messages.
- Users can work offline with previously acquired assets and without any cloud sign-in.

---

# 17. CODING AGENT PLAYBOOK

This section is written so a coding agent can implement the project sequentially without repeatedly rebuilding it from scratch.

## 17.1 Operating rules

1. Read this specification and current repo before changing anything. Confirm actual path, installed tool versions and existing work rather than inventing installations.
2. Start with **Stage 0**; create an ADR for any necessary deviation. Do not proceed to full UI before MPFB 5.3 compatibility is tested.
3. **No placeholders in shipped functionality.** If a feature depends on unavailable paid/source assets, implement a validated import interface and mark it pending rather than inventing a successful asset.
4. Preserve existing files and user data; write migrations, backup and tests before high-risk format changes.
5. Restrict changes per PR to a coherent vertical slice. Prefer small modules (roughly 300–500 LOC), pure functions and explicit contracts.
6. Add/execute lint, type checks and tests for all modified logic. Describe unrun integration tests honestly.
7. Track asset provenance and licensing from day one. Never commit third-party paid content or private AI checkpoints.
8. Use low-cost local reasoning/agents for routine tasks, escalate only for architectural or hard debugging. Avoid redundant parallel agents and speculative broad exploration.
9. Maintain an `IMPLEMENTATION_STATUS.md` mapping completed work to acceptance criteria; record next step and blockers after each task.
10. Do not ask for unprovided assets prematurely. First build workflows that operate using real, installed MPFB output and authorized free test assets; when Fab downloads are necessary later, surface precise product/format requirements.
11. Preserve user control over AI backend selection, scanned directories and software downloads.
12. Do not start over to fix isolated architectural debt; write migrations/refactors and keep milestones intact.

## 17.2 Required PR/task format

```
TASK ID: UCC-P0-001
GOAL: Verify Blender 5.3 and MPFB are callable from a worker.
INPUTS: Installed blender.exe + MPFB extension path.
FILES: tools/mpfb_smoke.py; blender_bridge/runtime_info.py; docs/integration/mpfb-compatibility.md
STEPS:
  1. Query installed versions and addon/operator registration.
  2. Test actual MPFB human creation in GUI and background modes.
  3. Save and reopen a project, compare scene signatures.
  4. Record operator and context restrictions, logs and tested settings.
TESTS: Real blender subprocess smoke; report structured JSON.
ACCEPTANCE: Save/reopen human and nonzero geometry proof.
FAILURE: Document confirmed blocker, do not mark successful.
DEPENDENCIES: None.
```

Each future task must have a definition of done, dependencies, files, exact tests and a proof artifact. Prefer one coherent change at a time. No untracked changes to source files outside scope.

## 17.3 Initial 12-task backlog

| ID | Task | Must pass before next |
|---|---|---|
| UCC-P0-001 | MPFB/Blender version and operator spike | Actual human creation and save/reopen |
| UCC-P0-002 | Dependency/license audit and model inventory | Accurate local findings; no hidden downloads |
| UCC-P0-003 | Worker JSON protocol and crash recovery | subprocess success, failure and timeout tests |
| UCC-P1-001 | Schemas, project storage, migrations | roundtrip + rollback unit/integration tests |
| UCC-P1-002 | Qt shell, status, workspace and settings | opens without AI, can browse project |
| UCC-P1-003 | Three.js GLB viewport and command bridge | selects real part via ID, orbit and screenshot |
| UCC-P1-004 | MPFB body target/sliders UI | physical changes persist after reopen |
| UCC-P1-005 | Part inventory/attachment validation | safe swap + undo + posed verification |
| UCC-P1-006 | Rig and test clip import | idle/walk/action on humanoid without breakage |
| UCC-P1-007 | Godot GLB pipeline | validated in editor scene |
| UCC-P1-008 | Unreal FBX + Unity FBX pipelines | validated both engines |
| UCC-P1-009 | RGBA frame/sheet export | reproducible sprites and metadata |

Follow the tasks in order unless a verified dependency forces a recorded adjustment.

## 17.4 First coding-agent instruction (copyable)

> Implement Stage 0 of `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md` only. Audit the installed Windows/Blender/MPFB/ComfyUI/Aseprite environment. Create a typed JSON worker protocol, a read-only diagnostic command, and a real Blender 5.3 + MPFB smoke test that creates an editable humanoid `.blend` and reopens it. Do not create the full UI, do not install extra AI checkpoints, do not fabricate MPFB API calls, do not substitute a dummy mesh, and do not claim passing tests without actual Blender execution. Keep modules focused, include automated tests and logs, document any blocked step, and provide a concise next-task plan based on observed results.

---

# 18. WINDOWS INITIAL SETUP AND FREE SOFTWARE POLICY

**Already known:** Blender 5.3, Aseprite, ComfyUI, Stable Diffusion WebUI, RTX 3060 12 GB. Do not download duplicates without a version check.

1. Verify Python, pip/uv, Git, Blender and Aseprite paths. Select the installed executable explicitly in application Settings.
2. Install MPFB through the official Blender Extensions entry **after** checking whether it is already installed. Official: https://extensions.blender.org/add-ons/mpfb/
3. Keep ComfyUI and SD WebUI where currently installed. UCC should connect to their existing APIs rather than downloading new installations.
4. Use the provided **read-only environment audit** to list candidate paths and local API responsiveness. Model discovery starts selected-folder only; offer a separate explicit drive scan later.
5. Updating existing Aseprite source: verify Git working tree is clean, back up local edits and current executable, then perform official `git pull` + `git submodule update --init --recursive` and rebuild using the instructions appropriate to its current Skia/VS configuration. Never overwrite a user's working Aseprite binary without review. Guide: https://github.com/aseprite/aseprite/blob/main/INSTALL.md
6. Future optional free components must have provenance, actual version, tested hardware support and license review before download; do not prescribe large 3D foundation models for RTX 3060 solely from marketing claims.

Suggested dev commands (once the repository exists and Python environment is selected):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install pyside6 pyside6-addons pytest ruff pydantic httpx
.\.venv\Scripts\python.exe -m pytest
```

These are **development setup examples**, not a tested lockfile. Do not run until dependencies and distribution/license strategy are reviewed. Avoid bulk-installing duplicate PySide6 package variants; version-pin and lock after the first successful compatibility pass. Qt WebEngine is a module to test explicitly on Windows.

---

# 19. OPEN ARCHITECTURE QUESTIONS THAT REQUIRE TESTS, NOT MORE USER ANSWERS

These are engineering findings to resolve automatically during development:

- MPFB 2.0.18's precise background registration/API behavior on Blender 5.3.
- MPFB rig/shape-key names and whether its default generated rig meets Godot/Unreal/Unity humanoid expectations.
- Which Qt WebEngine + Three.js versions package smoothly together under chosen license conditions.
- Exact free/allowed animation clips available for first-mile integration; a sparse authorized test pack is sufficient.
- Where existing ComfyUI checkpoints reside, and which API-format workflow templates their installed node set supports.
- Whether both image systems can be run on 12 GB VRAM without resident model contention; automate queue management and ask before unloading external work.
- Best non-destructive pipeline for detachable limb border geometry.
- Which user-owned Fab clips offer actual downloadable FBX as opposed to Unreal-only content.

These should become **discovery tasks and regression tests**, not a 40th-round questionnaire.

---

# 20. SOURCE DOCUMENTATION AND VERIFICATION LINKS

The sources below were checked while preparing this blueprint on 2026-11-11. Product releases, docs and licenses may evolve; rerun compatibility checks before shipping.

1. Blender 5.3 release (Nov. 10, 2026): https://www.blender.org/press/blender-5-3-release/
2. Blender 5.3 Python API: https://developer.blender.org/docs/release_notes/5.3/python_api/
3. MPFB official extension 2.0.18: https://extensions.blender.org/add-ons/mpfb/
4. MPFB versions/compatibility: https://extensions.blender.org/add-ons/mpfb/versions/
5. MPFB human-create operator docs: https://github.com/makehumancommunity/mpfb2/blob/master/docs/ui/new_human/newhuman.md
6. MPFB software/asset license: https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md
7. ComfyUI HTTP/WebSocket endpoints: https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx
8. ComfyUI official API example: https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example.py
9. Stable Diffusion WebUI API implementation: https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/api/api.py
10. Aseprite CLI: https://www.aseprite.org/docs/cli/
11. Aseprite source build/update: https://github.com/aseprite/aseprite/blob/main/INSTALL.md
12. Aseprite GitHub releases: https://github.com/aseprite/aseprite/releases
13. Fab Standard License: https://www.fab.com/eula?lang=en
14. Fab license categories/legacy licensing: https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab
15. Fab Launcher export/import procedure: https://dev.epicgames.com/documentation/en-us/fab/exporting-assets-from-fab-in-launcher
16. Godot supported 3D formats: https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html
17. Unreal skeletal mesh import pipeline: https://dev.epicgames.com/documentation/en-us/unreal-engine/fbx-skeletal-mesh-pipeline-in-unreal-engine
18. Unity 6 rig importer: https://docs.unity.com/en-us/engine/6000.0/manual/assets-and-media/asset-types/models/importing/fbximporter-rig
19. Unity 6 humanoid animation/Avatar import: https://docs.unity.com/en-us/engine/6000.0/manual/assets-and-media/asset-types/models/importing/configuringthe-avatar
20. PySide6 licensing and documentation: https://doc.qt.io/qtforpython-6/

---

# 21. FINAL IMPLEMENTATION DIRECTIVE

**Start with real MPFB integration, not UI polish or unsupervised AI-generated character meshes.** The project succeeds only if a non-artist can generate a legitimate editable human, adjust features, animate it, reopen it, and import it successfully into all three target engines. Once that is proven, invest in 100+ retargeted animations, advanced pixel-art styles and new anatomical character families.

**Best next work item:** `UCC-P0-001` — audit and smoke-test Blender 5.3 + MPFB 2.0.18 on the actual Windows machine. This is the critical dependency and determines the feasibility of the rest of the first milestone without a major rewrite.
