# UCC-CI-BLENDER-ARCHIVE-CACHE-001

The seven experimental Linux suites previously fetched the same official Blender
5.3.0 archive and checksum independently. Some runners received repeated HTTP 403
before any native test while other first-attempt suites passed. Those setup
failures remain qualified; neither cached tool bytes nor metadata receipts are
integration acceptance.

## Metadata receipt and accepted provenance

The opt-in boolean dispatch input `checksum_receipt_only` defaults false. Its
bounded public-metadata job fetches at most 64 KiB from the exact official HTTPS
checksum endpoint and retains one JSON receipt with original public text/hash,
selected Linux digest, URLs, UTC and workflow head/run/attempt. It downloads no
Blender archive and installs/runs no Blender or domain suite. A successful receipt
workflow with the domain matrix skipped is metadata-only success. Job conditions
precede matrix expansion, so admission requires zero domain execution rather than
a particular number of skipped matrix nodes.

Actual receipt run `44179235108` at `535b7e4cac547c1d8aff55579c820700fe6d290c`
failed at the original official checksum endpoint with four HTTP 403 responses,
exit 22, zero artifacts and zero domain execution. This is retained failure, not a
successful receipt or a reason to weaken verification.

Blender's [official infrastructure mirror project](https://projects.blender.org/infrastructure/mirror/wiki)
identifies the [official mirror service](https://mirror.blender.org/) and Clarkson.
A live HTTPS request for the identical checksum filename/version at
`https://mirror.blender.org/release/Blender5.3/blender-5.3.0.sha256` returned HTTP 302
to `https://mirror.clarkson.edu/blender/release/Blender5.3/blender-5.3.0.sha256`.
The latter returned HTTP 200 and 777 public bytes. Root independently fetched the
exact delegated URL without further redirects and verified the complete bytes and
unique Linux entry. The raw official manifest SHA-256 is
`94f6b7fddba74a12b39a18b8f0b5ddb2859a0f5db825001335a9ca6705665f5d`.
Its reviewed `blender-5.3.0-linux-x64.tar.xz` SHA-256 is
`dacb8264197a3f7fda6001285a5a506fc97ee943881261c2c3bd63c882f22e05`.
This metadata establishes the pin; no local archive download or execution was
performed. A different regional redirect refused during root's earlier probe is
retained separately and is not an authorized fallback.

## Public archive-only dispatch

A second optional boolean input, `archive_cache_only`, also defaults false. An
explicit true dispatch runs only the existing archive producer: no extraction,
Blender execution or domain tests. The run name says `PUBLIC ARCHIVE CACHE ONLY -
no Blender/domain execution`. If both inputs are true, checksum receipt mode takes
precedence and the archive producer and domain matrix are skipped. PRs, pushes
and default dispatches continue through the producer and seven real domain suites.

Two serial archive-only runs at the same exact feature head can establish cold
publication followed by warm reuse without repeating live domain jobs. Cold proof
requires an initial producer miss, actual pinned acquisition and publication;
warm proof requires the initial exact restore hit, acquisition step skipped and
both-file rehash. The final publication lookup also hits after a cold acquisition,
so it must not be used as evidence of warm reuse. Archive-only workflow success
is setup acceptance only and is never admitted as seven-domain integration.

## Exact public archive cache

One normal-mode `prepare-blender-linux` job prepares an exact version/key containing
both reviewed hashes, so a changed approved checksum manifest also changes the key.
Only the official tar and checksum pair may occupy the canonical cache directory;
extra entries, symlinks, hard links, changed files and wrong digests fail. A warm
producer rehashes the same two files. A cold producer first requests metadata from
the original official origin. Only transport/setup failure permits the explicit
verified Clarkson fallback. A checksum or archive validation failure stops the
job without a fallback. Curl content bounds (63), local writes (23), certificate
verification (60), configuration and unknown failures also fail closed. Only the
explicit reviewed transport/setup exit allowlist permits the alternate origin. Requests use HTTPS, refuse redirects to unreviewed hosts,
have explicit transfer/size limits, and use no automatic retries. Primary bounds
are 45 seconds for metadata and 120 for the archive; fallback bounds are 60 and
240 seconds. The preparation job has a 15-minute total limit.

The producer saves only after verification and requires exact cache publication
before releasing consumers. Cache actions use reviewed v5 commit
`caa296126883cff596d87d8935842f9db880ef25`; the official restore/save action manifests
use Node 24. There are no prefix restore keys, and even an unexpected partial
match returned by the service is rejected. Every one of the seven consumers must
restore the exact key, rehash both fixed digests, repeat the original strict
platform checksum check and only then extract the tar. Consumers never fetch an
origin on cache miss. Extracted Blender files, isolated profiles, MPFB settings,
source assets and generated scenes/images are not cached.

The existing seven normal suite names, assertions, per-suite/worker budgets,
`fail-fast: false`, `cancel-in-progress: false`, isolated extension directories and
closed JSON diagnostic artifact sets remain. Normal metadata monitoring must
account for the extra preparation job (and the skipped metadata receipt job),
while requiring seven actual successful domain jobs for domain acceptance. A
failed producer or consumer setup is never interpreted as passed domain work.

## Local verification and pending execution

The receipt-only phase passed 37 selected tests. The cache phase passes 53 selected
tests with zero failures/errors/skips, including 16 new cache boundaries and the
eight receipt tests. Cases reject wrong archive SHA, wrong/missing/duplicate
checksum entries, changed manifest bytes, extra members, symlink modes, real hard
links, oversized members, and consumer misses/partial identities. Small invented
opaque bytes live only in explicitly non-shipping unit fixtures; they are not a
Blender archive or integration proof. Installed YAML parsing, new Python AST
checks and installed Git Bash syntax-only checking pass.

No acquisition script was executed locally, no archive was downloaded/installed,
and no private assets were read or uploaded by this work. Actual remote cold-cache
publication, warm-cache reuse and all seven domain suites at the final new head
remain pending. No Blender, visual, usable-action, engine or release acceptance
is inferred from the local cache tests.
