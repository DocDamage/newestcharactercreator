# UCC-P1-SESSION-CATALOG-001

## Plan and behavior

Allow an explicit existing local animation catalog for one desktop session with
`--catalog FILE`. This enables ordinary source and portable-EXE workflows against
a chosen workspace library. The default application-data location remains the
default. The selection is passed through the existing common catalog accessor;
it is neither saved in preferences nor switched while the application runs.

The path must be absolute, canonical, existing, nonempty and a single-link regular
local file. Redirected ancestors, symlinks, junctions, hardlinks and Windows
network/device namespaces and alternate data streams are rejected. Startup
performs filesystem checks only. Explicit Refresh and reference lookups open
the catalog read-only. Index writers require an existing version-1 UCC schema on
their same SQLite `mode=rw` connection before any write; they neither create nor
repair tables. This admission also propagates into measured FBX registration.
Existing catalog operations continue to check source permissions;
Index controls may update the selected library. No licenses or permissions are
granted by selecting a catalog. A later invalid location errors without falling
back to the default database.

Touched files: small Qt-free path helper, desktop constructor/accessor and CLI;
focused location/CLI/real-Qt tests, the optional existing-schema writer contract,
and an explicit required-Qt CI step. Reversible
source changes only; no dependency, original catalog or asset modification.

## Reproduce and acceptance

Source: `python -m ucc.desktop --catalog "D:\workspace\animation_library.db"`.
Portable: `UCC-Desktop-Alpha.exe --catalog "D:\workspace\animation_library.db"`.
Use an existing reviewed catalog. Open a project and use the normal Animation
library controls. The flag cannot be combined with self-test options.

Run `python -m unittest discover -s tests -p test_desktop_catalog_location.py -v`
and, with `UCC_REQUIRE_QT=1`, the corresponding `test_session_catalog_qt.py`
command. Also run `test_catalog_existing.py`, `test_catalog_readonly.py` and
`test_fbx_catalog.py`. Required checks cover selection isolation, unchanged default behavior,
zero startup SQL, routing through real refresh, rejection and no fallback, CLI
forwarding, actual hardlinks and a redirected ancestor. Existing catalog/native/
reference Qt suites cover the downstream callers of the unchanged accessor.

The final focused gate completes 205 tests in 24.982 seconds: 203 pass and two
unchanged Windows symlink-privilege cases skip. All 24 new cases pass, including
real Windows junction, hardlink and alternate-stream rejection, same-connection
existing-schema admission and real Qt routing. The existing real Qt self-test
also passes. The local log is `session-catalog-dev001/focused-final001.log` under
the private outer evidence directory (SHA-256
`f8103e74eb3f3bf80eb933ece00e0bd2354c2566eb867e4c396d2ec7d1aa5631`).
The complete required-Qt gate runs 2,142 tests: 2,128 pass and the exact fourteen
prior Windows privilege cases skip, with zero failures or errors. All 2,118
baseline test IDs remain and all 24 additions pass without skips. The full suite
takes 734.750 seconds. Scanner and guardrail tests, expected sample-evidence
rejection, and the source executable's three self-test checks pass. Independent
audit verifies all 1,050 public source files are unchanged across execution.
Evidence: `session-catalog-full001/result.json` and `audit.json` under the private
outer evidence directory; result SHA-256
`d886de9480ff5dceac8e3a2c1e83e6211e77c6e3aea3b29c765ae732649c2cac`.
Only acceptance documentation and the already tested K publication base change
after this gate. Remote exact-head CI, packaged startup and actual frozen feature
acceptance remain pending.
This slice does not claim persistent playback restoration, Blender
animation, visual quality or engine acceptance.
