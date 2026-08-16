# Task-constraint datum

`charting-loop/task-constraint-datum/v1` is a closed, runner-facing custody record for
one prospectively selected benchmark task. It freezes the study boundary before any
builder or task session. It is not method text, a builder prompt, a qualification
receipt, or an evaluator.

A TaskSet using `charting-loop/exogenous-taskset/v2` must give every task a
`constraint_datum` with `path` and raw-file `sha256`. The path is exactly
`tasks/<task-id>/TASK-CONSTRAINTS.json`. The ordered TaskSet digest includes both the
official task-input digest and the constraint-datum digest, so changing either creates
a different TaskSet.

The datum has these exact top-level objects:

- `source` pins the upstream HTTPS repository, release/tag, full commit, official
  instruction and metadata bytes, public environment source tree, evaluator source
  tree, and license. Source-tree manifest digests are SHA-256 over a canonical JSON
  array of `{mode,type,object_id,path}` records from `git ls-tree -r`, sorted by path.
- `builder` declares the task-conditioned study mode, the exact study-eligible Paper 2
  MethodRef, the three visible input classes, and one neutral objective. It does not
  select an API, schema, language, storage engine, retrieval strategy, prompt, or file
  layout.
- `pair` freezes matched treatment/control inputs and the only treatment differences:
  access to the frozen builder-authored service and a minimal consume instruction.
  Service startup, use, non-use, or failure is observed and never gates scoring.
- `runtime` freezes resource/time limits and requires the exact seed and retry policy
  to be resolved identically in the later RUN pair.
- `egress` disables task-container public internet, permits benchmark-declared internal
  services symmetrically, permits only treatment to reach the frozen Corridor service,
  and requires a runner-held exact control-plane allowlist in the RUN pair. Dependencies
  are pre-fetched; egress logs exclude credentials and payloads.
- `audit` starts after official scoring and preserves observable logs, exact Git and
  container identities, persistent files, and database/volume evidence when present.
- `excluded_inputs` closes the builder/task-agent exposure boundary around solutions,
  hidden tests, verifier bodies, prior results, governance/qualification instructions,
  task-specific hints, and private data.

The validator checks the closed field sets, source/digest formats, instruction join,
method status, matched-pair policy, egress boundary, post-score ordering, and exact
enumerations. Structural validity cannot prove that a later runner honored the datum;
RUN/SCORE records and post-score evidence establish what was actually observed.

## Worker-QA and Position-ledger v2

`charting-loop/task-constraint-datum/v2` preserves every v1 field and adds the closed
top-level objects `qa` and `position_ledger`. It is the executable datum for a matched
Worker-QA study. It freezes, without adding builder-visible text:

- a distinct fresh Worker and fresh Independent-QA session per arm;
- byte-identical public QA instructions, timing, permissions, budget, feedback
  visibility, and exactly one Worker repair opportunity in both arms;
- an identical, Worker- and builder-invisible append-only Position-ledger capture
  profile, including the entry schema, observation boundary, hash chain, QA-readable
  reviewed prefix, failure behavior, and retention policy;
- official scoring after the bounded repair round for every QA/service/capture outcome;
  and
- a separate construction-QA budget outside the matched task pair.

`qa.construction` fixes a distinct read-only construction-QA role, assessment timing,
builder-only feedback, one repair round, and a non-gating failure policy.
`qa.matched_pair` fixes fresh and mutually distinct Worker/QA sessions, a regular
non-symlink `QA-INSTRUCTION.md` and its raw digest, QA timing and permissions, a budget
digest, own-Worker-only feedback, the four reportable outcomes, one repair round, and
the requirement to preserve and score every outcome. `position_ledger` fixes
`charting-loop/position-ledger-entry/v1`, a runner-held identical capture policy,
Worker/builder invisibility, QA access to the reviewed prefix, SHA-256 previous-entry
linking, dispatch-to-score observation bounds, preserve-and-score behavior, and
content-addressed result-branch retention.

The v2 pair therefore changes `comparison_unit`, `shared`, `score_order`, and
`repair_policy` to the matched Worker-QA contract. The only paired treatment difference
remains access to the frozen builder-authored service and its minimal consume
instruction. QA and ledger policy are common conditions. If feedback visibility is
varied, it is a separately frozen Corridor-access × feedback-visibility factorial
design. Historical v1 data retain the exact no-repair contract and are never upgraded
by inference.
