# UCC-P1-ANIM-007G — canonical playback inputs and ancestor watches

Status: locally accepted on top of creator-CI commit `25c76cda4c8eccb4e914f596cfe3b1a8c91a6826`. Required-Qt regression, native filesystem faults, actual GPU invalidation and independent saved-evidence auditing pass. Draft PR #67 is published; exact-head remote acceptance and a fixture-only Windows CI follow-up remain pending. No merge approval is implied.

## Problem and resulting behavior

A directory watch can continue following a renamed physical directory. If its file watch is unavailable, replacing the original parent with a junction can preserve the file's bytes, size, timestamp, device and inode while changing its canonical path. Replacing the parent with a real directory containing a hard link also preserves the file identity. Watching only the immediate parent can miss both changes and leave playback active with obsolete watch coverage.

Three new structural Qt regressions reproduce this on the unchanged implementation. All three fail because no ancestor notification arrives and publication remains active. These fixtures prove watcher behavior only; they are not Blender geometry or GPU evidence.

The binder now registers bounded directory-entry watches along the ancestor chains of the owner, selected catalog and exact registered sources. It generates `Path.parents` directly and never enumerates external directories. The existing watch limit and failed-attachment rejection remain. All handles, including ancestor watches, are removed on revocation.

Directory callbacks require source and catalog paths to remain canonical. Watched directory device/inode identities must remain unchanged, so replacing a real parent cannot hide behind hard-linked file identities. File snapshots also bind device identity. Directory timestamps remain excluded: unrelated entries and empty SQLite WAL/SHM coordination must not invalidate valid playback. Meaningful catalog/WAL bytes remain hashed, and an empty WAL is still armed for later committed writes. Resolution failures revoke playback or produce the existing structured storage error.

Both full API checks before/after watch attachment remain, with an additional final canonical-source and directory-identity check before publication. Legacy unreferenced behavior, source policy/NoAI checks, immutable masters, project history and all Blender/math/protocol code remain unchanged.

## Executed local evidence

Private evidence is outside Git under `evidence/anim007g`. Manifest `source-under-test-04-reference-path-watchers.json` freezes 72 source/test/workflow files. Only the frontend binder and its Qt tests differ from the accepted creator-CI source manifest; the independent auditor verifies that exact difference. Follow-up manifest `source-under-test-11-canonical-temp-fixture.json` changes only fixture construction in the Qt test module; all application, bridge and creator-CI/API source bytes remain identical to published head `8c242fb1f2037f8d0ccff2d9cd77a4e0ac4abdab`.

| Check | Observed result |
| --- | --- |
| Red regression on unchanged binder | Three real Windows filesystem cases fail in 7.146 seconds: source-parent junction, catalog-parent junction and real-parent replacement retaining the same hard-linked file |
| Focused current controls/watchers and legacy expression tests | All 24 pass; the required-Qt selector now executes fifteen reference-expression cases |
| Initial full required-Qt suite | 1,101 tests in 202.076 seconds: 1,087 passed, fourteen existing Windows symlink skips; the three new junction/hard-link tests do not skip |
| Canonical temporary-root follow-up | All 24 focused checks pass; all fifteen watcher cases pass with a deliberately noncanonical temporary parent; full 1,101-test suite passes in 136.430 seconds with the same fourteen existing skips |
| Optional Qt absence | Fourteen API checks pass and fifteen UI checks skip as intended |
| Preflight and actual source launcher | Three scanner checks, twelve guardrails and three-check SELF_TEST_OK pass |
| Actual Windows Play on copied real Blender cache | All 25 frames draw in 1.172 seconds; unrelated ancestor entry creation/removal preserves publication |
| Three actual parent faults | Each delivers a genuine ancestor notification and clears CPU playback plus destroys GL vertex/index/VAO resources while file bytes/size/time/device/inode stay unchanged |
| Independent saved-evidence audit | Revalidates both original/copied typed results, identical 25-frame buffers, source policy/catalog rows, restored canonical directories and all 72 source hashes; no new Blender work |

The GPU checks use disposable copies of the accepted creator result with body height 0.6, muscle 0.5, weight 0.55, nose width 0.65 and its rebuilt registered hand. Copied source and catalog parents are isolated, their exact paths and receipt are rebound, and the real API checker validates the copies before publication. Only the direct file watch is deliberately removed to exercise the directory fallback. Each directory move is confined to the explicit test root. Junction removal is nonrecursive and original evidence/source/catalog files remain hash-identical. No source animations, meshes, scenes, cache buffers or private renders are uploaded.

Terminal evidence is `actual05/acceptance.json` and `path-watchers-independent-06.json`. The actual GPU receipt SHA-256 is `7b91be7c0f0dc5c544124bd84837e501d3ef1810bf59778ea890c34bc1610fe6`. Earlier red logs remain separate; no assertion was weakened. New tests use native Windows junctions without installation and ordinary directory symlinks on Linux.

## First remote head and fixture follow-up

At initial head `8c242fb`, Core, preflight and Windows packaging pass. Both Linux Qt versions pass; both Windows Qt versions fail because the runner supplies a DOS 8.3 temporary alias (`RUNNER~1`) while production and Qt resolve the long path. The structural fixture retained its raw temporary root, causing mismatched watcher strings and correct canonical-catalog rejection before the intended fault. The fix resolves the fixture root before construction; every canonical-path, attachment and invalidation assertion remains. All fifteen cases also pass under a deliberately noncanonical temporary parent. No application or Blender change is required.

The initial Windows artifact independently matches all 90 bridge sources and its extracted portable executable passes all three self-tests without installation. Three initial Linux jobs fail before tests at the official Blender download with proven HTTP 403; healthy jobs are left untouched. The old-head observer is read-only while they finish. A fixture-only follow-up requires a new stable head and fresh acceptance; initial package or partial archive results are not relabelled as that head's results.

## Remaining work

Finish the initial healthy jobs before publishing the fixture-only follow-up to the coherent draft. Keep each published head stable until its healthy jobs are terminal. Require all five workflows, seven Linux archives / 39 JSON records and the exact-head Windows package plus actual executable self-test. Keep all earlier suites, checksums, budgets and artifact privacy. Do not update the published head while healthy jobs run; keep draft and unmerged pending owner approval.

Human visual quality, plain unprepared reference masters, usable target actions, root/loop/foot quality, actual Godot/Unity/Unreal imports, sprite output and the wider blueprint remain unfinished. No dependencies, installs, asset rights, NoAI restrictions or export permissions changed.
