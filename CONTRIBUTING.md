# Contributing

Use synthetic inputs only. Do not commit observations, local reports, real jobs,
credentials, venvs, build outputs or machine paths. Keep runtime stdlib-only and
all input authority explicit. Preserve third-party copyright and permission
notices; identify actual derivation rather than claiming a clean-room rewrite.

Run clean non-editable wheel and sdist tests as in docs/verification.md. Add
negative controls before changing guarantees. Do not substitute mocked successful
workers for actual subprocess acceptance. Mark incomplete requirements explicitly;
never turn UNKNOWN or N/A into healthy certification for convenience.
