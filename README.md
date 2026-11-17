[English](README.md) | [简体中文](README.zh-CN.md)

# agent-evidence (developer preview)

**Give Codex or Claude Code real, bounded local file observations—not another “done” claim.**
Explicitly select files, invoke the skill, and get independent kernel readback with
PASS / FAIL / UNKNOWN. No hand-written manifest, inventory or receipt is needed.
This preview verifies file readability / byte identity and explicit typed JSON
scalar equality (for example `config.json` → `version` equals integer `2`). It
does **not** prove tests ran/passed, general business correctness, or whole-task
completion. It is not the full Hermes/MOS stack or production certification.
Codex has native invocation evidence; Claude installation/discovery is tested,
but actual model invocation remains **NOT VERIFIED** (expired OAuth; user login gate).

## Install for your tool

Requires Python 3.11+, local POSIX storage, and an already installed/authenticated
Codex or Claude Code CLI. No PyPI release is assumed. From this source checkout:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install .
# Choose ONE, with your existing project's absolute physical path:
agent-evidence-project install --tool codex --project /absolute/path/my-project
agent-evidence-project install --tool claude --project /absolute/path/my-project
```

Keep this environment on PATH when starting your tool in `my-project`.
Restart an existing tool session after installation. Codex gets a project skill in
`.agents/skills/agent-evidence`; Claude Code gets one in
`.claude/skills/agent-evidence`. These are **native project skills**, not a shared
plugin/extension installation protocol. No global config, hooks or MCP is installed.
**Installation does not run checks. Automatic model invocation is disabled.**

### Codex

```text
$agent-evidence Verify config.json field version equals JSON integer 2 in this project. Write evidence to /absolute/path/my-project-evidence-001. Report scoped acceptance and observation separately; do not claim tests ran or whole-task completion.
```

### Claude Code

```text
/agent-evidence Verify config.json field version equals JSON integer 2 in this project. Write evidence to /absolute/path/my-project-evidence-001. Report scoped acceptance and observation separately; do not claim tests ran or whole-task completion.
```

Replace the example with an existing, explicitly authorized, public-safe file.
The evidence directory must be **new and outside the project**, with an existing
physical parent (no symlink components). No files are selected automatically.
The helper creates a private `.agent-evidence-<random>/` control directory inside
the project and reads the selected originals; it does not copy their bodies.
Do not select secrets. Control manifests contain selected relative paths.

### Without a model / troubleshooting

```sh
agent-evidence-project check --project /absolute/path/my-project \
  --output /absolute/path/my-project-evidence-002 --expect-json config.json version '2'
# Or --json config.json for readability only (acceptance UNKNOWN).
# Or --file README.md for presence / readable byte identity.
```

`OUT/report.json` is the unchanged kernel report; `OUT/integration.json` and stdout
summarize the scope. Read the verdict, not just the process exit:

| Scoped acceptance | Meaning |
| --- | --- |
| PASS | Explicit typed field equality holds on independently verified observation bytes |
| FAIL | Field exists on verified bytes but does not equal the typed expectation |
| UNKNOWN | No expectation, missing field, invalid JSON, unavailable evidence or byte drift |

`observation_verdict` retains kernel semantics separately. Field paths are bounded
dot-separated ASCII object keys, not expressions. Expected values are explicit JSON
scalars (not objects/arrays), recorded in the report; **never supply secrets**.
Types are exact: `true` differs from `1`, `2` differs from `2.0`.

**The check exits 1 even for PASS**: `task_verdict=UNKNOWN`, `complete=false`,
`certified_healthy=false`. Exit 2 means invalid invocation/admission. Install and
uninstall exit 0 means only that installation action succeeded. A file saying
`{"complete":true}` or a synthetic fixture never proves completion.

## Uninstall

```sh
agent-evidence-project uninstall --tool codex --project /absolute/path/my-project
agent-evidence-project uninstall --tool claude --project /absolute/path/my-project
```

Only the byte-identical installed skill is removed. Edited or extra files cause
refusal; neighboring settings/skills are untouched. Evidence and control directories
are retained for your review. See [integration details and limitations](docs/tool-integrations.md).

## Advanced / status

- [Kernel installation, synthetic examples, CI record and limits](docs/kernel-guide.md)
- [Architecture](docs/architecture.md), [contracts](docs/contracts.md), [threat model](docs/threat-model.md)
- [Hermes adapter](docs/hermes-adapter.md), [verification notes](docs/verification.md)

The kernel remains unchanged by this integration. Its check revision identifies
kernel code, not the skill/helper. Existing CI evidence does not certify this new
integration. The contracts are evolving; there is no production release approval,
business E2E proof or cryptographic attestation.

[MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md)
