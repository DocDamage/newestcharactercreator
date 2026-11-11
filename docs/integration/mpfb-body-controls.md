# Saved Height, Muscle and Weight → actual MPFB macro targets

**Increment:** [PR #27](https://github.com/DocDamage/newestcharactercreator/pull/27), after merged PR #26. The first body-editing step applies the existing normalized UCC Height/Muscle/Weight values to the **next generated MPFB humanoid**. It is an explicit regeneration workflow, not live re-sculpting of an arbitrary existing Blender file.

## Using the feature

1. Open/create a UCC humanoid project with no attached parts or animation references.
2. Adjust the three sliders in **Character → Body phenotype controls**. Each value is normalized from 0.0 to 1.0, **not** centimeters/meters, kilograms, or a target athletic measurement.
3. Choose **File → Save metadata** (Ctrl+S). The next Blender job deliberately reads the saved `project.ucc.json`, not draft unsaved slider positions.
4. Click **Generate humanoid using saved body controls...** and confirm the exact values in the dialog. Choose your installed Blender binary with MPFB enabled.
5. UCC uses MPFB `TargetService.get_default_macro_info_dict()` to retain all other traits at their documented defaults, changes only Height/Muscle/Weight, then calls `HumanService.create_human(macro_detail_dict=...)` and `add_builtin_rig(..., "default")`.
6. A second isolated Blender process reopens the saved master and independently verifies macro property read-back, active shape keys, evaluated mesh vertex count and a SHA-256 fingerprint of the real evaluated vertex coordinates.
7. Only after those tests pass will the master be staged as a new immutable `master/versions/<sha>.blend` and the saved UCC metadata revision advanced. **Preview saved master in UCC** may then display the newly generated shape after an explicit Blender-to-static-GLB conversion.

**Regeneration warning:** Generating again builds a new MPFB base from the saved three values. It does not modify an old `.blend` in-place, copy manual Blender mesh edits, or guarantee that attached equipment will fit. Older immutable masters remain available. Projects containing part or animation references are blocked until compatibility can be validated.

## Security / accuracy boundaries

- Exactly three explicit finite numeric values in 0–1 are allowed; no unknown target names, file paths, command strings, scripts, non-finite values, boolean coercion or extra MPFB attributes.
- No network, AI processing, Fab asset scan, model download, target installation or arbitrary user-supplied MPFB plugins are performed. MPFB must already be enabled.
- Worker creation and independent inspect use separate Blender subprocesses with `--disable-autoexec`. Source hashes, project identity/revision and cancellation are rechecked before committing.
- Actual evaluated mesh coordinates are inspected, not merely metadata. Matching Blender roundtrips establish consistent **static shape changes**, not verified rest-pose skin weights, walking animations, collision, facial deformation, height calibration or game-engine imports.
- The main schema still stores `height_m` independently. Its historical default is **not** a confirmed world-height measurement of the newly generated MPFB mesh.
- Final project state remains `generated_unverified` until separate rig/deformation and engine-import acceptance gates. Do not equate a matching body mesh hash with verified animation or an import-ready character.
- Purchased Fab assets, user models and binary Blender/GLB files stay local. Only JSON test diagnostics are retained by cloud CI.

## Acceptance evidence

[The live Blender/MPFB integration workflow](https://github.com/DocDamage/newestcharactercreator/actions/workflows/mpfb-cloud-smoke.yml) must build **two real MPFB humans**, one default/neutral, one with nondefault normalized controls, each saved and reopened in independent Blender processes. It must establish (1) observed macro values equal requested saved values, (2) consistent evaluated vertex hashes across each Blender save/reopen, (3) **different** evaluated geometry hashes between neutral and changed bodies, and (4) **different** rendered static preview triangle positions between the two characters, with identical authoritative UCC project/master bytes before and after preview.

Python-only mocks are contract regression tests, not proof of actual Blender behavior. The user's Windows 11 Blender 5.3 + MPFB environment, rigging under animation, true real-world height, and Godot/Unity/Unreal imports remain outstanding until explicitly executed.

**Next feature after verification:** an in-place *apply saved body changes to staged copy* workflow using MPFB `TargetService.reapply_macro_details()` and `HumanService.refit()`, with real armature/skin-weight preservation checks before replacing the master pointer. Do not add live sliders without that transaction.
