# Threat model and known gaps

Trust the caller's explicit admission, safe IDs, installed interpreter/package,
local kernel/filesystem and cooperative policy writers. This is not a sandbox
against malicious same-UID code, hostile callers, compromised interpreters or
network-filesystem locking differences. Policy metadata is not a signature.

All input path components use descriptor-anchored no-follow traversal; leaves
are nonblocking regular single-link files with size and before/after identity
checks. Output parents are anchored, directories are exclusive, and each file
is published using an exclusive link from a private random temporary file.
Concurrent losers never remove winners. Files are mode 0600; directories 0700.
Only a process's own temporary publication file is cleaned up.

Readers take nonblocking shared locks. External writers must take an exclusive
lock on the **same fixed inode** and must not replace the lock file. No missing
policy/lock is created. This package provides no policy mutation API. Policy
admission precedes target worker launch and is repeated inside each worker while
holding the lock. All declared target consumers contribute dependencies.

Transport drains stdout and stderr while writing stdin nonblockingly, all under
one deadline. Failure exhausts uncertain remaining byte allowance; process groups
are killed and direct children reaped. Kernel-hung syscalls, kill/reap latency,
and child processes escaping a process group are outside this bound. Built-in
workers never fork additional processes. There is no arbitrary execution API.

## Open blockers (not accepted guarantees)

- Supplied procedure and explicit Hermes-export validation do not prove business
  execution or complete upstream compatibility. Inventory coverage projections
  alone are not procedure pass or adapter conformance. Heartbeat/proposal/status
  metadata and delivery configuration do not bind a producer/run/outcome.
- Revision checks compare retained executing module code objects against compiled
  fixed installed source, including the actual `-m` entry. Stale `.pyc` and helper
  drift are rejected. This is not cryptographic attestation or protection against
  malicious caller mutation or a compromised interpreter.
- Root/ancestor bindings are checked after admitted traversal and at consumption
  boundaries. Tested replacement schedules do not prove immunity to every race.
- Output-only bounded readback now preserves ordinary exhausted failure reports.
  I/O errors or an over-cap aggregate report can still return a closed CLI error;
  admitted maxima (128 checks and 1024 declarations) have explicit tests; arbitrary
  larger inputs are not admitted and persistence under filesystem failure is not promised.
- Synthetic concurrent runs, lock transitions and freeze view consistency are
  exercised; a complete filesystem/root-race concurrency matrix remains open.
- Arbitrary public-safe IDs are caller responsibility, not secret detection.

There is no health certificate, business execution proof or full upstream
compatibility claim. Never treat this incomplete candidate as release-ready.
