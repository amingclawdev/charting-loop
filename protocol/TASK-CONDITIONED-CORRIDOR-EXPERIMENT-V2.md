# Task-conditioned Corridor experiment — protocol v2

This is prospective runner/evaluator guidance. It does not reinterpret any previously
frozen STUDY or RUN, add rules to a frozen method package, or constrain the builder's
implementation. A new STUDY binds these exact bytes through its `protocol_ref`; the
historical unversioned protocol remains available for studies that already froze it.

## Intended comparison

This design measures the result of a freely built, task-conditioned Corridor branch
service being consumed during an official benchmark task. The official task is the only
task requirement. Candidate schemas, qualification chains, warranties, governance
receipts, QA outcomes, and ledger continuity are evidence surfaces, not admission or
scoring requirements.

Freeze the TaskSet, Study, task constraint datum, protocol ref, analysis intent, and all
runner-side policies before any builder, Worker, or QA session. Builder- and agent-visible
inputs contain no prior result, task-specific repair hint, hidden test, verifier body,
score, governance instruction, or audit-ledger content.

For this design, use `charting-loop/task-constraint-datum/v2`; v1's frozen
`no-repair-after-pair-freeze` policy describes a different experiment and cannot be
silently reinterpreted.

## Build the treatment service

1. Freeze the exact public task instruction and environment, benchmark/evaluator
   identities, model/runtime configuration, limits, seed/retry policies, and the
   cataloged Paper 2 research input.
2. Start a fresh builder session. Give it only those frozen public inputs and the neutral
   objective: build and commit a Corridor branch service that may help a later agent
   complete the official task.
3. Do not prescribe an API, schema, language, file layout, database, retrieval method,
   prompt, or implementation strategy. The builder may create code and persistent state
   as it judges useful. Record the exact bytes it saw.
4. Freeze the full service commit, tree, startup material, and content identities. A
   branch name is only a locator.

The builder is not a task arm. Construction time, usage, retries, and resources are a
separate cost bucket.

## Construction QA

A fresh construction-QA session may assess the exact frozen service revision against
the public task, neutral objective, and observable service behavior. It is outside the
matched pair, cannot edit, and receives no hidden evaluator material, prior score, or
solution-shaped hint. Its assessment is `pass`, `fail`, `blocked`, or `not_assessed`.

If construction repair is allowed, freeze its count before builder dispatch. Each repair
creates a new revision and preserves earlier assessments. Construction-QA failure,
service-start failure, and an exhausted repair budget remain observed evidence; none
prevents the matched task pair from running or being scored.

## Matched Worker-QA pair

Use pristine environments. Each arm has a fresh Worker and a separate fresh Independent
QA session. Match the official task bytes, public environment, model, tools, runtime
limits, evaluator, seed/retry policies, QA instruction, QA timing, permissions, budget,
feedback visibility, and exactly one bounded Worker repair opportunity.

- Treatment alone receives the frozen builder-authored service and one minimal consume
  instruction that identifies access without adding a solution hint or restating the
  paper. It must attempt consumption and continue the official task if the service fails.
- Control receives only the official task and has no service access.

Each Worker first produces a candidate result. Its QA reviews only the official public
task/environment, that exact result, and non-secret observable execution evidence. QA
cannot edit, add task requirements, or see hidden tests, verifier bodies, solutions, or
prior scores. The original Worker sees its QA assessment and receives exactly one
bounded repair turn. Freeze the repaired result even when unchanged, failed, blocked,
or not assessed. Then apply the official evaluator to both arms. No further repair,
tuning, replacement, or re-prompt occurs.

Agent-visible QA is a matched common intervention, not the Corridor treatment. A study
that varies visibility must freeze a separate Corridor-access × feedback-visibility
factorial design rather than folding feedback into Corridor access.

## Append-only Position ledger

The runner captures the same agent-invisible Position-ledger profile in both arms. Every
entry has a monotonic sequence, previous-entry digest, canonical entry digest, observed
time, actor/session and role, Position and Direction identities, exact before/after
WorldRef or closed WorldSpan, and content-addressed observable action/result/artifact
references. Corrections append; they never rewrite.

QA may cite the exact prefix it reviewed. Ledger presence is RAW evidence, not an
admitted Fact, certificate, Warranty, authority, PASS, or current C. Capture, continuity,
or QA failure is preserved and never suppresses official scoring. The ledger is not
shown to Worker or builder unless a separately frozen study declares that visibility as
an intervention.

## Runtime and egress

Disable public-internet egress from both task environments. Allow the same
benchmark-declared internal services in both arms; treatment alone may reach the frozen
Corridor service. Route model control-plane traffic through the same runner-held proxy
and freeze its exact allowlist outside prompts. Prefetch images and dependencies. Record
allow/deny metadata without credentials or payloads.

## Audit after scoring

Apply the frozen evaluator before experiment-specific audit. Preserve, when present:

- the official score and evaluator receipt;
- exact builder, Worker, QA, scored, and result commits and trees;
- observable agent, runner, tool, service, and QA logs;
- the Position-ledger prefix and entry digests bound to the scored revision;
- service invocation receipts distinguishing attempted, successful, failed, and absent
  consumption;
- pre-score container/rootfs identity and a content-addressed persistent-file manifest;
- database files, dumps, transaction/query logs, and named-volume identities; and
- construction cost separately from treatment/control Worker and QA costs.

Do not publish credentials, hidden reasoning, unrelated account history, hidden
benchmark material, or private/unlicensed data. Keep scored trees immutable. Add logs,
scores, databases, and audit reports only in a descendant result commit or separate
result branch with provenance to the scored commit.

Preserve service non-use, QA failure, ledger loss, and infrastructure failure rather
than deleting the run. A single matched pair is descriptive evidence, not a causal or
general performance claim.
