# AI/operator replication runbook

> **Audience boundary:** this document is runner and AI/operator context. It **MUST NOT
> be exposed to experimental builder, Worker, or QA sessions**, in whole or in part.
> Those sessions receive only the inputs prospectively assigned to their role.

## Authority and interpretation

The authoritative runner contract is
[`protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md`](../protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md).
This runbook is an execution index for that protocol. It does not add method rules,
reinterpret a frozen study, or make an outcome valid. If this page and the authoritative
protocol differ, stop and follow the protocol; amend this projection separately.

The sole normative method source is [`method-paper/METHOD.md`](../method-paper/METHOD.md).
Freeze the MethodRef named by the study rather than substituting the current working
draft. Keep this runbook, governance instructions, previous outcomes, repair hints,
hidden evaluator material, and audit-ledger content out of every experimental prompt
and retrieval source.

## 1. Freeze before dispatch

Create the prospective Study and freeze all runner-controlled choices before starting a
builder, Worker, or QA session:

- official task instruction, benchmark release, task-constraint datum, environment,
  evaluator, and protocol bytes;
- model/version, reasoning profile, tools, public-network policy, runner/model proxy,
  limits, seed/retry policy, timeouts, and stopping rules;
- exact method commit and content digests;
- comparison unit, intended treatment difference, analysis intent, QA instruction and
  timing, one bounded Worker-rework rule, and any construction-repair allowance;
- evidence schema, cost-accounting fields, sanitization boundary, and artifact custody.

Verify that builder- and arm-visible inputs contain no previous result, task-specific
repair hint, same-task solution, hidden test or verifier body, score, governance
instruction, or operator audit content. Record content digests of the actual role input
bundles rather than relying on filenames or branch tips.

## 2. Construct and freeze the treatment

Start a fresh builder with only the frozen public task inputs, the study's exact method
package, and the neutral objective to build a Corridor service that may help a later
agent complete the official task. Do not prescribe its API, schema, language, storage,
prompt, or implementation strategy.

Record construction time and usage separately from task-arm cost. Freeze the complete
service commit, tree, startup material, and content identities before task execution.
A branch is a locator, not identity.

If the study permits construction QA, use a fresh read-only construction-QA session on
the exact frozen revision. Record `pass`, `fail`, `blocked`, or `not_assessed`. Apply
only the prospectively bounded construction-repair allowance; each repair creates and
freezes a new revision without rewriting earlier assessments. Construction failure
remains evidence and does not authorize an unplanned replacement.

## 3. Prepare the matched Docker pair

Create pristine treatment and control environments. Match official task bytes, public
environment, model, tools, runtime limits, evaluator, seed/retry policy, QA instruction,
QA timing, permissions, budget, feedback visibility, and Worker-rework allowance.

Dispatch a fresh Worker and a separate fresh independent-QA session per arm. Treatment
alone receives the frozen Corridor service and the minimal consume instruction declared
by the study. Control receives the official task with no service access. If the
treatment service fails, record attempted/failed consumption and require the Worker to
continue the official task; do not silently replace the service or alter control.

Disable public-internet egress in both task environments. Keep benchmark-declared
internal services matched and route model traffic through the same frozen runner-held
proxy. Treatment alone may reach the frozen Corridor endpoint. Prefetch dependencies
and record allow/deny metadata without credentials or payload bodies.

## 4. Run Worker, QA, and bounded rework

For each arm, preserve the same ordered lifecycle:

1. the fresh Worker produces and freezes its initial candidate result;
2. its separate QA reviews only the public task/environment, that exact candidate, and
   non-secret observable evidence;
3. QA records `pass`, `fail`, `blocked`, or `not_assessed` without editing the result or
   adding task requirements;
4. the exact original Worker receives its own QA assessment and, only as frozen by the
   study, gets one bounded rework turn; and
5. freeze the post-rework result even when unchanged, failed, blocked, or not assessed.

QA cannot see hidden tests, verifier bodies, solutions, prior scores, the other arm, or
this runbook. Do not add a second QA pass after repair unless a different prospective
study explicitly freezes that design. Do not replace failed sessions, tune one arm, or
select a favorable retry after outcomes are visible.

## 5. Score and classify every attempt

Apply the frozen official evaluator to both post-rework results. Experiment-specific
audit follows scoring; it must not change the scored state.

Record official score/evaluator receipts and distinguish task outcomes from
infrastructure state. A timeout, service-start failure, QA failure, ledger loss,
incomplete pair, or runner failure is preserved and classified rather than deleted.
Mark invalid/noncounting attempts explicitly and retain their predecessor relationship.
Never promote an observed score from an invalid attempt into a study result.

Treat a single matched pair as descriptive. Do not infer a causal method effect,
benchmark-wide efficacy, production readiness, semantic correctness, or real-world
authority from the score difference.

## 6. Preserve evidence without changing visibility

Bind evidence to exact commits, trees, task/environment/evaluator identities, and the
scored revision. When present, retain under controlled custody:

- builder, Worker, QA, repair, scored, and result identities;
- official score receipts and observable runner, tool, service, and QA records;
- append-only Position-ledger prefix/digests and service-consumption receipts;
- pre-score container/rootfs identity and persistent-file manifests;
- databases, dumps, SQL/transaction/query records, and named-volume identities; and
- separate construction, treatment, control, QA, and repair usage/cost accounting.

Corrections append; they do not rewrite attempts or scored trees. Put result evidence in
a descendant result commit or separate result branch with provenance to the scored
commit. Keep credentials, raw/private sessions, hidden reasoning, unrelated account
history, hidden benchmark material, and private or unlicensed data out of Git.

## 7. Produce the human summary and release candidate

The human summary includes every completed, failed, blocked, invalid, timeout, and
unscored attempt; the intended arm difference; official outcomes; infrastructure and
contamination facts; limitations; and digests for sealed artifacts. It must not expose
solution-bearing detail.

Build any public ref from a clean custody base with an exact allowlist. Solution code,
writeback SQL, databases, detailed logs, raw sessions, trajectories, and hidden
evaluator bytes remain embargoed or restricted. Follow
[`PUBLIC-RELEASE-CHECKLIST.md`](PUBLIC-RELEASE-CHECKLIST.md) against the exact candidate.
Scanner success is necessary but does not authorize publication; a human owner must
approve the exact remote and refs.
