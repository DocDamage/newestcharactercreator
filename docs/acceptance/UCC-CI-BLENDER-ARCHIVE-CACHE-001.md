# UCC-CI-BLENDER-ARCHIVE-CACHE-001

The seven experimental Linux suites currently fetch the same official Blender
5.3.0 archive and checksum independently. Some runners receive repeated HTTP 403
before any native test, while other first-attempt suites pass. Those setup
failures are not code acceptance and must remain qualified.

## Checksum receipt phase

The existing workflow has an opt-in boolean dispatch input,
`checksum_receipt_only`, default false. Only an explicit true dispatch runs the
bounded public-metadata job. It fetches at most 64 KiB from the exact official
HTTPS checksum endpoint, rejects missing/duplicate/malformed Linux entries, and
retains one JSON receipt containing the original public text/hash, exact selected
archive digest, requested/effective URL, UTC and workflow head/run/attempt.
It downloads no Blender archive, installs/runs no Blender and executes no domain
suite. Its successful workflow with the domain matrix skipped is **metadata-only
success**, never normal experimental integration acceptance. Job conditions are
evaluated before matrix expansion, so the run can contain one skipped matrix job
rather than seven concrete skipped jobs; acceptance requires no domain execution,
not a particular skipped-job count.

PRs, pushes and default dispatches retain the existing seven suite names,
assertions, budgets, profiles and explicit JSON diagnostic artifact members.
No private source, pose, scene, geometry or image is included in the new receipt.
The receipt parser's repeated-character test hashes are explicitly invented,
non-shipping fixtures, not an official archive pin or Blender integration proof.

The root must independently validate the exact dispatch event/input, tested head,
raw public text/hash and unique Linux checksum line before adopting a pin.
The local official endpoint returned HTTP 403; no static archive pin is invented.

## Subsequent cache phase: pending primary pin

Once the primary receipt is accepted, add one bounded archive producer and seven
exact-key consumers. Cache only the official tar/checksum pair; verify the pinned
SHA on producer misses/hits and every consumer before extraction. Keep isolated
profiles, official MPFB installation, all real domain checks and closed JSON
artifacts. No prefix restore keys or unverified origin fallback. A cold producer
403 remains a visible setup failure; cache success does not establish domain
success. This phase remains pending and no archive/cache execution is claimed.

## Local verification

Eight new parser/CLI/mode tests and 29 existing CI/privacy contracts pass: 37
tests, zero failures/errors/skips. Installed YAML parsing and new Python AST
checks pass. The actual primary receipt dispatch and archive/cache phase remain
unrun at this source checkpoint.
