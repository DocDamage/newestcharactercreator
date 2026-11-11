# Asset Provenance and Licensing Guardrails

Every AI model, image, animation, generated mesh, external executable and character-part source needs a manifest with provider, source URI, exact license/version, acquisition timestamp, permitted operations and hash if copied locally.

## Four independent permissions

1. **Private use:** Permission to possess/use the asset privately (subject to its terms).
2. **Use in a game/export:** Depends on engine restrictions and whether the license permits derived/work-in-project formats.
3. **AI input/training:** A separate permission. Do **not** infer from game-use rights; Fab NoAI restrictions require conservative handling. Avoid using third-party asset bytes as inputs to generative services without explicit review.
4. **Redistribute editable source:** Highest-risk action; generally **not** allowed for purchased Fab content without separate permission.

`tools/check_asset_policy.py` implements a deliberately conservative preflight. Its boolean fields are a user-reviewed policy record; the checker is **not legal advice** and cannot automatically interpret licenses.

## Example manifest record fields

- `asset_id` — stable unique identifier
- `provider` — e.g. Fab, Blender, user-authored
- `source_uri` — exact listing/page or original project source
- `license_name` — exact license, version/date when known
- `license_reviewed` — has a human reviewed the particular license?
- `no_ai_training`, `ai_training_permission` — conservatively independent checks
- `ue_only`, `can_use_in_non_unreal` — engine restrictions
- `can_redistribute_source` — explicit permission for source assets in a distributed editor/package

`config/asset_manifest.json` is intentionally empty. Do not populate it with invented assets just to pass checks. For a real asset record, get the current terms and attach a source link/reference. Unknown => deny automated export/public shipping until classified.

## Example commands

```powershell
py -3 Development_Guardrails/tools/check_asset_policy.py --manifest Development_Guardrails/config/asset_manifest.json --operation private_inventory
py -3 Development_Guardrails/tools/check_asset_policy.py --manifest Development_Guardrails/config/asset_manifest.json --operation engine_export --target godot
py -3 Development_Guardrails/tools/check_asset_policy.py --manifest Development_Guardrails/config/asset_manifest.json --operation ship_creator
py -3 Development_Guardrails/tools/check_asset_policy.py --manifest Development_Guardrails/config/asset_manifest.json --operation ai_input
```

The first call permits an empty read-only inventory; other operations block when there are no actual assets. **Import and export permissions for Fab depend on the particular product, license and content type**; never apply one global yes/no assumption to the whole library.

## Dependencies

Blender is GPL, MPFB program code is GPL, some core human assets are CC0, PySide6/Qt have module-specific licensing conditions, and compiled Aseprite builds have redistribution restrictions. Process boundaries are an engineering strategy, **not** a guarantee that distributing a proprietary bundle is legally safe. Public shipping requires an informed code/license review.
