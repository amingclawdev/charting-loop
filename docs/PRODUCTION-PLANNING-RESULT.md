# Experiment result: `production-planning`

This human task page compares repeated attempts on **one distinct Terminal-Bench 3.0
benchmark task**. For other tasks, return to the [experiment result
index](EXPERIMENT-RESULTS.md).

## Task overview

**At a glance:** three matched pairs completed. In all three, the Treatment arm
(Corridor access) passed 20/20 official checks, while the Control arm (task only)
passed 16/20, 16/20, and 15/20. Two earlier attempts are preserved as invalid and
noncounting. This is a repeated descriptive pattern on one task, not multi-task or
causal evidence.

Jump to:

- [Attempts comparison](#attempts-comparison)
- [CL-030: repair launcher failed](#cl-030)
- [CL-031: verifier replay](#cl-031)
- [CL-032: matched repair attempt](#cl-032)
- [Immutable summary locators](#how-to-read-the-locators-safely)
- [Ask AI to summarize or audit](AI-RESULT-ANALYSIS-RUNBOOK.md)

### Plain-language experiment labels

- **Treatment arm (Corridor access):** the experimental group. Its Worker gets the
  official task and can use the frozen, builder-authored Corridor service.
- **Control arm (task only):** the comparison group. Its Worker gets the same official
  task without access to that Corridor service. "Control" does not mean no work or no
  QA.
- **Arm:** one side of a matched comparison. Each arm gets its own fresh Worker and a
  separate fresh independent-QA session under the same task, model/runtime, limits,
  repair opportunity, and official evaluator.
- **Corridor:** a task-specific navigation aid built and frozen before either arm
  runs. It can help a Worker find the work location, frozen objective and rules, and a
  bounded next move. It is not a stored answer, hidden evaluator, authority grant, or
  guarantee of correctness.

`Treatment` and `Control` are standard English experiment terms for the experimental
group and comparison group. The parenthetical labels state what they mean in this
study. Both arms use the same matched Worker + independent-QA process; the intended
difference is Corridor access. QA is common to both arms and is not the treatment.

### Evidence boundary

**Distinct benchmark tasks represented: 1.** The three completed pairs are same-task
repetitions, not three distinct benchmark tasks. The official evaluator scored the
Treatment arm `1.0` in each completed pair and the Control arm `0.0` in each completed
pair.

That repeated observation is descriptive process evidence, not a causal estimate.
The pairs reuse one task and frozen research inputs; they are not an independent
benchmark sample. Runtime effort was matched within each pair but was `low` for CL-030
and `high` for CL-031/032. QA outcomes, repair execution, and infrastructure conditions
also differed across attempts. These records do not establish benchmark-wide efficacy,
production readiness, semantic correctness, or real-world authority. They are **not
multi-task evidence**.

## Attempts comparison

"Counted" means included among the three completed same-task pairs. It does not mean
statistically independent or causally identified. Invalid attempts remain useful
process evidence but are not pooled into the three official pair outcomes.

| Record | Counts? | Official result | QA / repair | Verifier and short interpretation |
| --- | --- | --- | --- | --- |
| [CL-030 completed pair](#cl-030) | Yes: one descriptive same-task pair. | Treatment arm 20/20; Control arm 16/20. | Treatment QA `fail`; Control QA `pass`. Both repair launches failed before execution, so no effective Worker repair occurred. | Original official evaluation; no replay reported. Useful as a score observation, not as evidence of a functioning QA/rework intervention. |
| [CL-031 invalid predecessor](#cl-031) | No: protocol-invalid and noncounting. | Not a scored study result. | Rework was not conditioned on QA failure. | Preserved as process evidence; the public-safe summary does not support a more detailed failure account. |
| [CL-031 completed pair](#cl-031) | Yes: one descriptive same-task pair. | Treatment arm 20/20; Control arm 16/20. | Both QA sessions `pass`; zero Worker rework. | Complete with post-hoc verifier replay of unchanged pre-score images after only unused experiment networks were removed. |
| [CL-032 attempt-003](#cl-032) | No: infrastructure-invalid and noncounting. | No observed score from this attempt is a study result. | Control QA timed out before the matched pipeline completed. | No counted verifier result; it cannot support a matched repair conclusion. |
| [CL-032 attempt-004](#cl-032) | Yes: one descriptive same-task pair. | Treatment arm 20/20; Control arm 15/20. | Both QA sessions `fail`; each Worker received one bounded repair turn. No second QA followed repair. | Original official evaluation; repair execution does not prove that either QA finding was closed. |

In total: three counted completed pairs and two preserved invalid predecessor attempts,
all for one distinct benchmark task.

## Attempts and case explanations

### CL-030

**What happened:** the Treatment arm passed 20/20 official checks and the Control arm
passed 16/20. Independent QA called Treatment `fail` and Control `pass`. Both allowed
repair launches then failed symmetrically because the resume shell could not find the
launcher.

**How to read it:** the score difference is a completed descriptive result. The failed
launches mean this case did not test a functioning QA/rework intervention, and the QA
verdicts should not be substituted for the official evaluator result.

- Public Treatment package: [open immutable CL-030 Treatment v2](https://github.com/amingclawdev/charting-loop/blob/49e704f199022a58f43180798aabceae8954bfa5/public/results/cl030/treatment/SUMMARY.md).
- Public Control package: [open immutable CL-030 Control v2](https://github.com/amingclawdev/charting-loop/blob/a191c3787a89db159f3fcfacbce7d8293d304acd/public/results/cl030/control/SUMMARY.md).
- Each linked commit has a sibling `MANIFEST.json`; the registry records its
  branch name, commit, tree, manifest digest, identity, outcome, and sealed-source
  digests.
- Next: [go to CL-031](#cl-031), [ask AI to analyze
  CL-030](AI-RESULT-ANALYSIS-RUNBOOK.md#audit-cl-030), or [return to the task
  overview](#task-overview).

### CL-031

**What happened:** an earlier attempt was invalid because rework was not conditioned
on QA failure. In the completed pair, both QA sessions returned `pass`, so neither
Worker reworked its result. The initial verifier launch failed symmetrically after
Docker exhausted its network pools. After only unused experiment networks were
removed, unchanged pre-score images were evaluated sequentially: Treatment passed
20/20 and Control passed 16/20.

**How to read it:** this is a completed score result with post-hoc verifier replay,
not an unqualified direct verifier run. The invalid predecessor is preserved but does
not count as another pair.

- Public Treatment package: [open immutable CL-031 Treatment v2](https://github.com/amingclawdev/charting-loop/blob/64d1147c8b95dd8d9287535f75135aec7bc51b7f/public/results/cl031/treatment/SUMMARY.md).
- Public Control package: [open immutable CL-031 Control v2](https://github.com/amingclawdev/charting-loop/blob/be42757e1e47d93daa032cb2754d7a145210f6a3/public/results/cl031/control/SUMMARY.md).
- Each linked commit has a sibling `MANIFEST.json`. CL-031 records that scoring was a
  post-hoc replay of unchanged pre-score images after unused networks were removed.
  Its Treatment receipt also binds the contemporaneous events for reading the frozen
  service and tests, running its tests and dry-run, and applying the plan. This proves
  observed Corridor consumption for this attempt; it does not prove causality.
- Next: [go to CL-032](#cl-032), [ask AI to analyze
  CL-031](AI-RESULT-ANALYSIS-RUNBOOK.md#audit-cl-031), or [return to the task
  overview](#task-overview).

### CL-032

**What happened:** attempt-003 is infrastructure-invalid and noncounting because
Control QA timed out before the matched pipeline completed. Fresh attempt-004
completed. Both QA sessions returned `fail`; each Worker received one bounded
same-thread repair turn. Treatment made no persistent database change and passed
20/20; Control appended a corrected planning run and passed 15/20.

**How to read it:** only attempt-004 counts. Because the frozen design did not run QA
again after repair, a completed repair turn does not prove that a QA finding was
correct or closed.

- Public Treatment package: [open immutable CL-032 Treatment v2](https://github.com/amingclawdev/charting-loop/blob/d3f939995002fcf1bba913d56383f4493984a580/public/results/cl032/treatment/SUMMARY.md).
- Public Control package: [open immutable CL-032 Control v2](https://github.com/amingclawdev/charting-loop/blob/d45790a8449d686a8fbcdc8e847fd8bccca58e20/public/results/cl032/control/SUMMARY.md).
- Each linked commit has a sibling `MANIFEST.json`. The Treatment receipt binds the
  two failed constrained counterfactual computations, the unchanged writeback hashes,
  the pre-score image, and the 20/20 evaluator receipt. The Control receipt binds its
  accepted local repair, changed writebacks, pre-score image, and 15/20 evaluator
  receipt. These are observable mechanism records, not a general causal estimate.
- Next: [ask AI to summarize all attempts or analyze
  CL-032](AI-RESULT-ANALYSIS-RUNBOOK.md), [return to the task
  overview](#task-overview), or [return to the result index](EXPERIMENT-RESULTS.md).

## How to read the locators safely

Each link names an immutable public-safe result commit containing one arm's
`SUMMARY.md` and `MANIFEST.json` on top of the public-root history. Main contains all
six current packages for discovery. The append-only registry retains both the six v1
summary releases and the six superseding v2 evidence releases; it is the authority for
the branch-to-commit-to-tree join. Branch names alone are not proof of identity.

The v2 manifests publish the E1–E7 evidence status, safe observable event receipts,
output hashes, writeback digests, pre-score image identities, and official evaluator
receipts. They retain task and order identifiers; this is not anonymized narrative.
Solution source, raw writeback SQL, databases, full Worker/QA/repair logs, raw sessions,
trajectories, hidden evaluator material, subscription authentication, credential
values, host-private paths, and private reasoning remain absent from the public
history. Full source artifacts remain bound by SHA-256 digest, byte size, provenance,
custody, and controlled source reference.

Each v2 manifest also contains a post-hoc execution amendment. It records model,
reasoning effort, runtime, command/message counts, QA/repair ordering, service and
pre-score identities, plus observed CL-030 timing/usage. CL-031/032 timing, token
usage, seed, and runner retry count are explicitly `unavailable`; they are not
reconstructed from prose. The generated execution-amendment view is in
[`exogenous/registry/EXPERIMENTS.md`](../exogenous/registry/EXPERIMENTS.md).

For the proposed next study and its claim boundary, start with the human
[`REPLICATION-INVITATION.md`](REPLICATION-INVITATION.md). Operators must use the
authoritative
[`TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md`](../protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md)
rather than inferring a protocol from these outcomes.
