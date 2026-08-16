# Invitation to replicate the Corridor method

## Why this experiment exists

The idea began in Aming Claw, while applying the paper's theory to real agent workflows.
In that practice, we found that an agent could use the theory as a diagnostic method:
compare the actual work state, the governing objective and rules, and the legal next
action, then identify when those elements had drifted apart. This showed a practical use
for the theory and generated the Corridor hypothesis; it did not establish that Corridor
works.

The next step was to combine the theory with lessons from Aming Claw into a reusable
methodology. Under this methodology, a fresh builder agent receives the frozen
methodology and the task requirements, then constructs a task-conditioned Corridor for
that task. After the Corridor is frozen, matched task arms execute the same task under
the same model, runtime, budgets, QA policy, and evaluator: one arm works with Corridor
access and the other works without Corridor access. The comparison tests whether
converting the diagnostic theory into task-specific executable guidance changes
observable task performance or recovery.

The first authorized public release is now live. It publishes six sanitized arm
summaries—Treatment and Control for each of CL-030, CL-031, and CL-032—plus their
machine-readable manifests and registry records. The underlying databases, SQL,
detailed logs, raw sessions, trajectories, solution-bearing service, credentials, and
internal Git history remain sealed. These are descriptive research records on one
benchmark task, not a published benchmark submission or leaderboard result.

We invite independent teams to test the idea on a fresh multi-step task. The useful
question is not whether a team can reproduce one of this repository's solutions. It is
whether a frozen method can help a fresh builder create a task-specific aid that later
agents can use, under a matched comparison, without receiving solution-bearing context.

## Hypothesis

Given the same task, model, runtime, budgets, QA policy, and evaluator, access to a
frozen task-conditioned Corridor may change observable task performance or failure
recovery relative to a task-only control. Positive, null, negative, blocked, and invalid
outcomes are all informative when the comparison and its failure boundary are preserved.

The hypothesis concerns the complete method-instantiated process, not any one schema,
prompt, service, or component. A single pair is descriptive evidence. A causal method
claim needs a prospectively frozen design that also addresses construction effects,
such as a matched placebo-builder arm or method ablation.

## Corridor, in plain language

A Corridor is a task-specific navigation aid built before the task arms run. It helps a
later agent join three things: where the work actually is, what frozen objective and
rules apply, and which bounded next move is available. It can refuse when those pieces
do not line up.

A Corridor is not a stored answer, hidden evaluator, authority grant, or guarantee of
correctness. The fresh builder chooses its implementation freely from the public task
and frozen method package; the experiment then freezes those bytes before either task
arm begins.

## The simple matched design

1. Choose an unseen multi-step task and freeze the public task, environment, evaluator,
   model/runtime, limits, network policy, and method identity.
2. Give a fresh builder only those frozen public inputs and a neutral objective. Freeze
   the Corridor service it constructs and record construction cost separately.
3. Start a matched Docker pair. Each arm gets a fresh Worker and a separate fresh QA
   session. Treatment alone can access the frozen Corridor; control receives the task
   only.
4. Hold the task bytes, model, tools, budgets, QA instruction, one bounded rework rule,
   and official evaluator fixed across arms. Preserve every completed, failed, blocked,
   timeout, and infrastructure-invalid attempt.

The builder is not a treatment arm. Independent QA is the same intervention in both
arms, not part of the Corridor treatment. The intended difference is Corridor access.

## What an independent report should answer

A useful public report states the exact frozen identities, the intended arm difference,
all attempt statuses and official scores, separate construction and task-run costs, and
a short explanation grounded in observable evidence. It also states contamination and
network conditions, limitations, and content digests for sealed artifacts.

Review the current descriptive observations in
[`EXPERIMENT-RESULTS.md`](EXPERIMENT-RESULTS.md). They are examples of auditable result
boundaries, not a target that a replication should reproduce.

## Running or publishing a study

The authoritative prospective runner contract is
[`protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md`](../protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md).
AI operators should use the separate
[`AI-REPLICATION-RUNBOOK.md`](AI-REPLICATION-RUNBOOK.md), which is deliberately excluded
from experimental builder, Worker, and QA context. Before sharing any ref, a human must
complete [`PUBLIC-RELEASE-CHECKLIST.md`](PUBLIC-RELEASE-CHECKLIST.md).

Public summaries may include claims, statuses, scores, limitations, and content
digests. Keep executable same-task solutions, writeback SQL, databases, detailed logs,
raw sessions, trajectories, credentials, hidden evaluator material, and private
reasoning out of every public ref.

Replication is welcome whether the result agrees with the current hypothesis or not.
The contribution is an exact, inspectable comparison—not a preferred outcome.
