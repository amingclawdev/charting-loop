# `ico-path-patch` engineering result

This page is the public-safe record for the second distinct benchmark task represented
in this repository. It summarizes the full-method smoke sequence without publishing
the challenge binary, patched binary, patch generator, hidden verifier material, raw
role transcripts, credentials, or solution-bearing failure details.

[Return to the experiment result index](EXPERIMENT-RESULTS.md).

## At a glance

- Task: `terminal-bench/ico-path-patch` from Terminal-Bench 3.0.
- Latest valid run: `charting-loop-tb3-ico-path-patch-008`.
- Agent condition: `gpt-5.6-sol`, maximum reasoning effort, Modal, zero automatic
  retries, Charting Loop method v7, Agent v0.8.1.
- Result: **15/19 verifier checks passed; official reward 0.0**.
- Classification: **valid method failure**. There was one completed trial, no trial
  exception, and no retry.
- Scope: a same-task engineering and recovery observation. It is not a matched
  Treatment/Control experiment, a new-task sample, a passing benchmark result, an
  accepted leaderboard submission, or evidence that the complete method caused the
  score.

Fifteen passing checks are useful diagnostic signal, but the benchmark's binary
outcome remains failure. This page never converts the partial check count into a pass.

## External comparison, with its boundary

On 2026-07-31, the official benchmark maintainers reported **“Best grader result:
10/19”** while asking whether this task was reproducible within its original
5,400-second limit. The [official task issue](https://github.com/harbor-framework/terminal-bench/issues/1453)
also said that no observed agent had combined the requested repairs into one
reproducible passing patch within that condition. On 2026-08-09, a maintainer closed
the issue by stating that all tasks were being moved to an eight-hour timeout.

Our 15/19 is therefore above the maintainers' reported 10/19 reference under the
original 90-minute setting. This is a comparison of verifier subchecks, not a current
eight-hour leaderboard maximum, not a matched same-model Control, and not a rank. The
project's Harbor upload failed on a profile-identity requirement after local scoring,
so the run has no accepted official leaderboard entry.

## Attempt chronology

| Job | Disposition | What it established | Adjustment carried forward |
| --- | --- | --- | --- |
| `002` | Launcher-invalid | A short task filter selected no dataset member; no task environment or model work started. | Pin the canonical `terminal-bench/ico-path-patch` filter and never reuse a job identity. |
| `003` | Runtime-invalid | Modal reached the evaluator, but the role runtime could not find Codex; the fallback Corridor was not method output. | Add fail-closed runtime and credential preflight before any paid role. |
| `004` | Runtime-invalid | Codex installed, but Agent v0.5.1 searched the wrong runtime home and stopped before paid model work. | Resolve and exercise the installed CLI from the same fresh Linux role environment. |
| `005` | Valid method failure, reward 0.0 | Method v4 built a large acceptance ledger, but construction closure remained unresolved and fixed phase budgets expired. | Add task-neutral work rows, capability records, and advisory reminders; do not import task answers into the SDK. |
| `006` | Valid method failure, reward 0.0 | Method v5's fixed per-phase allocation stopped Worker before a complete deliverable entered custody. | Replace phase budgets with one task deadline and freeze every complete Worker improvement for final restore. |
| `007` | Runtime-invalid | Builder and Worker produced frozen state, but importing a read-only adapter created an undeclared byte before QA and grading. | Suppress Python bytecode creation in every role while retaining strict frozen-tree digest checks. |
| `008` | Valid method failure, **15/19**, reward 0.0 | Builder, Worker, and QA completed under one deadline; both task roles used the same frozen Corridor. The remaining miss was an internal acceptance-boundary completeness failure, not a launcher, account, timeout, or evaluator crash. | Keep the failure as method evidence; next iterations should reduce construction volume and require boundary-complete acceptance witnesses without embedding a task-specific repair. |

The four launcher/runtime-invalid identities are evidence about the harness, not agent
task performance. Jobs `005`, `006`, and `008` are valid method observations even
though all received reward 0.0. No identity is overwritten or reclassified as a pass.

## What changed in the reusable method and SDK

The sequence did not add a stored solution for this task. It added task-neutral
execution support:

- a work backlog whose rows bind scope, dependencies, applicable capability IDs, and
  replayable done-when evidence;
- a capability registry for reusable mechanics with versions, digests, contracts,
  applicability, and side effects;
- an append-only Position timeline plus advisory reminders, so Worker and QA can find
  the current row and reuse relevant mechanics without turning reminders into Gates;
- one absolute task deadline instead of fixed Builder/Worker/QA allocations;
- immutable, digest-bound Worker snapshots and separate cooperative QA assessments,
  with the latest complete Worker state restored before grading when time expires;
- a fail-closed doctor for dataset, account, CLI, architecture, spend-headroom, job
  identity, and frozen-adapter checks; and
- shared Corridor access for both Worker and QA. QA audits the original task
  requirements against the same frozen work rows and capabilities rather than acting
  as an external judge that cannot inspect the Corridor.

These changes are generic scaffolding. Role labels are cooperative provenance, not an
operating-system permission boundary, and reminders are advisory rather than new
business-blocking Gates.

## Timing and construction diagnosis

Job `008` completed in 4,684.975 seconds wall time; agent phases consumed 4,605.638
seconds. Builder used 1,495.443 seconds, Worker 1,945.286 seconds, and QA 1,154.560
seconds. Builder did not consume the whole run. Its observed command round trips took
18.35 seconds; most Builder time was model work over a large acceptance ledger, work
backlog, task adapter, SDK inspection, binary inspection, and iterative hardening.

That diagnosis supports a general optimization target: preserve exact acceptance
coverage while making the construction representation smaller and more selective. It
does not justify copying this task's hidden failing boundary into the generic method.

## Identity and audit boundary

- Dataset content hash:
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
- Method identity: `charting-loop-method-v7`, source commit
  `c68813cea1aa1d1eeaafde69a3f35f71ffab6d0d`.
- Frozen Corridor digest:
  `sha256:1ce413d06b67d1f1b878c4159d5f4787acae03ae427d1626a2dfeb5f8f9a0695`.
- Uploaded SDK manifest digest:
  `sha256:d5da5c8b8b12ed3259000a73c2bcb9e624175ccfb17e891d4fc5de4858badbef`.
- Frozen Corridor file hashes matched the Builder manifest; structural validation and
  source mapping passed. Definition closure remained incomplete, construction
  readiness remained unresolved, and `task_ready` was false.
- QA's effective outcome was `not_assessed` because its emitted closure state was
  internally contradictory. Grading still ran against the frozen Worker submission,
  as required by the no-QA-gate policy.

Raw custody remains sealed because it contains a live benchmark problem, a
solution-bearing binary patch, detailed failure witnesses, role transcripts, and
authentication-bearing operational logs. Public auditability is provided here through
exact task/method identities, digests, timings, disposition history, and the official
score. Publication of the raw bytes would change the benchmark and leakage boundary;
redacting subscription and profile tokens alone would not make solution bytes safe.

## How to interpret this task beside `production-planning`

`production-planning` supplies three counted matched pairs on one task. Four Treatment
executions were observed at 20/20, but one belonged to an infrastructure-invalid pair
and remains noncounting. This page adds a second task and shows that the dynamic
Builder/Worker/QA pipeline can construct and consume a Corridor under a different task
shape, but the scored run still failed and has no matched no-Corridor arm. The combined
public record therefore supports two-task engineering coverage, not multi-task
efficacy or a general causal claim.

For the matched evidence, read the
[`production-planning` task result](PRODUCTION-PLANNING-RESULT.md). For navigation,
[return to the experiment result index](EXPERIMENT-RESULTS.md).
