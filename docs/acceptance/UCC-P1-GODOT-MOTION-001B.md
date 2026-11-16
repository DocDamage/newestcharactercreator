# UCC-P1-GODOT-MOTION-001B - private registered-input persistence

Local acceptance checkpoint, November 16, 2026. Actual retention, fresh-process
loading, catalog revocation, live copy cancellation and full required-Qt
regression pass within the scope below. Commit-specific remote gates remain
pending. This is source API persistence, not Godot import, playback or delivery.

## Behavior

retain_registered_native_inputs consumes a completed V2 source preparation and
a caller-bound production receipt SHA. The normal saved-target loader rechecks
the current project, all animation IDs, selected binding, source/catalog rows,
permissions and immutable historical proofs. PreparedRegisteredNativeSource is
a checked locator; an arbitrary DTO cannot substitute for the source receipt,
two worker graphs or the existing numerical and byte validators.

The closed UCC_PRIVATE_REGISTERED_NATIVE_INPUTS_V2 manifest binds 33 payload
files, with manifest.json making 34 files total. It retains the original byte
request, source recipe/receipt, seven private code files as data, provenance
metadata and worker control/report records. Four proof references point into
the existing 45-file target binding; they do not duplicate the private review
scene or make this a portable native-evidence package. The binding and current
source authority remain required for loading.

The selected saved specimen stays at revision 11, binding
36ee230c41790d4dab3950d2645df285f90e070c0ecd650a0b3642a1c2f3b663.
The original nine target producers and two case009 source producers retain their
historical identities. No new Blender or Godot job runs in this slice.

load_registered_native_inputs selects an explicit retention UUID and expected
manifest SHA, with the same typed RegisteredInputSelection and current per-use
permissions. It performs a read-only restart load, without selecting a latest
record, adopting a project revision or changing project/history/source policy.
V1 source guards, retention and byte-request semantics remain unchanged.

## Transaction and failure semantics

Payloads stage under a new owned job directory and commit through a no-replace
rename into .ucc-candidates/godot-registered-native-inputs/<UUID>. Before commit,
cancellation/failure publishes no candidate. After commit, a later error reports
the historical commit and expected manifest identity; it does not delete, repair
or rename a foreign replacement. A later explicit load must revalidate current
context and permissions. A data commit does not authorize execution or delivery.

Metadata parsing and hashing use the same bounded captured bytes. Closed file
inventories, lengths, hashes, path/descriptor identities, canonical ancestors,
host/source guards, source-job watches, per-entry cancellation and final owned
seals reject drift. Duplicate/flood tests verify early rejection and iterator
cleanup. Empty bytes are allowed only for the fixed .gdignore payload role.

## Actual retain and fresh-process restart

Private case registered-godot-retention-positive002 copies the exact accepted
case009 project: 68 source/history/proof files plus 84 files in its three genuine
producer directories. A cold 956-file source and a separate read-only backup of
the selected catalog provide a stable baseline. The user catalog is never written.

The unmodified retain API returns a verified private candidate. One separately
started canonical Python 3.12.10 process then calls the real load API using the
returned UUID/SHA and original explicit selection/permissions. The parent exits
0 in 109.329 seconds; the restart exits 0 in 44.094 seconds. The actual child
PID/parent/argv and terminal result are recorded; no native launch is allowed.

- Candidate: 72a0d223-65cd-4e37-a34e-e036c3747006.
- Manifest SHA:
  ae3d5b38d4240faee3827403a1416f5e867b41bc00955861599698aca53f0a31.
- Actual result SHA:
  715cde992410c6561bcdc49d87004e8c729605d23a0c854483055d5af82a819d.
- Independent admission SHA:
  21306a65ab823f9abb79ec9ecff861dd8199ec53cc2c7af9392ab63bfc24f302.

Independent admission verifies all 34 file hashes/lengths, the exact 186 project
files (152 originals plus 34 candidate files), one empty owned retention job,
the unchanged original three producer directories, four proof references and
all ten false readiness flags. All twelve preservation checks pass in both
processes, including global/owned catalog bytes and logical rows, original
source/worktrees, cold source, author/code inputs and the previous failed case.

## Actual failure paths

registered-godot-retention-wal001 uses a separate copy of the positive project
and an owned catalog backup. It changes only the selected local_preview_allowed
field from true to false, retaining NoAI. The commit stays in a 4,152-byte WAL;
the 49,152-byte main database remains unchanged during commit and fresh read.
A fresh real loader rejects with ValidationError from _reference_rows:
Registered catalog source/clip/policy differs from its immutable binding.
The parent exits 0 in 9.125 seconds and the child in 0.360 seconds, confirming
the expected causal rejection. An independent read-only replay of archived
main/WAL bytes verifies the selected field change and unchanged other tables.
All ten original-preservation checks pass; project/candidate bytes stay exact.
Closing the owned writer checkpoints its intentionally changed data, so owned
postclose byte/logical equality is explicitly not claimed. The global catalog
stays unchanged. Independent admission SHA:
6e9d1b182988e412f93966446450c80c0f7e28e63a1845c046e1b0f88c6e6189.

registered-godot-retention-copycancel001 calls the real retain API with a caller
Event. A bounded observer sees 2 of 33 files, including 160,560 nonempty bytes
in bind_positions.bin, then immediately signals cancellation. The exception
trace lies inside the actual production copy loop, through copy_file/hash_file
and the inherited budget. No commit phase, candidate or success manifest exists.
The parent exits 0 in 41.235 seconds, confirming expected cancellation; all
twelve preservation checks pass. This proves partial file-set cancellation,
without claiming interruption during a byte write. Independent admission SHA:
da8c9f715831a48a0aedbf8514b7025c920c973df5645b46a6b02ad234c0cc0a.

Earlier positive001 remains a failed composite test: retention returned a checked
candidate, but a Windows subprocess-audit argument comparison blocked restart
before any child creation. Its result is retained as exit 1, not acceptance.
The corrected harness uses Windows' exact serialized command and an explicit
Python executable; originals and the earlier prepared harness are preserved.
No product-code change was needed for that harness fault.

## Complete regression and source identity

The complete required-Qt/offscreen suite exits 0: **1,772 tests, 1,758 passed,
fourteen existing Windows symlink-privilege skips, no errors or failures**, in
702.861 seconds (704.641 wrapper seconds). Independent admission checks all
unique ordered raw/structured outcomes and exact previous skip IDs/reasons.
All 956 physical source files remain byte-identical before/after and match the
actual cold source and reviewed nine-file implementation under parent 2375a07.
Subsequent acceptance-document edits do not change that code/test identity.

- Raw log SHA:
  034db50c0091fab3a9291018f78307332824fb311e91a892fe62b788d2eef758.
- Per-test JSON SHA:
  56438a2389c3f010cf7fb6fc1c850edc60138c46791c08b4c9b0b77356631da8.
- Independent full admission SHA:
  95085d1e197ffde88c3aa5ec0405e89ad339704495252c3648e50afadcace987.
- Private coalesced gate: registered-godot-retention-local-gate001/
  local-gate-admission001.json, SHA
  d4286b001176588e2e28ffc8c07e17994414a5339d875680c6ea0a1592985b64.

Thirty-three distinct focused tests pass: thirty combined tests plus three new
inventory faults. An overlapping four-test repeat is not additive. Synthetic
native/context fixtures are isolated under tests/fixtures and explicitly marked;
they are not the actual source/retention proof. Existing native validators run
against the genuine case009 output in the real IO cases above.

## Limits, dependencies and next action

The same exact four source permissions from author record379 and seven code
hashes32a are retained as private data. No source-only, NoAI, UE-only or privacy
flag is widened. Provenance identity is not a code-license or execution grant.
The six experimental kernels stay outside Git; no dependency, installation,
public license, owner launcher, GUI control or engine project is added.

Actual postcommit foreign replacement, coherent readiness escalation, retained
data corruption and withdrawal of transient producer folders remain unrun;
their isolated unit faults must not be relabelled as live system tests. Godot
import/playback, runtime performance, delivery, code provenance, artist approval
and full application acceptance remain separate open gates.

Next: review and integrate this source-only persistence slice after its final
commit gates. Then consume it in a guarded private body-runtime verification
workflow, using separately selected reviewed code and genuine source references.
Rollback through its own Git revert; preserve completed private data/history and
failure diagnostics. The full character-creator blueprint remains unfinished.
