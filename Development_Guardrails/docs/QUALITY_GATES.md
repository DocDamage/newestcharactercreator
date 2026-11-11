# Quality Gates and Evidence Protocol

## Gate definitions

`config/gates.json` defines the required IDs for each milestone. Use `python Development_Guardrails/tools/verify_gate.py --list` to see exact names. Examples in `config/` are explicitly **not run**.

| Gate | Required proof | Behavior if unavailable |
|---|---|---|
| `P0_SPIKE` | Real Blender/MPFB environment probe, MPFB-created mesh and `.blend`, successful reopen via new Blender process | BLOCK UI implementation |
| `P0_COMPLETE` | Worker protocol, failed-worker recovery, dependency lock, legal review of runtime boundaries | BLOCK broad integration |
| `M1_CHARACTER` | Save-reopen, valid morph ranges, reversible swap, rig deformation, expression | BLOCK engine validation |
| `M1_EXPORTS` | Actual Godot/Unity/Unreal imports, animated playback, RGBA sprite render, atomic save under crash | BLOCK claim of universality |
| `M2_ANIMATIONS` | Mixed-rig retarget proof, asset permissions, 100 individually cataloged and previewable clips | BLOCK 100+ clip claim |

## Evidence JSON

Store one `evidence/GATE.evidence.json` with `schema_version`, `gate` and `tests`. Each passed test needs `id`, `status:pass`, `observed_at_utc`, and one or more `artifacts: [{path, sha256}]`. Paths are relative to the private evidence directory. Manual checks also need `reviewed_by` and `review_note`. Sign-off must be from a real review, not an automated placeholder.

**Interpretation:** SHA-256 and file presence prove integrity of stored evidence; they do **not** prove a game-engine import is good. For Blender Stage 0, semantic checks also read the actual structured smoke summary. For higher phases, reviewers must open and check exported objects in the target engine; capture actual importer logs, video/stills and object-bone counts where available.

## Required process

- Keep private local evidence untracked (`evidence/`). Hashes are calculated from existing files; never supply invented values.
- Reject unexpected or duplicate test IDs, missing proof, tampered hashes, path traversal, symlink escape, or missing manual reviewer fields.
- Rerun a gate after changing input versions or source geometry. Results refer to exactly the artifact hashes they validated.
- On error, record issue/rollback and the next attempt; never downgrade a red integration gate to an informational warning to ship.
- CI validates pure code and contracts. Blender and target engine validation run on the user's actual Windows workstation or a properly provisioned trusted runner.

## Example commands

```powershell
py -3 Development_Guardrails/tools/verify_gate.py --list
py -3 Development_Guardrails/tools/verify_gate.py --gate P0_SPIKE --evidence-dir evidence
py -3 -m unittest discover -s Development_Guardrails/tests -v
```
