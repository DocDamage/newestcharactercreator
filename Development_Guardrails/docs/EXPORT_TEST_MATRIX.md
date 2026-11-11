# Engine-Ready Export Validation Matrix

**A file on disk is not a pass.** Use a fresh test project in the actual destination engine and preserve logs/screenshots and a manual deformation review.

## Standardized test character

One actual MPFB-derived editable human with a representative body morph, swappable part, body rig, facial expression and at least idle + walk + one large-deformation motion (e.g., crouch/attack). Use a small **licensed or self-made** animation set; Fab acquisition is not required yet. Export the same master revision to all engines. Record all versions and a SHA-256 for each source/export.

## Cross-engine tests

| Area | Godot | Unity | Unreal |
|---|---|---|---|
| Format | GLB/glTF | FBX or validated glTF importer | FBX skeletal mesh |
| Scale | Known meter-height | Known humanoid scale | Known cm/world scale |
| Axis/orientation | Correct model forward/up | Correct avatar forward/up | Correct model forward/up |
| Skeleton | Named deform bones, no losses | Humanoid mapping or Generic rig, verified | Correct skeleton + retarget workflow |
| Animation | Idle/walk playback, feet planted | Clip playback, no root jumps | Sequence playback, proper root and skeleton |
| Skinning | Elbow/knee/wrist/face range | Same | Same |
| Materials | Visible textures and alpha | Same | Same |
| Facial | Named morphs where supported | Blendshape bindings | Morph targets |
| Attachments | Swapped part stays attached | Same | Same |

For every engine record: import asset name, engine version, imported mesh/bone/clip counts, missing texture list, warnings, observed scale, visual screenshots/video showing extreme deformation, and actionable failures. Differences should be explicit per-target adapters, not modifications to the master mesh.

## 2D checks

- Render fixed orthographic camera, selectable camera origin, custom azimuth/elevation, 4/8/16/custom directions.
- For each resolution (e.g. 32, 64, 128, 256 and custom), validate actual frame dimensions, frame ordering and transparency.
- Record stable pivot, frame duration, action name, direction tags, hitboxes/anchors, optional component layers and metadata JSON.
- Verify silhouette, clipping and frame consistency; pixelation is **not** automatic artist-grade pixel art. Flag cleanup tasks for Aseprite.

## Root motion / retarget pitfalls

Mismatch between Blender rest pose and FBX export, distorted limbs, mirrored scale, orphaned bones, quaternion flips, wrong unit conversions, IK-only controls masquerading as deform bones, missing root motion, and incompatible animation skeletons are blocker conditions. Do not silently mark them resolved by baking all transforms without tests.

## Video and screenshots

Captured evidence may include copyrighted third-party animations; keep it private unless authorized. Do not publish purchased Fab source assets in demo repositories or installers.
