# Terminal-Bench 3 Builder generalization audit

Date: 2026-08-20

Backlog: `CL-092-BUILDER-CORRIDOR-GENERALIZATION-AUDIT`

Method condition: `charting-loop-method-v8`

Disposition: **no Method change from this evidence; route implementation questions to their owning layer**

## What this package is

This is a public-safe, results-only audit of three fresh Builder observations under the
frozen Method-v8 condition:

- `heat-pump-warranty`;
- `music-harmony`; and
- `bun-sourcemap-leak`.

It asks why constructing a task-conditioned Corridor consumed so much of the shared
task clock, which operations recur across domains, and which layer should own a future
repair. It does not publish task solutions, raw role transcripts, hidden evaluator
feedback, credentials, or generated submission bytes.

This is not a benchmark score, a matched comparison, a causal estimate, or evidence
that a proposed repair improves task performance. The three observations are a small
diagnostic cohort. The older `production-planning` and `ico-path-patch` results are
positive references only; neither is used to promote a component or estimate efficacy.

## Bottom line

The recurring cost is real, but most constructed bytes are not reusable Core. Across
the three frozen Corridors, only `METHOD-CAPSULE.json` was byte-identical. Their task
adapters shared only a function named `main`; pairwise function-name Jaccard overlap
was 0.013 to 0.076. Whole-adapter promotion would therefore preserve task specificity,
not remove it.

The useful common layer is narrower:

1. a machine-readable authoring contract;
2. one aggregate validator and identity-join report;
3. a bounded, read-only coupled-witness envelope that supports success and negative
   outcomes such as deny, hold, and refusal;
4. explicit handoff identities for `structurally_valid`, `task_ready`, and
   `officially_deliverable`; and
5. automatic construction telemetry.

Those items belong to SDK Core or Agent/Harness orchestration. Domain algorithms stay
in domain capabilities; exact requirements and operation algorithms stay in the task
adapter. The evidence does not justify changing frozen Method v8. A possible
source-derived Rule-authority clarification remains a candidate for prospective
falsification, not a Method-v9 conclusion.

## Evidence custody and limits

The source observations were copied from volatile execution storage before analysis
and committed to an access-controlled Git custody repository.

| Item | Identity |
|---|---|
| Custody commit | `ffc08ea3e4903512fc3a95f5d6b4f1941940def1` |
| Custody root tree | `94cd73d80c1987d092e9bb2875dd8727297875a6` |
| Retained paths | 246 |
| Audit-draft commit | `21ba85874b14fa817ebec66c0b62e4a1e9eee6e6` |
| Audit-draft tree | `b9087c0a209d35cc00a8983cc55c923572e63d68` |
| Audit-draft paths | 247 |

Retained evidence includes preregistration and deviation records, cohort summaries,
role artifacts, frozen Corridors, Position and freeze records, submission manifests,
timing/results, and verifier results. Recorded exclusions are interpreter caches,
compiled bytecode, task workspace/output bytes, and redundant job-level wrappers.

The repository has no off-host remote. Its current custody status is therefore
`local_git_immutable_but_not_off_host`: the commit and tree provide local byte identity,
but not disaster-resistant replication. This is an explicit closure blocker for
complete custody, not a reason to discard the audit.

## Reconstructed Builder timeline

Times below come from the retained runner records and role event streams. “First edit”
is measured from role-session start to the first patch operation, rounded to the
nearest second. “Operational replay” is the first real adapter check or capture, not a
text-only mention. Cost telemetry was unavailable. Harbor aggregate token fields were
null, but Builder role streams retained token counts.

| Run | Total task clock | Builder phase | First source edit | First acceptance validation | First operational replay | First task-ready freeze | Command groups | Frozen files / bytes | Builder tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| heat-pump-warranty | 7,200 s | 2,093.872 s | ~663 s | ~668 s | ~1,853 s | 2,107.517 s | 64 | 13 / 658,931 | 7,172,242 input; 6,913,280 cached; 99,627 output |
| music-harmony | 7,200 s | 1,463.095 s | ~494 s | ~631 s | ~1,008 s | not recorded; unresolved freeze at 1,463.558 s | 32 | 12 / 100,456 | 3,771,321 input; 3,619,584 cached; 67,243 output |
| bun-sourcemap-leak | 1,800 s | 1,772.116 s; task deadline reached | ~514 s | ~763 s | ~1,304 s | 1,773.850 s | 19 | 12 / 119,511 | 2,701,030 input; 2,555,392 cached; 80,062 output |

Further construction signals:

- SDK-source inspection command groups were 11, 5, and 2 respectively.
- Validator command groups were 9, 5, and 3 respectively.
- Adapter sizes were 79,104, 58,282, and 43,447 bytes.
- The largest acceptance ledger was 393,285 bytes with 239 items.
- No cost value is inferred from missing telemetry.

These observations make authoring and validation cost measurable. They do not show
that every pre-edit second is waste: task reading is legitimate work, so the observed
494–663 second pre-edit interval is only an upper bound for an authoring-discovery
target.

## Exact reuse diagnostic

A same-task Bun replay restored the frozen Corridor and measured first-valid freeze at
0.594 seconds, compared with 1,773.850 seconds during construction. It also restored
Worker/QA time and later obtained 33/36 checks.

This is a path and timing diagnostic only. It used the exact same-task artifact after
verifier feedback had already been observed, used a private runner, had no fresh
control, and did not satisfy the task. It is classified as contaminated and cannot be
reported as a pass, an efficacy estimate, a prospective validation, or a causal
effect.

## Reproduced conformance defect: nested freeze identity

The retained Bun replay also exposes a current implementation defect that is separate
from Method semantics and separate from QA JSON parsing:

1. the frozen `FREEZE.json` stores acceptance identity under its nested
   `acceptance_ledger` object;
2. the current `corridor_kit qa validate` path reads flat top-level fields instead;
3. on the retained, byte-identical QA assessment and freeze, the CLI normalizes the
   declared pass to `not_assessed`; and
4. calling the same normative QA decision with the nested frozen identity produces a
   valid `pass` with no errors.

The frozen file had no flat `acceptance_ledger_status`, `source_mapping_status`,
`definition_closure_status`, or `construction_readiness_status` fields. The CLI and
direct nested result therefore disagree on identical assessment bytes and frozen
identity.

Owner: **SDK runtime CLI field resolver**. The normative JSON parser is already
single-owned by `corridor_kit.acceptance::load_qa_json_text`; this reproduction is not
evidence for another parser or a Method change. No source repair is included in this
audit-only package.

## Candidate ownership and disposition

Every retained candidate has exactly one owner. Full machine-readable contracts,
falsifiers, and source-run mappings are in `AUDIT.json`.

| ID | Candidate | Owner | Disposition |
|---|---|---|---|
| M-01 | Construction-profile liveness boundary | Method invariant | Already substantially present in v8; no restatement/version bump |
| S-01 | Machine-readable Corridor authoring contract | SDK Core | Retain for prospective implementation/measurement |
| S-02 | Validate-all and identity-join report | SDK Core | Retain for prospective implementation/measurement |
| S-03 | Bounded coupled-witness envelope | SDK Core | Retain; must support pass, deny, hold, and refusal without becoming an oracle |
| S-04 | Single QA semantic owner | SDK Core | Already implemented; regression/conformance item only |
| S-05 | Nested freeze identity resolver | SDK Core | Retain as a narrow conformance repair; reproduced, not repaired here |
| H-01 | Latest structurally-valid Builder handoff | Agent/Harness | Retain with three separate identities |
| H-02 | Automatic construction telemetry | Agent/Harness | Retain; append-only, provenance-bound reporting |
| D-01 | Release/provenance/source-map primitives | Domain capability | Retain only as a single-domain candidate |
| D-02 | Public record/document evidence survey | Domain capability | Retain only as a single-domain candidate |
| D-03 | MusicXML structural inspection | Domain capability | Retain only as a single-domain candidate |
| T-01 | Exact Rule/Acceptance compilation and algorithms | Task adapter | Keep task-specific; never promote wholesale |

Rejected evidence:

- `R-01`: exact same-task Corridor reuse and its 33/36 result, usable only for path and
  timing diagnosis;
- `R-02`: hidden-evaluator failure identities, task answers, fixed offsets, private
  indicators, generated submission bytes, and task fixtures.

## Frozen-v8 delta audit

| Proposed idea | Method-v8 disposition | Owner / next test |
|---|---|---|
| Rule closure gets authority only from pinned sources, authorized precedence, stable identity, and preserved conflicts | Possible missing clarification; not established by this cohort | CL-093 prospective Method disposition; first test as conformance/validator semantics |
| Any canonical joined Position input change creates a new `PositionRef` | Already in v8 | No Method delta |
| Effective Direction is replayed at a content-addressed Position | Already in v8 | No Method delta |
| Counterfactual transition is hypothetical and read-only | Already in v8 | No Method delta |
| Construction invalidity is visible but non-gating for external grading | Already in v8 | Agent/Harness conformance |
| Coupled witness supports negative outcomes | Implementation envelope requirement | SDK Core |
| Separate structurally-valid, task-ready, officially-deliverable identities | Runtime handoff requirement | Agent/Harness |
| One QA parser/decision owner | Already implemented | Regression/conformance |
| Nested acceptance identity is read consistently from `FREEZE.json` | Implementation defect | SDK runtime CLI resolver |

The resulting Method disposition is `NO_METHOD_CHANGE_FROM_CURRENT_EVIDENCE`. This
audit is an input to the clean `CL-093` disposition row. The superseded `CL-091` design
must not be treated as implementation authority.

## Claim boundary

This package supports these limited claims:

- three Builders spent substantial portions of their task clocks constructing and
  validating task-specific Corridors;
- whole task adapters showed very low structural overlap;
- a smaller set of authoring, validation, handoff, and telemetry mechanics is a
  plausible cross-domain implementation target;
- the nested freeze identity defect is reproducible on retained bytes; and
- current evidence does not establish a Method-v9 requirement or an efficacy gain.

It does not support claims of benchmark improvement, multi-domain efficacy,
generalization, leaderboard rank, causal effect, or prospective validation. Any future
implementation must be evaluated on fresh tasks with frozen identities and explicit
falsifiers.
