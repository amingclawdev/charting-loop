# CL-031 Treatment — public result summary

Treatment is the experimental arm: the Worker received the same frozen
`production-planning` task as Control and had access to the frozen,
builder-authored Corridor service.

## Result

- Official evaluator replay: **20/20 checks**, reward `1.0`.
- Independent QA: `pass`.
- Rework: not required; zero repair attempts.
- Replay boundary: the original verifier launch was blocked by Docker address-pool
  exhaustion. After unused experiment networks were removed, the unchanged pre-score
  image was evaluated with a no-op replay agent and no Worker or database mutation.

## Interpretation

This is a completed descriptive score with post-hoc verifier replay, not an
unqualified direct verifier run. It is one arm of one matched pair on the same single
benchmark task used by CL-030 and CL-032.

The paired Control arm scored 16/20. Read the
[task-level comparison](../../../../docs/PRODUCTION-PLANNING-RESULT.md#cl-031).

## Custody boundary

The controlled source record is commit
`6b45cca3ce32d0ca1eefc062e3fda6104132f6f1`, tree
`b30ad584efb7abf42855b44e0cdaebf5f0ea7376`. Databases, SQL, detailed logs,
raw sessions, trajectories, and evaluator bytes remain sealed. The public
[MANIFEST.json](MANIFEST.json) binds this summary to selected source records by
digest and size.
