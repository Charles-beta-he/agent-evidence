# Verification

This development slice was exercised on macOS 27.0 arm64, CPython 3.11.15, using
fresh non-editable wheel and sdist installations outside the source checkout.
Linux, Windows and Python 3.12–3.14 are untested; Windows observation is unsupported.
There is no complete-package acceptance or independent result-review approval.

Reproduce with build 1.4.0, setuptools 82.0.1 and a separate clean runtime venv:

```sh
python -m build --no-isolation
python -m venv /absolute/physical/path/runtime
/absolute/physical/path/runtime/bin/python -m pip install --no-deps dist/agent_evidence-0.1.0.dev0-py3-none-any.whl
/absolute/physical/path/runtime/bin/python -I -B -m unittest discover -s /absolute/path/to/tests -v
```

For sdist verification create a second clean venv, install setuptools 82.0.1,
then install the tar.gz with `pip install --no-deps --no-build-isolation` and run
the same tests. Test commands must not add source/donor directories to sys.path
or PYTHONPATH. Set temporary HOME/TMPDIR to synthetic directories. Tests generate
all fixtures; no business data is required. There are no pytest plugin hooks.

Coverage includes real worker and independent readback; malformed JSON; source
and receipt drift; policy denial with zero target-worker calls; unioned consumer
domains; missing policy/lock; no-follow/FIFO/hardlink boundaries; exclusive
publication contention; lock contention/recovery; hostile child pipe flooding,
non-reading stdin and pipe holders; CLI exit codes and body redaction. Narrow
policy mutation schedules use test hooks alongside real child probes.

Tests also cover loaded code/source equality, stale bytecode, helper replacement,
the actual `-m` entry code, root and ancestor replacement, and bounded 128-check /
1024-declaration reports. The read-only SHA-pinned CI workflow is configured,
not executed evidence; no Linux or additional Python-version pass is claimed.
The inventory tests cover three-way reviewed metadata/raw-byte pins, dependency
union before target open, B1 final negatives/late positives, B2 consumption expiry,
immutable one-shot freeze, six pure coverage views and supplied replay rejection.
The installed-artifact suite also exercises lock replacement/contention, actual
worker policy transitions, shared ledgers, and concurrent output ownership.

The procedure suite exercises exact grant hash/issuer/identity/action/scope and
valid intervals, acceptance/negative/cleanup record bindings, undeclared effects,
missing and malformed fields, declaration types and full digests, distinct IDs
and duplicate conflicts, latest failure/future/stale evidence, frozen inventory
expiry/clock rollback, disabled required denominators, missing/changed bundles,
and no-I/O/no-execution validation. Synthetic assertions are not business E2E.
Both artifact lanes exercise fixture --procedures, run, bundle evaluation,
negative evaluation and stored-report replay. The offline sdist lane can rebuild
the extracted sdist to a wheel with the existing build toolchain, then install
that wheel into a second clean runtime venv using --no-index --no-deps.

The Hermes suite covers the static 21 required dispositions, missing and forbidden
bindings, pure zero-I/O and worker pre-I/O refusal, active/legacy/inactive state,
historical versus current failures, schedule/timing uncertainty, route normalization
and explicit conflict precedence, exact script mapping, heartbeat-only freshness,
unbound producer/status/delivery, poison FIFO policy denial, shared budget, final
failure and real-worker body non-disclosure. Artifact lanes run the Hermes fixture,
CLI and negative current-failure scenario, with stored report readback.
These tests use only synthetic exports; they do not import donor or owner modules.
