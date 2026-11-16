# UCC-P1-MAT-001-D — Existing desktop actions and coherent material history

Status: three actual window actions, real Blender execution and saved undo/redo
verified on disposable projects. Whole application goal remains active.
Depends on [material-preserving backend acceptance](UCC-P1-MAT-001-C.md).

## Plan and changes

Enable the existing body and face controls for the narrowly supported prepared
MPFB human with an immutable material binding and at most one registered visible
hand. Route existing actions to the accepted backend, admit only the matching
saved result, and preserve master, material appearance and rebuilt hand as one
undo/redo step. Unknown parts, source-animation references, stale IDs, dirty
sessions and unrelated result changes must stay explicit errors. Test cancellation
through the existing action and preserve originals throughout. No new controls,
installation, provider or owner-launcher replacement is required.

`core.material_master_intent` defines metadata eligibility and exact adoption.
It does not inspect geometry or grant rights. `CharacterSession` gets a narrow
material-aware face intent method and one external-result history adopter.
Adoption requires a new master and material binding together, one revision,
the same hand variant/instance and unchanged unrelated intent. Existing generic
master adoption remains strict. The controller checks current disk state and
dirty-session state before updating its saved revision, without reopening the
project or clearing history.

`desktop.material_master_workflow` runs the existing backend and reads the
registered material proof before adoption. Generation, refit and face adapters
route material-bound metadata through it; existing reference-aware behavior is
retained. View eligibility enables the existing controls. The existing busy
state freezes editing and exposes Cancel. Material-aware cancellation clears
preview state and reports that no new result was adopted, without a generic
error dialog. Other errors remain visible. Low-level body/face safety guards
and unsupported hand/source-reference restrictions remain.

## Actual application evidence

Private root: `D:/dev/new Character Creator/evidence/export001`.

| Case | Actual existing control | Saved change |
| --- | --- | --- |
| `mat-ui272` | Apply saved body controls | Height 0.50 → 0.54 |
| `mat-ui278` | Apply saved face shape | Nose width 0.50 → 0.60 |
| `mat-ui279` | Generate humanoid | Height 0.50 → 0.56 |

Each starts the actual production `MainWindow` on the Windows Qt platform with
a real controller and admitted private copy. Widget edits and the Save action
persist intent. Qt input activates the existing buttons; existing confirmation
dialogs are answered on these disposable projects. Normal `BackgroundJobs`
threads invoke real Blender/MPFB workers. No backend result or worker is replaced.
The actual success handler validates proofs and adopts the result.

Each case records visible window captures and metadata before, after intent
save, after adoption, after Undo+Save and after Redo+Save. Assertions compare
the exact master, appearance and hand together against the pre-job and published
states, while preserving intended sliders and facial strengths. Disk and session
agree after each saved step; the final material binding is admitted again.
Original source project and master hashes remain unchanged.

Blender 5.3.0 build `02f0899d78e3`, MPFB 2.0.18, Python 3.12.10 and existing
PySide6 6.11.2 are used. Success screenshots were visually inspected. These
captures verify the real editor and history; they do not prove desktop rendering
of the chosen material or replace the separate Godot evidence from the backend.

Initial private UI attempt 270 failed before submitting a worker: setting the
slider value did not emit its normal release signal. That failed run is retained.
Corrected 272 uses the widget's release behavior and scrolls its button into view;
it does not bypass the application handler or retry a live worker.

Successful runs precede a later change limited to material-aware error dispatch
and the hand help caption. The success/adoption pipeline is unchanged. Current-
source `mat-ui282` activates the actual Cancel action after observing a real owned
Blender child alive. The child stops, no result is adopted, metadata bytes and
backup history remain unchanged, and the window shows the normal cancellation
message. Its launch observer returns the real process; it does not provide a
substitute worker outcome. Its screenshot was visually inspected.

## Tests and limits

Metadata and Qt tests cover coherent adoption, exact undo/redo, unrelated changes,
wrong hand variants, unsupported metadata, source-reference rejection, dirty/stale
completion, no-op history, all three dispatch paths, busy controls and cancellation
reporting. Synthetic bytes are explicitly isolated in
`tests/fixtures/material_desktop_logic.py`; they never count as Blender evidence.
Early focused 268 errors came from test fixture construction and an incorrect
test action name; corrected focused runs pass. Full 273 and 275 predate the final
cancellation error route; the final suite is recorded separately in the private
acceptance manifest. No existing product assertion was weakened.

Final required-Qt suite 283: 1,299 tests, 1,285 passed, 14 existing skips,
264.913 seconds. Current material desktop tests 281: 10 passed. Guardrails 284:
12 passed. Pure metadata/history/controller imports load no Blender, Qt, NumPy
or model runtime. `git diff --check` passes. These tests complement the actual
window evidence above; synthetic dispatch tests do not substitute for it.

The owner checkout/launcher and previous frozen archive are unchanged. Actual
desktop material preview, color/roughness controls, frozen execution, source-
animation material closure, different hand selections and artist approval remain
unfinished. No dependencies, licenses, NoAI flags or distribution rights change.

The next task recorded at this gate was explicit skin-color/roughness editing in the desktop,
backed by the verified material transaction and strict history adoption. Keep the
authoritative appearance proof unchanged while editing draft values, define a
verified same-spec no-op, and execute actual save/reopen and undo/redo before
claiming the new controls work. This now has separate
[controls acceptance](UCC-P1-MAT-001-E.md); the earlier results above remain unchanged.
No placeholder textures or promotional art.
