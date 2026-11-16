# UCC-P1-MAT-001-F — saved material desktop preview

Status: source implementation and private real-application acceptance complete.
The full creator goal remains incomplete; owner launcher and frozen build are unchanged.

Depends on the accepted material controls/graph and full static surface preview.
The task carries the saved owned shader's explicit color and roughness, and the
evaluated mesh's smooth normals, into an immutable complete static surface and a
fixed local dielectric PBR renderer. It must preserve the existing geometry-only
preview and motion diagnostics. No new UI control or asset shader execution.

Touched areas: Blender preview export and its closed job option, bounded static
material decoder, material preview job, immutable surface buffers, OpenGL shader,
existing preview action and source watchers. All source/master work is read-only
and uses private staged copies. Removing the material route restores the earlier
geometry-only behavior; no project schema or authoritative asset migration occurs.

Acceptance requires real normal application actions on both previously accepted
colors; fresh Blender source/hand/shader admission; unchanged metadata/history and
original masters; actual GPU uniform and buffer readback; visible complete and
face-focused images; material-proof mutation invalidation; shader/normal faults
rejected; a shared total deadline and cancellation; full regression and independent
evidence/hash audit. No Blender render parity, textures, shadows or engine import
approval is inferred from a desktop preview.

Lighting policy: fixed white directional light and diffuse ambient, dielectric
metallic zero, GGX distribution, Smith visibility and Schlick Fresnel, linear
lighting with explicit sRGB output. Zero roughness uses a 0.045 sampling floor
for its delta-like highlight. This is a bounded preview lighting model, without
environment maps, tone mapping, shadows or Blender lighting matching.

Current private evidence root: `D:/dev/new Character Creator/evidence/export001`.
Run 303 stopped at the old protocol's all-options rejection before static export;
its failed receipt is retained. The contract now permits only a closed
`owned_material_spec` and still rejects unknown options. Unit 304 failed because
the isolated synthetic triangle did not reach the existing upright head region;
the fixture was corrected without changing the product gate. Unit 306 failed in
its finite mocked clock sequence; the corrected test expires one shared budget
after source admission. Unit 307: 23 tests, 22 passed and one existing Windows
symlink-privilege skip. These fixtures are not Blender/model evidence.

Runs 308/309 reached static export but stopped because that operation had not
activated the checked core contract import path. Runs 311/312 reached the actual
renderer and exposed PySide6 6.11's scalar uniform overload. Retained-mesh probes
315/316 isolated its erroneous integer upload; the renderer now uses typed
`glUniform1f`. Probe 317 rendered the retained real export without GL errors.
The failed evidence remains separate from final acceptance.

Final visible MainWindow runs 318/319 use the normal existing preview QAction,
Qt worker, complete fresh Blender admission and static export, then the normal
completion handler and actual GPU renderer. Both retain all originals and project/
backup/session history. Their saved colors/roughness are respectively `#94603d`
at 0.65 and `#7d513c` at 0.72. GPU readback verifies the actual linear color and
roughness uniforms within 1e-6 and exact position/normal buffer bytes, with GL
error zero. Whole-character, face-focus and application screenshots were decoded
and visually inspected. Both display the complete 26,756-triangle surface.

Independent fresh Blender references 325/326 and audit 328 compare all 80,268
corners per character: position multiplicities and triangle multisets match
exactly. The installed Blender glTF extractor rounds float32 normals to four
decimals before normalization. All exported normals match that independently
computed serialization rule within 4.334385343088844e-8. Maximum difference from
unrounded source normals is 8.183212776330152e-5, below the derived rounding/
normalization bound 1.7332008205603834e-4. Installed exporter sources are hashed.
Failed audits 322/323/324/327 are retained: their assumptions omitted exporter
rounding, pre-normalized the reference, or used Python float64 rounding at ties.
No product assertion or tolerance was relaxed.

Retained-preview replay 329 uses the actual admitted mesh for separate diagnostics.
Roughness 0.1/0.9 changes 74,992 pixels with identical geometry silhouettes and
actual GPU roughness readback. These diagnostic values are not project edits.
Four copies of the real GLB with wrong roughness, a texture reference, missing
normals or NaN normals reject explicitly. On a private project copy, an actual
QFileSystemWatcher clears the GPU surface after a material proof changes; the
copy's proof is restored and originals stay unchanged. This is retained-artifact
replay, not a claim of another Blender worker run.

Actual Cancel 330 observes owned live Blender PID 28500, stops it through the
normal QAction and leaves project/history unchanged. It retains the existing
preview cancellation error dialog, which was observed and dismissed. Actual
export worker fault 333 rejects explicit parameters that differ from the saved
owned shader. Actual retained-mesh clay GPU probe 332 passes the earlier geometry-
only path with its original tint and no GL error.

Final required-Qt suite 320: 1,322 tests, 1,308 passed, 14 existing Windows
symlink-privilege skips, 289.793 seconds, process return code 0. All Python sources
predate the run. Focused desktop 310: 60 passed. Guardrails 334: 12 passed;
initial discovery 331 found zero tests and is not acceptance. Pure core imports
load no Blender, Qt, NumPy or model runtime. `git diff --check` passes.

Runtime: Python 3.12.10, PySide6 6.11.2, Blender 5.3.0 `02f0899d78e3`, MPFB
2.0.18, OpenGL 3.3.0 NVIDIA 610.88 on RTX 3060 12 GB. Exact commands, retained
worker results/logs, output hashes and screenshots remain in private evidence.

Reproduce from this checkout with its existing Python paths and private admitted
project: launch the desktop, open the saved material-bound character, choose
View → Preview current saved Blender master, then use face/whole-character focus.
No cloud or installation is needed. Lighting limitations above remain explicit;
textures, expression/material playback, source-animation material closure, frozen
execution and Blender render/artist/engine quality approval remain unfinished.

The next task recorded at this gate was carrying the saved owned material and
frame-specific evaluated normals into facial-expression playback. It now has
separate [facial material acceptance](UCC-P1-MAT-001-G.md); the earlier evidence
above remains unchanged.

No dependency, license, distribution, NoAI, cloud or owner-launcher changes.
The full creator goal remains incomplete.
