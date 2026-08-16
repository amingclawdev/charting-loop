# Exogenous experiment data

This tree holds neutral task, study, run, score, and optional-log data. It is outside the
method paper and outside a Candidate's authority surface.

```text
benchmarks/<benchmark-id>/<release>/TASKSET.json
studies/<study-id>/STUDY.json
runs/<run-id>/RUN.json
runs/<run-id>/SCORE.json          optional
runs/<run-id>/attachments/        optional, opaque, never indexed
local/                             private, ignored
registry/INDEX.json                generated
registry/EXPERIMENTS.md            generated
```

Missing logs or attachments mean `not_assessed` or `unknown`. They do not affect system
identity, participation, validation, baseline comparison, or ordinary score
eligibility. A SCORE is an evaluator-issued measurement Fact, not authority. Failed,
blocked, invalid, unscored, and infrastructure-error runs remain visible.
