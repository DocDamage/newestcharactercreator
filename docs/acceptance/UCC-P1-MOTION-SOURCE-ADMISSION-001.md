# UCC-P1-MOTION-SOURCE-ADMISSION-001

## Plan and acceptance

Expose the measured source clock without changing clip, receipt, project-binding,
or registered-target identities. The existing two-worker FBX importer already
preserves source frame origins. A separate immutable clock readout distinguishes
the interval between first and last samples from nominal sample coverage.

Dependencies: existing reviewed FBX catalog intake and receipt validation.
Touched modules: source clock contract, catalog read accessor, verified-reference
property, existing desktop indexing completion, and focused tests. All changes
are additive and revertible; asset bytes and existing project/catalog originals
are outside the change.

Acceptance requires strict clock boundary tests, malformed-receipt rejection,
stored read-only reopen, existing catalog/reference regression, and required-Qt
indexing tests. Genuine acceptance uses one selected private source, its exact
existing local-preview policy, a new owned catalog, two native Blender workers,
and a fresh-process read-only reopen. Record source/policy hashes and actual
commands, versions, exit codes, logs, and aggregate metadata locally. Do not
publish private source files, snapshots, bone matrices, or asset images.

## Scope

The user attests that the supplied animation assets came from Fab, free or
purchased. This does not change the recorded operation-specific policy. The
selected pack's existing reviewed policy permits local preview and prohibits AI
input, raw redistribution, and engine use. Its AI-generated provenance remains
recorded. Filename descriptions do not establish action quality.

Stored clock inspection is metadata inspection; fresh source verification still
uses the existing native admission path. This task does not establish target
retargeting, rendered preview, gait/loop quality, usable-clip counts, or engine
integration.

## Verification

Local canonical Python 3.12.10 required-Qt regression: **84 passed, zero skips**,
6.578 seconds, actual exit 0. It includes source clocks, FBX intake/catalog,
fresh reference checks, project reference/history, and real offscreen Qt indexing.
Log SHA-256: `0076c9a6a8861c7fa35c51be4a8dee85927c4ab605a50525d16bf435c0b6814b`.
The earlier 82-test pass is retained separately; review then added two tests for
cancellation after measurement and during clock read, suppressing completion
without claiming rollback of already completed catalog records.
The required-Qt CI workflow now runs the existing FBX indexing suite explicitly.

Genuine selected-source check called the existing measurement coordinator once:
two Blender **5.3.0**, build `02f0899d78e3`, workers agreed. A fresh Python
process reopened the owned catalog read-only with equal metadata and policy.
Measured source clock: **1–300 at 30 fps**, 76 bones, three roots; sample span
299/30 seconds, nominal coverage 10 seconds. Both native worker stderr logs were
empty. Result SHA-256:
`66cbc28b42cdc64ff47957db2332a3240862d353db2a1e12ad3a0e7f79f40ba7`.

A separate final-code clock-only process exited 0 without repeating Blender;
stored metadata and the owned catalog MAIN bytes remained unchanged. Report SHA:
`53f25df571886b6f9cbb901ea79ba785479c30e60fd64689093b0f293bacb38e`.
Source, existing policy, historical intake record, and original global catalog
MAIN/sidecar byte identities stayed unchanged. The original database was never
opened through SQL. These preservation claims cover the named files only.

Local private reports and native logs are retained under
`D:/dev/new Character Creator/evidence/export001/motifect-source-admission-H001`;
final focused regression is in sibling `motifect-source-clock-focused-H002`.
No private assets or snapshots enter Git. Native desktop feature rendering,
normal packaged feature flow, target retargeting, engines, and motion quality
were not tested by this slice. Publication CI is a separate gate.
