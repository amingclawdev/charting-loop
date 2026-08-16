# Neutral exogenous run template

`RUN.json` is a runner-owned assignment envelope for corridor, task-only, or external
systems. It freezes the study/task join, runtime, trial/seed, exact WorldRef, and subject
artifact identity before scoring. It does not contain a score, certificate, warranty,
authority claim, or optional log.

The v2 `measurement_plan` is also frozen before execution. It requires stage-accounted
UsageReceipt and PackageCost schemas for construction, guided execution,
re-entry/revalidation, and retry, plus complete digest-bound raw evidence and an
independent replay. Actual usage, evidence, cost, and replay receipts stay in the
runner's append-only output and must bind this RUN digest; they are not written back
into RUN.json.

The v2 WorldRef fixes project/run/generation, repository/full base, environment, a
contiguous RAW ledger prefix, admission receipt/root and Rule, projector schema/algorithm,
and derived-state identity. Changing any field creates a different WorldRef; changing
the base, admission Rule, or projector starts a new generation. `subject.repository_url`
and `subject.base_commit` must equal the WorldRef values. Both supported RUN schemas
currently support exactly an `ai-agent` executor.

Copy it into `exogenous/runs/<run-id>/RUN.json`, replace all template values, and set
`template=false`. A missing score remains a valid registered/unscored run.

Legacy RUN v1 remains readable, but no measurement plan is inferred and it cannot meet
the v2 formal-evidence/direct-comparison gate. A complete plan alone also does not make
a run formally comparable.

```sh
python3 tools/exogenous_registry.py validate-run templates/run --allow-template
```
