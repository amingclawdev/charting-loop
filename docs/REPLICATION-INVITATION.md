# Invitation to replicate the Corridor method

## Two evidence dimensions worth testing

### 1. Matched evidence: 20/20 versus 15–16/20

Within each `production-planning` pair, the benchmark task, model, runtime, limits,
QA policy, and evaluator were held fixed. The frozen-Corridor Treatment passed
**20/20 in all three matched pairs**. Task-only Control passed **16/20, 16/20, and
15/20**.

The mechanism hypothesis is not that Corridor makes the model smarter. It is that a
task-conditioned, executable, replayable Corridor lets the same model act against
joined global constraints instead of relying on local context alone. The
[case detail](PRODUCTION-PLANNING-RESULT.md) describes the observed mechanism and also
discloses an evaluator semantics discrepancy.

This is a repeated descriptive single-task matched pilot. It is not benchmark-wide or
multi-task causal evidence, and it does not establish that the mechanism generalizes.

### 2. Transfer-motivating engineering evidence: 10/19 to 19/19

For the different `ico-path-patch` task, an
[official maintainer issue](https://github.com/harbor-framework/terminal-bench/issues/1453)
reported **“Best grader result: 10/19”** and said no recorded agent attempt had combined
all required repairs within the original 5,400-second limit. After same-task adaptive
development of a Corridor-supported workflow, our job 009 passed **19/19 official
verifier checks**, received **reward 1.0**, and completed within that same
**5,400-second limit**.

This second observation is an engineering result with incomplete Method conformance
and no matched Control. It is not an accepted leaderboard submission, does not
establish a world-first result, and does not show that every model failed. It motivates
transfer testing; it is not a second independent efficacy replication. Read its
[attempt chronology and limits](ICO-PATH-PATCH-RESULT.md).

Together, the observations pose the question for an independent study: can a fresh
builder use the frozen method to construct a useful Corridor for a fresh, distinct,
unseen multi-step task, without solution-bearing context? Follow the
[replication quickstart](REPLICATION-QUICKSTART.md) and submit every positive, null,
negative, blocked, timeout, invalid, or unscored outcome through the public-safe
[Corridor replication report](https://github.com/amingclawdev/charting-loop/issues/new?template=replication-report.md).

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

The first authorized public release is now live. It publishes six current sanitized
matched-arm summaries—Treatment and Control for each of CL-030, CL-031, and CL-032—
plus a separate `ico-path-patch` job-009 engineering summary. The machine registry
contains thirteen append-only rows: six historical arm records, six superseding
matched-arm records, and the separate engineering record. The public index therefore
covers two distinct tasks, but only `production-planning` has a matched comparison.
In short, the current matched package has six sanitized arm summaries; the job-009
engineering record is separate rather than a seventh causal-evidence arm.
The underlying databases, SQL, detailed logs, raw sessions, trajectories,
solution-bearing services, credentials, and internal Git history remain sealed. These
are descriptive research records, not accepted benchmark submissions or leaderboard
results.

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
   session. In Treatment, both Worker and QA can access the same exact frozen Corridor.
   In Control, neither Worker nor QA can access any Corridor; both receive the task-only
   condition.
4. Hold the task bytes, model, tools, budgets, QA instruction, one bounded rework rule,
   and official evaluator fixed across arms. Preserve every completed, failed, blocked,
   timeout, and infrastructure-invalid attempt.

The builder is not a treatment arm. Independent QA is the same role and policy in both
arms; its Corridor visibility follows its arm. The intended difference is whether both
task roles can use the exact frozen Corridor.

## What an independent report should answer

A useful public report states the exact frozen identities, the intended arm difference,
all attempt statuses and official scores, separate construction and task-run costs, and
a short explanation grounded in observable evidence. It also states contamination and
network conditions, limitations, and content digests for sealed artifacts.

Review the current descriptive observations in
[`EXPERIMENT-RESULTS.md`](EXPERIMENT-RESULTS.md). They are examples of auditable result
boundaries, not a target that a replication should reproduce.

## Running or publishing a study

Start with the public
[`REPLICATION-QUICKSTART.md`](REPLICATION-QUICKSTART.md). It pins a starter kit and
Method identity, states prerequisites and participant-paid cost boundaries, and links
the public-safe
[Corridor replication report](https://github.com/amingclawdev/charting-loop/issues/new?template=replication-report.md).
That report is the Charting Loop project's research intake. It does not upload a job to
Harbor, confer benchmark acceptance, or create a leaderboard entry.

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
