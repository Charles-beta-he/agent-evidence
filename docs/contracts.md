# Contracts (development slice)

`agent_evidence_checks_dev1`, `agent_evidence_policy_v1`,
`agent_evidence_check_receipt_dev1`, and `agent_evidence_checks_report_dev1` remain
supported. Inventory and supplied-procedure extensions are documented below.
The `agent_evidence_hermes_run_v1` extension and safe export field allowlists
are documented in [Hermes adapter](hermes-adapter.md).
Unknown fields are rejected. A manifest is a caller-authorized bounded control
input; it cannot supply authority for any files outside its root-relative target
map. It is not an inventory catalog, exemption or exact grant.

A manifest has exact fields: `schema`, `profile_id`, `candidate_revision`,
`targets`, `checks`, `policy`, `lock`. A target maps to `path` and `domains`.
A check has `system_id`, `check_id`, `target_id`, `operation` (`presence` or `json`),
`domains`, `required`. All consumers' domains are unioned per target before
any target worker. The policy has `schema`, `domains`; each domain maps to exact
boolean `enabled` and nonnegative integer `epoch`. Missing/invalid policy or
lock is never implicitly enabled or created. An empty domain list is explicit
caller classification, not proof that content is nonbusiness.

Roots must be absolute physical lexical POSIX paths. Relative roots, traversal,
symlink components, URI members and ambiguous separators are rejected rather
than expanded. Root-relative members permit only ASCII letters, digits, dots,
underscores and hyphens within nonempty components. Exact paths are never
returned in reports. IDs permit 1–64 ASCII letters/digits plus `_ . : -`.
**Caller must supply public-safe IDs**; a valid ID could still encode a secret.

Control JSON: at most 256 KiB; depth at most 16; at most 1024 entries in any
container; strings at most 4096 characters; keys at most 128; finite numbers
and signed-63-bit magnitude integers. Duplicate keys, non-object top levels,
invalid UTF-8 and nonfinite/overflow numbers are rejected. Manifest checks are
limited to 128, targets to 1024, per-consumer domains to 32. No truncation into
successful results occurs. Content reads have a 1 MiB cap. A shared ledger
limits read bytes to 8 MiB and monotonic work to 10 seconds. Each child has at
most 2 seconds, 256 KiB stdout and 16 KiB stderr. Limits are not CLI overrides.

Receipt context binds run/profile/system/check/target/operation, candidate
revision, installed source-closure revision, input/output inode identities and
raw policy digest. Times are aware UTC; receipts older than 300 seconds or in
the future are rejected. Worker output has a closed schema and closed reasons.
Presence PASS proves observed content identity only. JSON PASS adds strict
object readability, including the documented complexity limits. Invalid JSON
is FAIL; missing/unavailable/denied/incomplete evidence is UNKNOWN, except an
explicit stable disabled policy produces NOT_APPLICABLE. Aggregate FAIL takes
precedence; then UNKNOWN; then PASS; only all N/A aggregates N/A. Empty is UNKNOWN.

Each observation receipt is exclusively published and then read by an independent
child which also rereads the source under policy admission. Source or receipt
drift cannot borrow PASS. Final control inconsistency invalidates positive/N/A
rows; a conclusive business FAIL verified by independent readback is retained,
including its reason and diagnostic metadata. For Hermes, final control failure
promotes that verified nested negative to the outer report verdict FAIL instead
of retaining an outer PASS; the original observation receipt is unchanged.
Unverified or late worker negatives are not retained. Invalid control JSON is
UNKNOWN, not a conclusive business-JSON failure.

No required check rows disappear when disabled. `certified_healthy=false` and
`certification_status=not_provided` are unconditional. `complete=true` requires
nonempty required checks all PASS, aggregate PASS, successful final control,
valid live inventory, and nonempty required procedures with PASS, valid inventory,
zero required gaps and zero unmapped receipts. Hermes additionally requires every
fixed disposition to PASS; required UNKNOWN rows prevent completeness.

| Stage / example | Exit | Output |
|---|---|---|
| Invalid invocation | 2 | Closed `invalid_invocation` diagnostic |
| Manifest schema/unsafe ID rejected before output creation | 2 | `schema_invalid`, no report |
| Existing output directory fails admission | 2 | `input_unavailable`, winner files unchanged |
| Admitted run with invalid policy/inventory/procedure evidence | 1 | Incomplete report; exact failure/unknown disposition retained |
| Complete scoped generic run | 0 | Complete report, never certified healthy |
| Offline supplied bundle / stored report replay | 1 | No live admission, never complete |

Errors that prevent report publication return a closed diagnostic (2), not a
fabricated incomplete report. No exit code alone proves production health.

## Inventory-run extension

`agent_evidence_inventory_run_v1` adds an exact `inventory` map with four explicit
control members: `declarations`, `scope`, `attestation`, `catalog`. These and the
policy/lock must have distinct paths and cannot alias target paths. The caller
explicitly authorizes these bounded review controls, not arbitrary refs within
their contents. `fixture --inventory` generates a complete synthetic example.

The four schemas are `agent_evidence_inventory_{name}_v1`. Declarations contain
`schema` and `procedures`; each declaration contains `procedure_id`, `system_id`,
boolean `required`/`exempt`, `source_ids`, and `domains`. IDs are distinct; required
plus exempt is invalid. The raw declaration bytes are pinned, including every
field, not just names. This is an inventory declaration subset, not a procedure
receipt validator. Each system has at most 32 distinct source pins.

Scope, attestation and catalog all carry exactly matching `owner_id`,
`evidence_id`, `basis_id`, `reviewed_at`, `expires_at`, `revoked`,
`max_freshness_seconds`, `declarations_sha256`, sorted exact `procedure_ids`, and
exact `source_pins` (target ID -> raw SHA-256). Scope adds `scope_complete=true`
and nonempty `negative_boundaries` (public-safe IDs). Attestation adds
`scope_complete=true` and `approved_scope_sha256`; catalog adds the same approved
raw scope hash plus `source_domains`. Both approvals must equal the observed raw
scope hash. Review time must not be in the future, expiry must be later than
review, revocation must be false, and freshness is capped at 86400 seconds.
These are cooperative caller review claims, not authenticated signatures.

All target, check, declaration and catalog domain dependencies are unioned
before any target context/worker/content open. Unknown or disabled domains deny
that source across all consumers. Controls, worker reads, readbacks, and final
controls use the same byte ledger and fixed monotonic deadline. Fixed lock inode
identity is carried into workers and final freeze; lock acquisition is
nonblocking. Cooperating writers must lock that same inode, never replace it.

`acquire_inventory` admits controls only; the coordinator records actual worker
observations before `freeze_inventory`. Batch APIs are internal sequential state,
not a caller-editable grant or serialization contract. Freeze is single-use even
on failure and concurrent freeze calls have one winner. Final policy reads
bracket the final controls; complete success alone exposes `control_snapshot`.
Missing/invalid/drifting final control stays UNKNOWN with drift, even if a later
deadline expires. Late success and pure not-started exhaustion both expose no
snapshot. The generic lane does not implement the optional Hermes disabled
fallback. Stable disabled controls may be exposed, but inventory remains invalid
when source observation was denied. Inventory source hash mismatch is UNKNOWN.

Six views (`profile`, `checks`, `procedures`, `remediation`, `lifecycle`, `adapter`)
are **inventory coverage views**, not implementations of procedure/adapter
semantics. They share one current-clock consumption decision over the same deeply
immutable freeze. Expired or backwards-clock consumption cannot retain approval;
no source/policy is reopened. Required disabled rows remain N/A and remain gaps;
no view executes anything or resolves historical failures by suspension.

Stored report evaluation only returns `supplied_evidence_only`, UNKNOWN and
`live_admission=false`. It cannot reconstruct a live batch or frozen object.
Explicit procedure bundles are separately validated as described below. There is no
caller `now` option that extends approval. Output-only exclusive publication and
bounded byte-for-byte readback are separate from input acquisition: they may
persist an exhausted failure report but never renew input budget or admit work.

## Supplied-procedure extension

`agent_evidence_procedure_run_v1` extends inventory-run with `procedures`, an
explicit root-relative bundle file, distinct from every target/control. This
bounded sanitized control input contains no business bodies. The runner reads it
once on the shared budget, never opens its refs, and evaluates after freeze.
Missing or invalid bundle evidence cannot drop reviewed declaration rows.

`agent_evidence_procedure_bundle_v1` has exactly `schema`, `declarations`,
`receipts`, `admitted_evidence`. The declarations object uses the inventory
schema; each row adds a required `validation` object with exactly:

- `implementation_state`: missing/scaffolded/implemented/enabled/disabled; only
  enabled can validate PASS. A non-enabled implementation is UNKNOWN, not an
  exemption. Only explicit stable policy disable produces N/A.
- `freshness_seconds`: integer 1–86400; `min_successes`: integer 1–32 (not bool).
- `acceptance_atoms` (nonempty), `negative_assertions`, `allowed_side_effects`:
  unique public-safe ID lists, at most 32 each.
- `issuer`, `action`, `scope`: exact public-safe IDs expected in the grant.

`admitted_evidence` maps IDs to UTF-8 JSON **text**, preserving raw bytes for
hashing. No text is a path. This map is independently supplied by the caller;
receipts cannot add admission by pointing elsewhere. The library entry point
`evaluate_procedures(declarations, receipts, admitted_evidence,
frozen_inventory=None)` instead accepts a map of IDs to bytes. Whole bundles
have the 256 KiB control limit; library admitted bytes have the same total cap.

A receipt (`agent_evidence_procedure_receipt_v1`) has exactly `schema`,
`receipt_id`, `procedure_id`, `system_id`, `declaration_sha256`, `started_at`,
`completed_at`, `result`, `execution_mode`, `grant`, `acceptance`, `negative`,
`cleanup`, `side_effects_observed`. The declaration SHA-256 covers the **entire
row** serialized by `agent_evidence.serialization.encode` (sorted keys, compact
JSON). Inventory separately pins the complete declaration document's raw bytes.
Times are UTC, ordered, not future and fresh at consumption. Only result PASS
and claimed mode `live_e2e` can validate; a mock claim is a definite negative.

Each pointer is exactly `{id, sha256}`. `acceptance` and `negative` map each
required atom name to a pointer. `cleanup` is one pointer. Assertion records have
exact fields `schema=agent_evidence_assertion_v1`, `receipt_id`, `procedure_id`,
`system_id`, `kind` (acceptance/negative/cleanup), `name`, `status`
(PASS/FAIL/UNKNOWN). Cleanup must have name `cleanup`. Identity, kind, name and
raw-byte SHA-256 must match. This validates the supplied readback record, not
cleanup of any real resource by this package. Observed side effects must be a
subset of the declared allowlist; no effect is executed.

The `grant` pointer names a record with exactly `schema` (value
`agent_evidence_procedure_grant_v1`), `grant_id` (equal to the pointer ID),
`receipt_id`, `procedure_id`, `system_id`, `issuer`, `action`, `scope`, `status`
(active), `valid_from`, `expires_at`. All identities match exactly; the interval
must cover receipt execution and remain unexpired at current evaluation time.
A valid grant record is **not a capability**. Cooperative admitted bytes are not
signed attestations; callers must review who supplied them.

Exact duplicate receipt IDs count once; conflicting content for the same ID is
UNKNOWN. Only fresh fully valid successes count toward the threshold. Latest
failure or missing/stale/future latest evidence defeats historical successes;
unparseable chronology is UNKNOWN, never silently ignored. Equal latest times
combine with FAIL precedence. Distinct IDs do not prove independent runs/people.
Unknown procedure IDs in receipts leave a registry gap. Duplicate declaration
IDs remain separate UNKNOWN rows. Invalid required types conservatively remain
required. Empty required sets are UNKNOWN. Explicit supplied contradictions are
FAIL; malformed, absent, stale or ambiguous evidence is UNKNOWN.

A real frozen inventory is bound to the complete declaration document and
rechecked with the current clock without I/O. Changed or omitted declarations
cannot shrink its required denominator. Disabled required rows stay N/A and gaps.
`inventory_valid` is true only with a currently valid live frozen observation;
procedure mode remains `supplied_evidence_only` even then, and
`live_admission=false` means the procedure report grants no execution authority.
Standalone bundle validation may PASS structurally but never restores inventory
trust. Stored report replay is UNKNOWN. Standalone evaluation keeps
`complete=false`; the live run coordinator computes scoped completeness using
the conditions above. All paths keep `certified_healthy=false` and
`certification_status=not_provided`.

