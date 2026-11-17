# agent-evidence (development slice)

Bounded local evidence observations, **not production certification**.
This is an incomplete, unpublished implementation candidate. It is not the full
Hermes or MOS stack, nor the complete planned evidence package.

Implemented: explicit presence/strict-JSON checks, read-only cooperative policy,
a fixed bounded subprocess worker, exclusive receipts, and a second independent
child that reads the receipt and recomputes the observation. Presence is content
identity only. JSON success is object readability, not business validation.

Implemented inventory slice: explicit scope/attestation/catalog admission,
raw-byte declaration/source pins, one-shot immutable freeze, and six inventory
coverage views. `fixture --inventory` generates this synthetic contract.
Implemented procedure slice: exact admitted grant/assertion bytes, complete
declaration binding, distinct success IDs, latest-evidence freshness, acceptance,
negative and cleanup assertions, and allowed side-effect validation. This is
**validation of supplied evidence**, not independently verified business work.
`evaluate` validates explicit procedure bundles; stored diagnostic reports remain
UNKNOWN and cannot restore live admission.

Implemented Hermes slice: a fixed 21-disposition catalog, versioned explicit
sanitized inputs, job/route/registration/timestamp semantics and forbidden checks
with zero target I/O. See [the field contract](docs/hermes-adapter.md).
This does not establish complete compatibility with any Hermes release.
Implemented: fixed-module executed-code/source equality, stale-cache and helper
drift rejection, root/ancestor identity checks, and bounded declaration/check
counts. A SHA-pinned read-only CI workflow is provided but has not run.
The cross-platform matrix remains unverified. The schemas are development
contracts, not a complete stable package. Do not use for certification.

## Install and exercise

Python 3.11 or newer and a local POSIX filesystem are required. Install a built
artifact (not editable):

```sh
python -m pip install dist/agent_evidence-0.1.0.dev0-py3-none-any.whl
agent-evidence --help
agent-evidence fixture --out /absolute/physical/path/demo-input
agent-evidence run --input-root /absolute/physical/path/demo-input --manifest manifest.json --output-root /absolute/physical/path/demo-output
```

Choose existing physical parent directories with no symlink components. Both
leaf destinations must be new. These are synthetic fixtures only; no host scan
or business export occurs. A successful scoped check can be `PASS`, but `run`
returns **1**, `complete=false` without complete inventory and procedure evidence.
Reports use `implementation_status=scoped_evidence_pipeline`. For an inventory example use
`fixture --inventory --out NEW_INPUT`, then the same `run` command. To replay a
stored report use `evaluate --input-root OUTPUT --bundle report.json`; this
returns 1 and `supplied_evidence_only`, never live admission.
For a complete scoped example, use `fixture --procedures --out NEW_INPUT`, then
`run`: valid fresh synthetic evidence returns **0**, `complete=true`, but always
`certified_healthy=false`. Missing, denied or invalid required evidence prevents 0.
Evaluate its explicit bundle with
`evaluate --input-root NEW_INPUT --bundle procedures.json` (exit 1, even when
supplied evidence is PASS; offline evaluation cannot restore live admission).
The fixture's synthetic `live_e2e` field is an assertion under test, not a claim
that the fixture generator executed a business procedure.
For the explicit Hermes example use `fixture --hermes --procedures --out NEW_INPUT`
then `hermes run --input-root NEW_INPUT --manifest manifest.json --output-root NEW_OUTPUT`.
The `hermes` report axis preserves all 21 required rows; byte-observation PASS
does not turn an UNKNOWN semantic result into success.
Exit 0 also requires complete scoped PASS for `run`. Invalid
invocation/schema/admission returns 2; admitted runs with negative or incomplete
evidence return 1. A receipt being written is never a completeness
claim. `report.json` is read back and stdout is JSON, with closed-code errors on
stderr. Input bodies and child stderr are never returned.

```python
from agent_evidence import run_checks
report = run_checks('/absolute/physical/path/demo-input', 'manifest.json',
                    '/absolute/physical/path/another-output')
assert report['certified_healthy'] is False
```

All supplied IDs must be public-safe. Format checks cannot prove an ID is not a
secret. Roots are represented in receipts by device/inode digests, not paths.
No environment fallback, HOME expansion, owner imports, execution plugins,
network calls, repair actions or policy writers are provided.

## Status and limits

The only exercised host/version is recorded in `docs/verification.md` after
artifact verification. Linux and other Python versions require execution before
being called supported. Windows observation is unsupported. There is no release
approval, production certification, business E2E proof or cryptographic attestation.
See [contracts](docs/contracts.md) and [threat model](docs/threat-model.md).
