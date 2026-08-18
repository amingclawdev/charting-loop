# Join a Corridor replication pilot

This page is the shortest public path from “I want to test this” to a bounded report.
It is for a **fresh, distinct, unseen multi-step task**. Repeating one of this
repository's tasks is useful same-task engineering evidence, but it is not an
independent method-transfer replication or new-task evidence.

## What you are testing

A builder receives the frozen public task inputs and frozen Method, then constructs a
task-conditioned Corridor. After those Corridor bytes are frozen, matched task arms
run under the same task, model, runtime, total time constraint, tools, network policy,
QA policy, and evaluator:

- **Treatment:** both the Worker and its separate QA can read and use the same exact
  frozen Corridor.
- **Control:** neither the Worker nor its separate QA can access a Corridor; both see
  the task-only condition.

The builder is preparation, not a third task arm. Record its time, model/API usage,
and compute cost separately from Worker and QA costs. Preserve positive, null,
negative, blocked, timeout, invalid, and unscored outcomes alike.

## Frozen starter identities

Use these exact public identities for the first pilot, or preregister a different exact
identity before any builder or task role starts:

| Item | Pinned identity |
| --- | --- |
| Public starter repository | `amingclawdev/charting-loop` at commit `9ba540e2359545b1ae44684315d13c3601ac7713` |
| Frozen Method | `charting-loop-method-v8`, source commit `3c3813444a7d43d0a56837e9cb960be86ce26d06` |
| Method digest | `sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446` |
| Scope Datum digest | `sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af` |
| Authoritative experiment contract | [`protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md`](../protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md) |
| AI/operator procedure | [`AI-REPLICATION-RUNBOOK.md`](AI-REPLICATION-RUNBOOK.md) |

The starter repository is an implementation convenience, not Method authority. The
Method identity and its content digests remain separate. Record the exact task,
evaluator, model, runtime, container/image, dependency, network, budget, and analysis
identities used in your own pilot.

## Prerequisites and cost boundary

You need permission to use the chosen task and evaluator, a container-capable runtime,
model access for a builder and four task-role sessions, and a GitHub account to file a
report. Start with one private pilot and set a total spend limit you are willing to
bear. The participant pays their own model, benchmark, storage, and compute costs; this
project does not reimburse them. A report is welcome even if cost, policy, or
infrastructure blocks execution.

## Run sequence

1. Select one unseen, distinct multi-step task. Do not use `production-planning` or
   `ico-path-patch` as an independent-transfer claim.
2. Check out the exact starter commit above. Freeze the task/evaluator bytes, model and
   effort, runtime/image, tools, network policy, one total arm-time constraint, QA
   instruction, analysis plan, and allowed evidence surfaces.
3. Give a fresh builder only the allowed public task inputs, exact frozen Method
   package, and neutral construction objective. Do not provide this repository's
   completed task results, post-hoc analysis prompts, hidden evaluator material, or a
   same-task solution.
4. Freeze the builder's Corridor before either task arm starts. Record its commit/tree
   or content digest and construction cost. The frozen object must be identical for
   Treatment Worker and Treatment QA.
5. Run the matched arms. Treatment Worker and Treatment QA both receive the exact
   frozen Corridor. Control Worker and Control QA receive no Corridor. Keep every
   other declared condition matched.
6. Let each role freeze complete task-state versions within the single total arm-time
   constraint. If time expires, submit or restore the latest complete frozen version;
   do not invent a separate hidden stage budget.
7. Apply the same official evaluator to both final arm states. Preserve every attempt
   identity, status, score, failure boundary, role timing, construction cost, arm cost,
   contamination declaration, network declaration, and sealed-artifact digest.
8. Sanitize the report using [`PUBLIC-RELEASE-CHECKLIST.md`](PUBLIC-RELEASE-CHECKLIST.md),
   then file a
   [Corridor replication report](https://github.com/amingclawdev/charting-loop/issues/new?template=replication-report.md).

## Public-report boundary

The issue should contain claims, exact non-secret identities, statuses, scores, costs,
limitations, observable evidence summaries, and content digests. Do **not** paste
credentials, tokens, private paths, raw sessions, private reasoning, complete
trajectories, hidden evaluator material, databases, writeback SQL, detailed logs, or
solution-bearing services. Keep sealed artifacts under controlled custody and report
their digests and availability instead.

Filing the issue starts project triage only. It does not make a Harbor job public,
submit to an official benchmark, create a leaderboard row, or guarantee inclusion in
this repository's release registry. Those actions require their owners' separate
processes and approvals.
