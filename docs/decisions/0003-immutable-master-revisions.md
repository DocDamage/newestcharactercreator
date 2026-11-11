# ADR 0003 — Immutable Blender masters and atomic project pointer

**Status:** Accepted for staging, pending real Blender verification for geometry.

## Problem

A character's editable `.blend` and `project.ucc.json` cannot be replaced as a single atomic operation on ordinary Windows filesystems. Blender processes can crash or time out; a GUI may have a stale revision. Rewriting `master/character.blend` before validating it would corrupt the last usable character even if the JSON write later failed.

## Decision

The Blender job writes into an **explicit, job-scoped output directory**. UCC copies completed bytes into a private immutable `master/versions/<sha256>.blend`, then performs an optimistic-concurrency-checked, atomic update to the project JSON pointer. The old `.blend` is never overwritten, and the metadata store saves a backup before advancing the project revision. A failed pointer write leaves the previous project and master active. Any unreferenced hashed file is an orphan, not an authoritative project, and may be garbage-collected only after reference checks.

The copy **always** sets `geometry_state=generated_unverified` and resets rig/part-validation metadata. A file's `BLENDER` signature, hash and byte count are not proof that Blender created a usable humanoid. The separate future `validate_master` workflow must run actual Blender fresh-process reopen and geometry/rig checks before marking a master `validated` or enabling engine exports.

## Boundary conditions

- The source must be a regular file below the explicitly authorized worker-output directory. Directory and source symlinks, project escapes, oversized files, and a mismatched existing SHA-256 destination are rejected.
- The staging file resides on the project volume and is fsynced before installation; the final immutable filename is the content SHA-256. A hard-link install avoids overwriting an existing hash destination. This assumes a filesystem supporting hard links (e.g., Windows NTFS); a future fallback needs the same no-overwrite guarantee and tests.
- The `.blend` pointer changes **last**, with revision checking and metadata backups.
- Startup recovery must handle unreferenced revisions conservatively; do not delete based on filename alone.
- A successful test of `stage_unverified_master` with structural test bytes must never be presented as an actual Blender/MPFB validation.

## Required evidence

- Simulated failure before pointer update leaves old project readable.
- Concurrent edit causes a revision conflict and leaves the other user's changes untouched.
- Content hashes are stable, prior revisions are retained, symlink/path escape is rejected, and duplicate data reuses the same content-addressed artifact.
- Real Blender verification is still required for any `geometry_state=validated` claim.

## Follow-up

Connect this staging transaction to the typed Blender job protocol once UCC-P0-001 proves actual MPFB generation/reopen. UI work still waits on that gate.
