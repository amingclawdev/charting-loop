# Runs

Every `runs/<run-id>/RUN.json` is immutable and may have one optional `SCORE.json`.
Attachments are optional opaque material and cannot affect validation or generated
identity. A branch is a hint; the complete WorldRef and artifact digests are identity.
SCORE is an optional evaluator-issued measurement Fact, not authority or a Warranty.

RUN records describe the prospectively frozen execution identity. Post-hoc public
causal evidence does not rewrite a RUN or SCORE. A public result manifest may instead
join a RUN-shaped attempt to observable command receipts, service revision, writeback
digests, a pre-score image, and the official evaluator receipt. Missing evidence is
recorded as unavailable or unsupported; it is never backfilled as a successful event.
Credential-bearing full logs, raw databases and SQL, hidden tests, and hidden reasoning
stay outside the public derivative while their exact digests and controlled custody
locators preserve the audit join.

For historical executions that predate complete RUN capture, a public-v2 result may
carry a typed execution amendment and attempt-disposition ledger. This is an
append-only description of what was observed, not a replacement RUN. Missing timing,
usage, seed, retry, or invalid-attempt receipts are null with an explicit
`unavailable` or `waived-no-posthoc-backfill` reason. The generated human projection
appears in `exogenous/registry/EXPERIMENTS.md`; `INDEX.json` remains the frozen RUN
index.
