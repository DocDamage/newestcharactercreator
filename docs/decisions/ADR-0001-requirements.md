# ADR-0001 — Locked character creator requirements

Status: recorded from the approved blueprint; requirements unchanged.

This file preserves section 1 of `UNIVERSAL_CHARACTER_CREATOR_BLUEPRINT.md`,
as that specification explicitly requires. It introduces no new architecture
decision, stack change or release approval. Changes require a deliberate ADR and
user authorization under AGENTS.md.

Blueprint SHA-256 at recording: `4de9f64fff149250d9c776bd72e3c8d530fc9553b628c9aa7568b786b5a4733e`.

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
