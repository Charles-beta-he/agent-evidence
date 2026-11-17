# Hermes explicit-input adapter (v1)

This adapter interprets **sanitized caller exports**, not live Hermes files. It
makes no complete-version compatibility claim. There is no HOME/environment
fallback, owner import, scheduler invocation, provider call, Git command, network
request, destination resolution, export command or automatic discovery.

## Run a synthetic example

```sh
agent-evidence fixture --hermes --procedures --out /absolute/physical/path/hermes-input
agent-evidence hermes run --input-root /absolute/physical/path/hermes-input --manifest manifest.json --output-root /absolute/physical/path/hermes-output
```

Both leaf directories must be new and have physical existing parents. The fixture
creates only synthetic metadata, a synthetic presence target, policy and optional
inventory/procedure inputs. It does not inspect or export a real installation.
The run returns **1**, not 0: full-package acceptance is incomplete. Its
`hermes.checks` always contains 21 required rows, including UNKNOWN and disabled
N/A rows. `hermes.verdict` is the semantic axis; top-level `checks` describe actual
bounded byte observation/readback, so an observed export can have a PASS byte
observation and UNKNOWN/FAIL semantics. Presence never implies execution.

Library entrypoints:

```python
from agent_evidence import run_checks
from agent_evidence.adapters.hermes import evaluate_inputs

report = run_checks('/absolute/physical/path/hermes-input', 'manifest.json',
                    '/absolute/physical/path/another-output', hermes=True)
rows = evaluate_inputs({})  # 21 UNKNOWN required rows, no filesystem reads
```

`evaluate_inputs` consumes already supplied Python values, not paths or live
admission. It uses the current clock for freshness. It cannot independently
attest source acquisition. The CLI/library run uses installed fixed workers and
a second child recomputing each observation and semantic result. If a time
threshold changes between children, disagreement is conservatively UNKNOWN.

## Manifest / authority boundary

`schema: agent_evidence_hermes_run_v1` has the existing exact `profile_id`,
`candidate_revision`, `targets`, `policy`, `lock` fields. `checks` must be `[]`;
requested adapter checks are generated from the static catalog, not caller code.
`hermes` has exactly:

```json
{"schema":"agent_evidence_hermes_inputs_v1","inputs":{"jobs":"jobs-target","heartbeat":"heartbeat-target"}}
```

Values are target IDs in the existing exact manifest target map, **not paths**.
Supported keys: `jobs`, `heartbeat`, `proposal`, `status`, and each of the four
presence check IDs listed below. Omitted bindings yield UNKNOWN without a target
read. Unknown/blocked binding keys and unsupported versions are rejected before
workers. The bounded manifest itself is directly authorized by the CLI flag;
it is not permission to scan the root. Optional `inventory` and `procedures`
retain the existing schemas (`procedures` requires inventory).

All target observations are subject to admission, unioned consumer domains,
cooperative policy locks, bounded no-follow reads, and the same shared byte/time
ledger. Final policy/inventory failure invalidates usable observations before
projection. Projections perform no reads. This implementation does **not** use
the optional legacy disabled fallback on not-started final-budget exhaustion:
it returns UNKNOWN instead. A started/failed final read never becomes a successful
snapshot, and neither fallback nor semantic metadata restores execution authority.

## Safe export field allowlist

Do not provide original owner files. Remove prompts, message text, destinations,
error bodies, environment/configuration, credentials, proposal bodies and refs
before constructing these records. This package does not perform that export.
Unknown fields are rejected as `export_invalid`; raw input bytes and exception
text are never echoed. IDs must be public-safe; lexical validation cannot prove
that a string is not a secret. JSON uses the existing strict decoder and limits.

### Jobs: `agent_evidence_hermes_jobs_v1`

Exact top-level fields: `schema`, `jobs` (at most 512 records). Each record allows
only the following fields; `id` and `schedule` are required.

| Field | Contract / missing-value semantics |
|---|---|
| `id` | Unique public-safe identifier; duplicate IDs are FAIL |
| `enabled` | Boolean, default true; non-boolean invalidates export |
| `state` | `scheduled`, `error`, `paused`, `completed`; missing/null/blank defaults by enabled; other values are unknown |
| `schedule` | `{kind: interval, minutes: integer 1..525600}`, `{kind: once, run_at: timestamp}`, or `{kind: cron, expr: string}`; exact keys |
| `last_status` | `ok` / `error`; missing/other is unknown for active jobs |
| `last_run_at`, `next_run_at` | Nonnegative finite epoch seconds or UTC ISO timestamp; missing/invalid is unknown |
| `execution_error`, `delivery_error` | Boolean flags, never error text; missing/non-boolean is unknown for active-job health |
| `deliver` | Destination-free platform string, list of strings, or comma-separated strings; rules below |
| `script` | Optional null or string <=128 characters; only the exact registered basenames below match |
| `no_agent` | Must be exactly true for the two local-only registration checks |

Cron expression support is structural: five fields and optional sixth year field,
numeric lists/ranges/steps or `*`, with bounded ranges. Named weekdays/months,
macros and owner-specific grammar are not translated. No schedule is executed or
next run independently calculated. A valid shape is not evidence a job ran.

Active means enabled and state scheduled/error. Disabled, paused and completed
records cannot turn historical failures into a current failure. Counters overlap:
`historical_observed_failures` includes inactive/stale/future records; recent is
within 24 hours; active-recent and scheduling-error counts govern current FAIL.
Stale/future/unknown timing/status, unknown states, malformed/unresolved routes,
o active jobs, unknown or overdue next runs prevent health PASS. A conclusive
active-recent or scheduling failure takes priority over route/timing ambiguity.

Routes: null, empty string or an empty/all-empty string list default to local.
Whitespace/comma-only scalar strings are malformed. Lists split embedded commas;
non-string members remain malformed. `local` is case-sensitive. Built-in platform
names are case-insensitive (telegram, discord, slack, whatsapp, signal, matrix,
mattermost, homeassistant, dingtalk, feishu, wecom, wecom_callback, weixin, sms,
email, webhook, bluebubbles, qqbot, yuanbao). `origin` and case-insensitive `all`
remain unresolved, never expanded. Unknown tokens are malformed. Destination-
bearing tokens are outside this export contract: a recognized external platform
still proves a local-only policy conflict, but the token remains malformed and
no destination is returned. Explicit no-agent/enabled/local-only violations take
FAIL priority over another matching record's route ambiguity.

Registration matches **only** `experience_ratchet_watchdog.py` and
`memory_hygiene_dream_cron.sh` for their respective systems, never suffixes,
absolute paths, inferred scripts or executed commands. Passing registration means
configuration readback, not execution or successful delivery.

### Other exports

Each object must contain exactly the listed fields:

| Schema | Fields besides `schema` | Meaning |
|---|---|---|
| `agent_evidence_hermes_heartbeat_v1` | `heartbeat_at`, `success_at` | Finite nonnegative epoch/UTC times, no future values. FAIL if either age >=180s or heartbeat-success >120s. Fresh PASS is only a timestamp signal; no writer/run identity. |
| `agent_evidence_hermes_proposal_v1` | `observed_at`, `entry_count` (integer 0..1000000), `write_blocked` (bool), `auto_trim_memory` (bool) | Unsafe write policy FAIL takes priority over timing ambiguity. Otherwise future/invalid/>48h metadata UNKNOWN; even safe fresh metadata UNKNOWN because producer identity is unbound. No body read. |
| `agent_evidence_hermes_status_v1` | `dirty` (bool), `record_count` (integer 0..1000000) | Always UNKNOWN producer identity, not verified Git acquisition. No paths/status body. |

Presence keys bind explicitly admitted regular files, not owner-relative defaults.
The bounded observer hashes their bytes; it does not execute or parse scripts.
Missing/unreadable targets are UNKNOWN (conservative acquisition failure), not
proof the corresponding feature is absent on a real host.

## Static 21-disposition catalog

| System | Check | Input / supported disposition |
|---|---|---|
| hermes-core | hermes_doctor | UNKNOWN, native execution disallowed; zero target I/O |
| hermes-core | post_update_check | UNKNOWN, full post-update execution disallowed; zero target I/O |
| hermes-core | dirty_worktree_awareness | status; UNKNOWN producer unbound |
| cron | cron_list_readback | jobs; structural PASS, invalid UNKNOWN / duplicate FAIL |
| cron | cron_error_cluster_watch | jobs; current supported failure FAIL, incomplete UNKNOWN, otherwise scoped PASS |
| cron | cron_ticker_heartbeat_watch | heartbeat; timestamp-only PASS/FAIL/UNKNOWN |
| cron | gateway_manual_restart_rogue_watch | UNKNOWN process identity; zero target I/O |
| delivery:local | delivery_job_config_readback | jobs; configuration-only PASS/UNKNOWN |
| delivery:local | delivery_failure_watch | jobs; always UNKNOWN run-route outcome |
| delivery:local | cron_output_readback | UNKNOWN run-output identity; zero target I/O |
| delivery:telegram | delivery_job_config_readback | jobs; configuration-only PASS/UNKNOWN |
| delivery:telegram | delivery_failure_watch | jobs; always UNKNOWN run-route outcome |
| experience-ratchet | experience_ratchet_cli_present | explicit same-name binding; presence-only PASS |
| experience-ratchet | experience_ratchet_watchdog_script_present | explicit same-name binding; presence-only PASS |
| experience-ratchet | experience_ratchet_watchdog_cron | jobs; exact registration PASS/FAIL/UNKNOWN |
| memory-hygiene-dream | memory_hygiene_dream_script_present | explicit same-name binding; presence-only PASS |
| memory-hygiene-dream | memory_hygiene_dream_cron_wrapper_present | explicit same-name binding; presence-only PASS |
| memory-hygiene-dream | memory_hygiene_dream_cron | jobs; exact registration PASS/FAIL/UNKNOWN |
| memory-hygiene-dream | memory_hygiene_dream_latest_proposal_readback | proposal; unsafe FAIL, safe UNKNOWN |
| model-providers | provider_static_readiness | UNKNOWN unbound static evidence; zero target I/O |
| model-providers | provider_health_watch | UNKNOWN provider execution disallowed; zero target I/O |

Acquisition missing/denied/drift/timeout outcomes can supersede semantic results.
Disabled bound targets are N/A only under a successful stable final observation;
they stay required and in the gap count. Six forbidden checks remain UNKNOWN,
not N/A and not silently omitted. Delivery configuration is never delivery proof.

## Verification limits

Synthetic truth tables and real installed worker/CLI tests cover the above
contract, not compatibility with an upstream release. Loaded-code/source closure
and root/ancestor checks are implemented. CI is configured but not yet executed;
only local macOS CPython 3.11 artifact execution is demonstrated. Hermes runs
retain `complete=false` while required UNKNOWN dispositions remain, unlike complete
generic runs. All reports retain `certified_healthy=false`; no release is implied.
