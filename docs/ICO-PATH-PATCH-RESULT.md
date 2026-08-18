# `ico-path-patch` engineering result

This page is the public-safe record for the second distinct benchmark task represented
in this repository. It summarizes the full-method smoke sequence without publishing
the challenge binary, patched binary, patch generator, hidden verifier material, raw
role transcripts, credentials, or solution-bearing failure details.

[Return to the experiment result index](EXPERIMENT-RESULTS.md).

## At a glance

- Task: `terminal-bench/ico-path-patch` from Terminal-Bench 3.0.
- Latest valid run: `charting-loop-tb3-ico-path-patch-009`.
- Agent condition: `gpt-5.6-sol`, maximum reasoning effort, Modal, zero automatic
  retries, Charting Loop method v8, SDK v0.4.0, Agent v0.9.0.
- Result: **19/19 verifier checks passed; official reward 1.0**.
- Classification: **official task pass in a same-task adaptive engineering run**.
  There was one completed trial, no trial exception, and no retry. Complete Method
  conformance was not established: definition closure was incomplete and construction
  readiness remained unresolved.
- Scope: a same-task engineering and recovery observation. It is not a matched
  Treatment/Control experiment, a new-task sample, an accepted leaderboard
  submission, or evidence that the complete method caused the score.

Job `008` remains a valid 15/19 method failure. Its four failing verifier checks were
observed before general Method and SDK work strengthened acceptance-boundary
representation and job `009` ran. No task-specific solution bytes were placed in the
reusable SDK, but the sequence was informed by same-task verifier feedback. Job `009`
therefore does not retroactively turn the earlier outcome into a pass, make the
sequence an independent reproduction, or make it a controlled comparison.

## Public task difficulty snapshot

The strongest public comparison now comes from Harbor's own publicly readable trial
table for the exact shipped task content digest. At `2026-08-18T18:36:05Z`, before
job `009`, that table contained **59 completed trials across 11 exact
agent/model/reasoning configurations and 0 reward-1 passes**. With job `009` included,
it contained 60 completed rows: 59 at reward `0.0` and this one at reward `1.0`.

- [Frozen minimized dataset: all 60 public rows](../public/results/ico-path-patch/job-009/PUBLIC-TRIALS.json)
- [Public Harbor job: 19/19, reward 1.0](https://hub.harborframework.com/jobs/2e54f22b-69c3-4eef-b77c-02b28f183266)
- [Harbor's public-client source](https://github.com/harbor-framework/harbor/blob/main/src/harbor/auth/constants.py#L304-L312)

The snapshot is pinned to task digest
`sha256:0115a4136189b48da79070f9b3004dc4e0dfc1a60725c5acebdd7f380d037d14`
and has digest
`sha256:a360805445a70c298f430c16b845f826efcc59e516cc1ebd279fc88ee6230dc6`.
It retains only public trial/job ids, the three fields forming the exact
configuration key, reward, status, and timestamps. The public client key itself,
full configuration/environment payloads, creator or claimer identities, paths,
trajectories, and solution-bearing bytes are excluded.

This establishes the difficulty of the task in the observed public table and the
identity of our public pass. It does not establish that every model or private run
failed, that this was a world-first, that it is a leaderboard maximum, or that the
Method caused the result. This was the fourth scored same-task attempt in our adaptive
sequence and had no matched Control.

## External comparison, with its boundary

On 2026-07-31, the official benchmark maintainers reported **“Best grader result:
10/19”** while asking whether this task was reproducible within its original
5,400-second limit. The [official task issue](https://github.com/harbor-framework/terminal-bench/issues/1453)
also said that no observed agent had combined the requested repairs into one
reproducible passing patch within that condition. On 2026-08-09, a maintainer closed
the issue by stating that all tasks were being moved to an eight-hour timeout.

Job `009` completed all 19 verifier checks in 1 hour, 26 minutes, and 34 seconds. Its
agent elapsed time was 5,107.230 seconds, below the original 5,400-second task limit.
It demonstrates that this adaptively developed harness produced a 19/19 run under the
former time condition. It does not directly answer the issue's independent-agent
reproducibility question because earlier same-task verifier feedback informed the
development sequence. The currently available public issue history does not establish
a world-first result or leaderboard maximum. This run is not a matched same-model
Control, a rank, or an accepted Harbor submission.

## Attempt chronology

| Job | Disposition | What it established | Adjustment carried forward |
| --- | --- | --- | --- |
| `002` | Launcher-invalid | A short task filter selected no dataset member; no task environment or model work started. | Pin the canonical `terminal-bench/ico-path-patch` filter and never reuse a job identity. |
| `003` | Runtime-invalid | Modal reached the evaluator, but the role runtime could not find Codex; the fallback Corridor was not method output. | Add fail-closed runtime and credential preflight before any paid role. |
| `004` | Runtime-invalid | Codex installed, but Agent v0.5.1 searched the wrong runtime home and stopped before paid model work. | Resolve and exercise the installed CLI from the same fresh Linux role environment. |
| `005` | Valid method failure, reward 0.0 | Method v4 built a large acceptance ledger, but construction closure remained unresolved and fixed phase budgets expired. | Add task-neutral work rows, capability records, and advisory reminders; do not import task answers into the SDK. |
| `006` | Valid method failure, reward 0.0 | Method v5's fixed per-phase allocation stopped Worker before a complete deliverable entered custody. | Replace phase budgets with one task deadline and freeze every complete Worker improvement for final restore. |
| `007` | Project-caused harness-integrity invalid | Builder and Worker produced frozen state, but importing a read-only adapter created an undeclared byte before QA and grading. This was caused by our frozen-harness behavior, not by the benchmark runtime. | Suppress Python bytecode creation in every role while retaining strict frozen-tree digest checks. |
| `008` | Valid method failure, **15/19**, reward 0.0 | Builder, Worker, and QA completed under one deadline; both task roles used the same frozen Corridor. The remaining miss was an internal acceptance-boundary completeness failure, not a launcher, account, timeout, or evaluator crash. | Keep the failure as method evidence; next iterations should reduce construction volume and require boundary-complete acceptance witnesses without embedding a task-specific repair. |
| `009` | Official task pass with incomplete Method conformance, **19/19**, reward 1.0 | Method v8 execution completed under the original 5,400-second limit. Worker and QA queried the same frozen Corridor; six Worker snapshots preserved complete states, and the sixth was restored for grading. Definition closure was incomplete, construction readiness unresolved, and QA normalized to `not_assessed`. | Index the engineering result while disclosing same-task verifier-feedback-informed adaptation and without treating changed Method, SDK, Agent, Builder artifact, and model sample as a matched causal comparison. |

Jobs `002`–`004` are launcher/runtime infrastructure-invalid identities before
meaningful task work. Job `007` is instead a project-caused harness-integrity invalid
attempt. Jobs `005`, `006`, and `008` are valid method observations even though all
received reward 0.0; job `009` is an official task pass but not a complete
Method-conformance pass. No prior score or attempt identity is overwritten.

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

Method v8 also makes the replay semantics explicit: Position is an evidence-bound
checkpoint, and Direction is the projection of the applicable Rule closure at that
Position. Each compiled acceptance item must carry all six required obligation
partitions before the task is declared ready. These are task-neutral constraints on
the Builder's representation, not a stored repair for this benchmark.

These general changes were nevertheless developed after observing job `008`'s hidden
verifier outcome. “No task-specific solution was embedded” is narrower than “no
feedback influence”: evaluator-feedback-informed hill climbing remains a live
alternative explanation for the same-task improvement.

These changes are generic scaffolding. Role labels are cooperative provenance, not an
operating-system permission boundary, and reminders are advisory rather than new
business-blocking Gates.

## Timing and construction diagnosis

Job `009` completed in 5,194 seconds wall time; agent phases consumed 5,107.230
seconds. Builder used about 1,350.758 seconds, Worker 2,912.605 seconds, and QA plus
runner finalization 843.867 seconds. The frozen Corridor contained 11 files and
119,516 bytes; its acceptance ledger and task adapter accounted for roughly 78% of
that representation.

Observed tool wall time was small compared with model time: 8.683 seconds for 42
Builder calls, 94.391 seconds for 218 Worker calls, and 29.101 seconds for 51 QA calls.
The long run was therefore not primarily command latency. Construction still spent
about 22 minutes and 31 seconds compiling requirements, but Worker reasoning and
execution was the largest phase at about 48 minutes and 33 seconds. Job `008` had
already shown a similar construction-volume problem: it completed in 4,684.975
seconds wall time, with Builder using 1,495.443 seconds.

That diagnosis supports a general optimization target: preserve exact acceptance
coverage while making the construction representation smaller and more selective. It
does not justify copying this task's hidden failing boundary into the generic method.

## Identity and audit boundary

- Dataset content hash:
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
- Method identity: `charting-loop-method-v8`, source commit
  `3c3813444a7d43d0a56837e9cb960be86ce26d06`. The execution code condition was HEAD
  `9e4aa1acda90ebbd366c3039166ac3c9c79596b3`, with SDK v0.4.0 and Agent v0.9.0.
- Frozen Corridor digest:
  `sha256:b8b8f2853ffc9cb30372af08dcd6ef1a652235243d822b9998f9bff2aa08ce7d`.
- Worker froze six complete snapshots. Snapshot 6,
  `worker-000006-458931fa489a7207`, was restored for grading with tree digest
  `sha256:458931fa489a7207663b311fdaf44a6a9ecc628b58b9ad798c6055bd3c6c4e7a`.
- Worker and QA both queried the same frozen Corridor runtime Guide. QA found no
  concrete defect, but its envelope combined incomplete definition closure with
  complete assessment closure. QA's effective outcome was `not_assessed`; no repair
  ran, and the sixth Worker snapshot was graded.
- The Corridor itself reported `definition_closure_status=incomplete` and
  `construction_readiness_status=unresolved`. The 19/19 score is therefore an official
  evaluator pass, not evidence that the complete frozen Method contract was satisfied.
- The original Modal container had already been destroyed when custody was collected.
  The Corridor was reconstructed from archived Builder write events, and the recovered
  bytes reproduced the frozen digest exactly. This is recovered byte-identical
  custody, not a direct container download.

Raw custody remains sealed because it contains a live benchmark problem, a
solution-bearing binary patch, detailed failure witnesses, role transcripts, and
authentication-bearing operational logs. Public auditability is provided here through
exact task/method identities, digests, timings, disposition history, and the official
score. Publication of the raw bytes would change the benchmark and leakage boundary;
redacting subscription and profile tokens alone would not make solution bytes safe.

The current immutable `public-v2` public-summary package is
[`public/results/ico-path-patch/job-009`](../public/results/ico-path-patch/job-009/).
Its manifest binds the private audit, runner result, Corridor custody manifest, role
transcripts, official reward receipt, final Worker snapshot, original binary, patch
generator, and patched binary by digest and size without publishing those bytes. It
also binds the minimized public-trial snapshot through the summary digest and exact
release commit/tree. The earlier `public-v1` package remains immutable and is
superseded, not rewritten.

## How to interpret this task beside `production-planning`

`production-planning` supplies three counted matched pairs on one task. Four Treatment
executions were observed at 20/20, but one belonged to an infrastructure-invalid pair
and remains noncounting. This page adds a second task and a passing same-task recovery,
showing that the dynamic Builder/Worker/QA pipeline can construct and consume a
Corridor under a different task shape. It still has no matched no-Corridor arm, and
job `009` changed multiple implementation and sampling variables relative to job
`008`. The combined public record therefore supports two-task engineering coverage,
not multi-task efficacy or a general causal claim.

For the matched evidence, read the
[`production-planning` task result](PRODUCTION-PLANNING-RESULT.md). For navigation,
[return to the experiment result index](EXPERIMENT-RESULTS.md).
