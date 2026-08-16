# Migration from pilot v1 to draft v2

V1 is preserved rather than silently reinterpreted.

| Concern | v1 location | v2 location |
|---|---|---|
| runner envelope | `templates/legacy-corridor-v1/` | `templates/run/` + `exogenous/` |
| builder artifact | nested `corridor/` in v1 envelope | `templates/corridor/implementation/` |
| method source | deleted `methodology/CORRIDOR-METHOD.md` | `method-paper/METHOD.md` only |
| theory catalog | `charting-loop/theory-index/v1` without publication roles | `charting-loop/theory-index/v2` with one exact public primary and explicit drafting provenance |
| authority logs | required structured v1 boundary | optional in core; opt-in strict profile |
| registry | `registry/`, schema v1 | `exogenous/registry/`, neutral schema v1 |

## Compatibility rules

- `charting-loop/corridor/v1` continues through the unchanged v1 validator path.
- `charting-loop/candidate/v2` dispatches to a separate, narrow validator.
- `charting-loop/theory-index/v1` remains readable and consumable by legacy method
  catalogs under its original unlabeled-provenance semantics.
- `charting-loop/theory-index/v2` requires exactly one `published-primary` theory and
  keeps consulted internal drafts explicitly non-primary; v2 role guarantees are not
  inferred for v1 records.
- The legacy registry accepts only `charting-loop/registry-entry/v1`.
- The draft v2 Candidate is not registry-eligible and cannot be builder treatment input.
- Existing v1 digests and semantics are not upgraded in place.
- A v1 experiment remains reproducible by using
  `templates/legacy-corridor-v1/` with the legacy registry commands.

## Data migration

Do not move a published v1 run into v2 by editing it. Preserve it in the v1 registry and
create a new neutral RUN that references immutable subject provenance. Scores are
evaluator-owned receipts. Optional logs stay optional and never become authority merely
because they are attached.

Before publishing a later method version, freeze the method bytes in a prior commit,
update its catalog entry, and independently decide whether `builder_eligible` may
become true.
