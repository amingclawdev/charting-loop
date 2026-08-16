# Task-conditioned Corridor benchmark v3

Status: executable leaderboard protocol. This protocol does not replace the frozen
v2 matched-pair study and does not retroactively change CL-030, CL-031, or CL-032.

## Purpose and claim boundary

The Charting Loop idea grew from using an agent to diagnose drift in long-running
Aming Claw work: the live state, governing objective, and legal next move can drift
apart. The method proposes compiling those task-specific relationships into a
Corridor that later agents can inspect and replay.

Version 3 asks a performance question: how well does the complete method-instantiated
agent perform on Terminal-Bench 3.0? Its next run uses the prospective v4 method and
agent v0.2.0. It includes construction, execution, and an independent
Corridor-visible QA/rework loop in one scored Harbor trial. This prospective change
does not relabel an earlier smoke run that used the v3 method and agent v0.1.0.

A leaderboard score is an end-to-end performance result. It is not, by itself,
evidence that the paper caused an improvement. Method attribution still needs a
matched task and a null/placebo Builder. CL-030/031/032 remain narrower Worker-only
Corridor-access observations because their QA sessions did not read the Corridor.

## Frozen benchmark identity

- Dataset: `terminal-bench/terminal-bench@3.0.0`
- Harbor package content hash:
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`
- Release size: 74 scored tasks across 7 domains.
- Resource boundary: 4 tasks require a GPU; use a GPU-capable Harbor environment
  such as Modal for a complete run.
- Agent: `benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent`

Do not replace `@3.0.0` with `@latest` in a reportable run. Terminal-Bench 3.0 is a
continuous benchmark; a mutable tag can change the task population.

## Roles and visibility

| Role | Sees | Must not see or do |
|---|---|---|
| Builder | frozen method, exact official task goal, public task environment | verifier/oracle internals; execute the final task; embed a stored answer |
| Worker | exact official task, live state, frozen Corridor and freeze digest | rewrite or replace the Corridor |
| independent QA | exact official task, post-Worker state, the same frozen Corridor and digest | mutate task state; repair; rewrite the Corridor |
| Harbor grader | task artifacts after the agent returns | depend on the QA verdict as an allow/deny gate |

The Builder must receive the task goal. A task-conditioned Corridor cannot be built
from the method alone: the task supplies the objective and public constraints that
the method tells the Builder to chart. The goal is not a hidden solution, and it is
the same task instruction later given to Worker and QA.

Both Worker and QA receive the same absolute Corridor path, freeze-manifest path,
and content digest. The harness verifies the digest before every downstream phase.
The Corridor tree and freeze manifest are root-owned and have no write bits. The QA
task-state non-mutation rule is a role contract; the current single-trial Harbor
adapter does not provide a read-only clone of mutable databases or services. That
limitation is acceptable for a leaderboard probe but must be removed or separately
measured before treating the run as a clean causal experiment.

The frozen Corridor contains `ACCEPTANCE.json`, a task acceptance ledger compiled
from the official instruction and all named public specifications. Each atomic item
has a stable ID, source reference, task scope, decision rule, and typed relations to
overlapping or dependent items. The freeze manifest records whether that ledger is
complete, incomplete, invalid, or missing and records the exact expected ID set.

Worker uses the ledger to check the entire task. QA uses the same ledger and Corridor
for diagnostics, but also independently re-reads the original public sources so all
three roles do not merely inherit the same omission. QA emits one result for every
expected ID and distinguishes definition, applicability, source coverage, and
observed assessment. Closing one repair witness never implies whole-task closure.

## Per-trial sequence

1. Start a fresh official task environment.
2. Upload the repository's current `method-paper/METHOD.md` as a read-only method.
3. Start a fresh Builder session with the method, exact task instruction, and public
   environment. It constructs a new Corridor inside this trial.
4. Close the Corridor byte set: reject symlinks/special files, record every relative
   path, size, and SHA-256, hash the manifest, and remove all write bits. If the
   Builder produced no safe files, freeze an explicit construction-failure Corridor
   rather than importing a prebuilt artifact or aborting the trial. Record the
   acceptance-ledger status and exact IDs without blocking the trial when the ledger
   is absent or incomplete.
5. Start a fresh Worker session. It reads the frozen Corridor, executes the official
   task, and verifies its own mutations.
6. Start a distinct QA session. It reads and may execute the same Corridor for
   diagnostic and counterfactual checks, independently re-reads the public task
   sources, and may write only its assessment.
7. Treat `pass`, `blocked`, and `not_assessed` as advisory terminal QA observations.
   A `fail` can trigger repair only when it contains a concrete constraint,
   observation, and safe replay witness tied to the expected Corridor digest.
8. On one valid witnessed fail tied to an acceptance ID, restore the original Worker
   session for exactly one repair pass, then restore the original QA session for
   exactly one whole-ledger closure check.
9. Return unconditionally to Harbor grading. QA never suppresses, replaces, or
   short-circuits the benchmark grader.

All Builder, Worker, QA, repair, and closure model usage belongs to the scored agent
cost. The root ATIF-v1.7 trajectory embeds one complete role trajectory per Builder,
Worker, and QA. A resumed Worker or QA trajectory contains its initial and continued
turns, so totals are aggregated once rather than double-counted by phase.

## No-gate rule for construction experiments

Do not ask the Builder to add a mandatory approval, pre-mutation, or workflow gate.
Such a gate changes the experiment from “does this aid help?” into “can the agent
construct, satisfy, and maintain a new governance system while solving the task?”
That greatly expands U→C work and can stop progress before the underlying structure
has converged.

A Corridor may expose a validator, planner, warning, diagnostic refusal, or bounded
write API. Those are explicit tools. They must not become a new prerequisite for the
Worker to continue, and QA must not become a grading gate.

An incomplete or invalid acceptance ledger is therefore evidence, not a runtime gate.
Worker still executes and Harbor still grades. The harness records internal QA as
`not_assessed` whenever a purported pass cannot prove complete acceptance.

Gates belong in a separate long-lived-system protocol after the structure is stable.
If an early U→C gate in such a system blocks because required evidence cannot yet
exist, preserve the block, bypass/waive that gate without claiming PASS, finish the
original path, and carry the same diagnostic root through each downstream dependent
gate. Later gates may also need bypass because the first bypass intentionally left
evidence gaps. This is a linear unlock used to reveal and repair gates one at a time;
it is not the benchmark procedure in this document.

## Prohibited shortcuts

- No task-specific Corridor may be built before the trial.
- No CL-030/031/032 production-planning service or answer may be reused.
- No oracle, verifier test, hidden reward, or task-specific online solution search.
- No omission of Builder/QA calls or their token and cost accounting.
- No conversion of an invalid or witness-free QA fail into repair authority.
- No internal QA pass with a missing, duplicate, unknown, unmapped, unresolved, or
  unassessed acceptance item.
- No use of any post-hoc downloaded task, verifier output, or role transcript as an
  input to a later Builder, Worker, or QA.
- No claim that three attempts on one task are three distinct task samples.

## Interpretation

Report the 74-task result as “full-method agent performance on Terminal-Bench 3.0
package 3.0.0.” Report task-level outcomes and construction failures, not only an
average. Use a later single-task matched comparison to estimate the Corridor
artifact effect, and a null/placebo Builder arm to distinguish the method from the
more general benefit of letting any agent build a tool first.
