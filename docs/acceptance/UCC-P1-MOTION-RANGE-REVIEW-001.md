# UCC-P1-MOTION-RANGE-REVIEW-001 - ephemeral registered preview window

**Source checkpoint, November 17, 2026.** Committed implementation
`57720597a28f84fa62b1bbf16fcda9a63c309c52` matches the 1,019-file public source
freeze. Full required-Qt regression and its independent audit pass. Three genuine
normal source GUI flows exit 0 with the finite observations below; their separate
independent renderer/WAL admission status is recorded in the single field below.
Exact-head CI, Windows artifact inspection and generic startup are separate
publication metadata and are not asserted as future successes here. Normal
packaged G range-review feature execution remains **UNVERIFIED**.

F is closed separately: PR #80 merged as
`d9f5bfb7bceafe20775649fb6edd3c1b35a0a5de` with the exact accepted tree.
Its ten applicable fresh-main checks passed. Its merged local/remote feature
branches were pruned ordinarily; the detached proof checkout at `fbb932c`
preserves all 1,407 raw files. That physical inventory includes historical
ignored files; it is not the 1,015-file F tested-public-source count.

This G slice adds an ephemeral inclusive frame window to the existing registered
saved-target preview. Target frames 1-300 still address the same original complete
cache; source frame equals target frame plus one. Start/end controls, Apply review
window and Go to window start do not create a clip, Action, binding, cache, export,
project revision or catalog classification. The existing Reset view stays a camera
reset. Shared MotionViewer and legacy PlaybackClock defaults are retained.

The new immutable PlaybackWindow and WindowPlaybackClock preserve absolute
zero-based cache indices. Valid Apply stops playback and installs a fresh clock
at the selected first frame. An invalid pair retains the previous window/clock
and play state. Play from the selected end restarts at its selected beginning,
not global frame zero. Scrubbing and queued/late ticks stay within selected bounds.
Go to window start pauses and seeks. A single-frame window is a static view with
Play disabled. Changing/reopening the selected saved preview resets the window;
no window is persisted.

For inclusive target bounds start/end, the endpoint sample span is
`(end-start)/30` seconds; nominal sample coverage is `(end-start+1)/30` seconds.
The legacy final-sample dwell is retained: the end frame is reached at the sample
span and remains playing for its last 1/30-second sample interval before stopping
and holding. For target75-150/source76-151 this is 76 samples, a 2.5-second sample
span and 76/30-second nominal coverage. Static windows have span zero and do not
start playback. Timing metadata must not be presented as a performance benchmark.

Apply, Play, seek and Go-to-start retain the existing current-project/source,
selected-binding and catalog checks. The saved cache and complete proof closure
remain authoritative; the range controls do not slice/rewrite MotionCache, adopt
a new watch baseline or weaken WAL/rights invalidation. No heavy new proof hashing
is added to the GUI thread. This slice does not establish a new cryptographic
same-stat directory-event guarantee beyond the existing transport.

## Frozen source and completed scoped checks

The four candidate paths are:

- `src/ucc/preview/playback_window.py` (new pure contract/clock).
- `src/ucc/desktop/target_action_preview.py` (existing viewer controls).
- `tests/test_playback_window.py` (new nonshipping pure cases).
- `tests/test_target_action_preview_window.py` (new nonshipping Qt cases).

The frozen source manifest is
`372a9a06f101a23bf85218300120ff799996b21ea9ba789f348af658ff87f488`.
The helper's 19 pure tests pass. The focused 52-test group passes without skips:
19 pure window tests, 14 new Qt window tests and 19 existing target-preview tests.
These are synthetic control/contract tests, not actual original renderer proof.

The broader selected unittest run completed **172 tests: 171 passed and one
unchanged Windows privilege skip**, in 38.687 seconds. All 59 Qt cases passed
without skips. The skipped case is
`test_motion_cache.MotionCacheTests.test_redirected_binary_is_rejected`, reason
`Creating symlinks needs Windows privileges`; it is present in the accepted F
fourteen-skip baseline and its source is unchanged.

The surrounding runner actually exited **1**, because its blanket skip rejection
was too broad. The unittest log ends `OK (skipped=1)`; the runner is not relabelled
as exit 0. Independent scoped observation
`a0558120d7a7baac2d127ca62bb3d9916060ab49b7f207dbb51c30068c0b026d`
checks source/order/outcomes and this qualification. Raw broader log SHA:
`ac8d2dc32d1f52ba63e99f773f7011f3288c6843fede1698e63e606ad3c3947e`.

## Full source regression and genuine source observations

The full required-Qt run and independent audit pass: **1,992 tests = 1,978 passed
+ fourteen exact prior Windows privilege skips**, unittest time **599.683 s**,
canonical Python 3.12.10 and existing Qt 6.11.2. All 1,959 F test IDs remain in
relative order, with exactly 33 G additions (19 pure and 14 Qt); there are no new
G or optional-Qt skips. Actual discovery, raw log, events and outcomes agree.
The full result is `d909da896991...`; independent admission is `aed8c8a556c2...`.

Its explicit lean preservation scope covers original p186, the original
four-role379 inputs, global catalog MAIN and logical state through **owned byte
replays only**, raw A-F proof checkouts, and G public/cold source. It does not
rehash or claim preservation of all 81 historical case/artifact namespaces. The
three genuine GUI results additionally preserve the owned p186 copy and all nine
immutable flags. Owned
catalog policy restrictions below are deliberate exceptions, not immutable flags
silently reported true. Originals receive no SQL opens.

All three genuine flows use normal MainWindow project/source/binding selection,
fresh private-source consent and the public saved-preview load route. Current
review independently derives the exact eight-field selection for the original
integration diagnostic clip and binding `36ee230c4179...`. The normal source GUI
is explicitly qualified by an instance-owned catalog provider and a Qt nonnative
project chooser; no packaged-launcher equivalence is claimed. Known QA writers
are closed by primary attestation during the viewer lifetime, except each
explicitly owned WAL restriction. This is not broad OS/BASE quiescence or
independent worker-thread affinity proof.

Positive root30546/child30092 exits 0 without timeout and records **158 observed
original renderer calls**: four initial full-cache, 146 during target75-150,
two during queued Apply120-125, two static150 and four during close-while-playing.
It observes source76-151 labels, distinct 2.5-second span and 76/30-second coverage,
normal pause/resume/end hold/replay/Go-to-start, queued-tick range application,
static Play disabled, and real dock close while playing followed by queued-event
drain. Root Prepared/cache/watch authority and local cache/clock/canvas are
cleared; visible windows close, the worker terminates, and the transparent
renderer observer is restored.

Preparation independently decompresses the sealed original binary/chunk manifest
to derive all 300 position/triangle hash pairs. The immutable packed cache is
hashed **once** before timed review. The observe-only wrapper always calls the
original `SkinRenderer.draw` with unchanged arguments/return, then compares the
product frame and renderer's CPU upload-buffer hashes against those independent
references. Every **observed** draw stays within its accepted absolute window and
matches those hashes. First/end observations are required. Trace bounds change
only after the normal Apply slot accepts the new window. This is submission/CPU
buffer evidence: no screenshot, private pixel/geometry emission, GPU-memory
readback, all-76-samples-rendered or 30-FPS/performance claim is made.

Separate static-WAL root72986/child38920 and playing-WAL root90829/child34000 both
exit 0 without timeout, with **six** and **ten** observed draws respectively.
Each has its own fresh catalog seed; neither restores rights. A writer opens WAL
before the viewer, with autocheckpoint disabled, then restricts **only** the exact
current motion asset's `local_preview_allowed` from true to false. Held MAIN stays
49,152 bytes with SHA prefix `6670a8fe9a93...` while committed WAL grows from zero
to **4,152 bytes**. Writer-held raw snapshots remain in RAM until cleanup.

The static case is paused at absolute149; normal Go-to-start is attempted after
the restriction and the range controls clear/disable. Disabled Apply cannot adopt
a new clock. The playing case starts at range75-150 and is playing at absolute75
before restriction, then the existing watcher/guard clears the preview. Both drop
root Prepared/watch identities and local cache, clock, canvas and window state,
then normal source reopen rejects with the actual message
`ValidationError: Registered catalog source/clip/policy differs from its immutable binding` while
the writer is still held; review is absent and Load disabled. No zero-latency
pre-event invalidation guarantee or exact watcher-versus-timer causal trace is
claimed. After viewer cleanup, writer close/checkpoint is recorded separately:
MAIN changes to SHA prefix `429e03ec8ad8...` and WAL disappears. Only `asset_sources`
changes in the reported table hashes; exact selected-row/field replay validation
belongs to the independent admission field below.

**Independent three-case renderer/WAL admission: ACCEPTED.**

`registered-motion-range-renderer-audit001/independent-renderer-admission001.json`
SHA256 `7a09aaa3d4b6bc75b6593354d1024115ce733f68617c4dceca3cf4980919d4a2`
independently validates all 300 sealed cache records, every observed renderer
submission, and the retained held-WAL/checkpoint row changes. It verifies only the
selected local-preview restriction changed and preserves the declared lean scope.

All three retained stderr streams contain **648 bytes** with an
`0x8001010d`/faulthandler mention at `open_project`. All three actual parents/children
still exit 0 without timeout. Stderr is not claimed clean; no crash diagnosis or
cause is inferred. Parent native streams and QA events remain in RAM until the
child/viewer cleanup permits flushing. No engine/subprocess launch or UI error
message is observed.

| Private retained record | SHA prefix | Scope |
| --- | --- | --- |
| `registered-motion-range-review001/source-manifest001.json` | `372a9a06f101` | Exact tested 1,019 public files |
| `registered-motion-range-full-regression001/run001/result.json` | `d909da896991` | Actual required-Qt full run, exit 0 |
| `registered-motion-range-full-audit001/independent-full-admission001.json` | `aed8c8a556c2` | Full discovery/order/skips and explicit lean preservation |
| `registered-motion-range-review-actual001/positive001-result.json` | `dc9331ee8c85` | Normal range controls, renderer submissions and close cleanup |
| `registered-motion-range-review-actual001/wal-static001-result.json` | `90fa3982c6d8` | Static Go-to-start restriction, clear and blocked reopen |
| `registered-motion-range-review-actual001/wal-playing001-result.json` | `762fb3a6d964` | Playing restriction, clear and blocked reopen |

The original four-role author record
`379546fd557d27cf51b15fc19a35b3b0eefb223dbc0abbef6cfc9e9543ec811b`
remains unchanged: private local preview, NoAI, no AI input, no cloud transmission
or source redistribution. No new engine-use grant, private correction program,
dependency, download or license is introduced. Original master/history/p186,
source bytes and global catalog remain preserved. The original diagnostic is not
called walking or usable; a review window is not a trim/bake/edit operation.

Loop, editing, usable-action, gait, rotation, foot/hand contact, artist/appearance,
performance/VRAM, engine/runtime, delivery and shipping approval remain false or
unverified as before. Publication wiring retains existing Qt suites and adds the
window suite to required desktop/package checks. Final commit/PR/main checks,
source-first AST/PYZ/payload/private-kernel inspection and generic three-check
startup are recorded separately as publication metadata. This source checkpoint
does not predict their future success or require metadata-only rewrites after
checks. Normal packaged G feature execution remains **UNVERIFIED**; generic health
and code identity do not establish that flow. The broader blueprint remains open.
