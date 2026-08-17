# Terminal-Bench 3.0 frozen-capability Corridor protocol — v4

Status: prospective engineering/performance protocol. The exact method identity and
SDK tree identity are resolved from the frozen catalog and run metadata before any
paid Builder call. A leaderboard score is end-to-end performance, not a causal
estimate or proof that the method caused an improvement.

## Question

How does one method-instantiated agent perform when each fresh task receives:

1. a Builder that sees the exact official task and a frozen task-neutral Corridor SDK;
2. a newly compiled, frozen task-specific Corridor;
3. a Worker that reads its acceptance ledger, work rows, selected capabilities, and
   runner timeline; and
4. an independent QA session that reads the same frozen Corridor and runtime view,
   while independently re-reading the public task sources?

This is not a treatment/control experiment. A later matched task-level comparison is
needed to estimate a Corridor artifact effect, and a null/placebo Builder is needed to
distinguish method attribution from the general benefit of building a tool first.

## Frozen identities

- Dataset: `terminal-bench/terminal-bench@3.0.0`.
- Dataset content hash:
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
- Population: 74 scored tasks in 7 domains; 4 tasks require GPU-capable execution.
- Agent: `benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent`.
- Method: `charting-loop-method-v5` at
  `8b0fd5e1c6102c6b4c44cf03612b93c450ddb6fd`.
- Method digest:
  `sha256:1b8d375f835e1226682febeb2479ea018b4d27725f376128a31430d39a46975a`.
- Scope-datum digest:
  `sha256:6a9cfc8eb65d90a5deca463113e238b96c6b28af09c63b3b7ea537c2af2949f0`.
- SDK: `corridor_kit`, resolved by `KIT_VERSION` plus the canonical source-tree digest
  recorded in each trial before Builder starts.

A branch tip, `@latest`, mutable SDK directory, or post-task module update is not an
identity. Any byte change creates a new condition.

## Information and authority boundaries

| Role | Receives | May write | Cannot claim |
|---|---|---|---|
| Runner | frozen identities, task environment, role outputs | freeze manifest, Position timeline, run metadata | task correctness |
| Builder | method, official goal and public task world, frozen SDK | Builder scratch and task Corridor before freeze | final task execution or evaluator PASS |
| Worker | official task, live state, frozen Corridor, frozen SDK, runner timeline | official task state | that row/reminder status proves acceptance |
| Independent QA | official task, post-Worker state, same Corridor/SDK/timeline | QA assessment only | mutation authority or grading authority |
| Harbor grader | returned official task state | official score | method causality |

Rule remains the normative authority layer. A work row is an execution projection; a
capability is mechanics; a timeline event is RAW observation; and a reminder is
advisory. None is a Rule, admitted Fact, Gate, Contract amendment, stored answer, or
permission to mutate.

## Frozen reusable capability boundary

The runner hashes and uploads the exact SDK read-only before the scored task is
exposed to Builder. The reusable layer may contain generic JSON/hash/manifest
mechanics, acceptance/work/capability validation, Position timeline projections,
shell-free capture, and task-neutral domain operations. The initial binary pack is
limited to read-only ELF inventory, changed-byte range comparison, and shell-free
replay binding.

It must not contain a benchmark task ID, fixed task offset, opcode recipe, verifier or
oracle material, candidate answer, task fixture, prior-task Fact, or post-outcome
repair. The Builder selects applicable capabilities by stable ID/version/digest and
builds task-specific adapters inside the current Corridor. A module learned from this
task's score, verifier output, or transcript cannot be added to the frozen condition.

A same-task rerun after modifying the SDK is an engineering regression run. It is not
a fresh task sample, transfer result, or clean leaderboard attempt.

## Builder outputs and freeze

The Builder must first establish the complete public task acceptance surface, then
compile executable decomposition:

- `ACCEPTANCE.json` maps every public normative clause to a stable acceptance ID,
  source, scope, Rule, definition state, and typed relations;
- `WORK_ITEMS.json` binds every acceptance ID to bounded, acyclic rows with scope,
  dependencies, done-when conditions, selected capability IDs, and reminders; and
- `CAPABILITIES.json` declares only selected operations with exact version, digest,
  entrypoint, input/output contracts, applicability signals, and side effects.

All three files are strictly validated. Incomplete, invalid, or missing surfaces are
recorded as construction evidence but do not stop Worker or the official grader. The
runner closes the complete task Corridor byte set, rejects symlinks and special files,
records relative paths/sizes/digests/executable modes, computes one tree digest, makes
the tree root-owned and read-only, and verifies it before every downstream phase.

## Position timeline, current row, and reminders

The runner initializes a hash-linked append-only Position timeline outside the frozen
Corridor before Builder. Each event binds its predecessor and exact content digest.
After Corridor freeze, the runtime deterministically projects row states and one
current row from frozen work definitions plus the visible timeline prefix. Worker and
QA receive the same timeline path and can query the same Guide:

```text
Guide(frozen work rows, frozen capabilities, Position prefix)
  -> current row + bounded capability descriptors + reminders
```

The projection reports inconsistencies such as multiple active rows or unknown row
references. It does not rewrite history, synthesize missing done-when evidence, or
block execution. Reminder delivery and use are observable process facts, not Gates.
Missing timeline evidence is reported as evidence loss and never suppresses Harbor
grading.

## Per-task sequence

1. The doctor verifies clean committed source, exact dataset/method/agent identities,
   Modal and Codex readiness, sufficient operator-attested spend headroom, and the
   unused job identity.
2. The runner hashes and uploads the frozen SDK, verifies the remote tree digest, and
   initializes the Position timeline.
3. A fresh Builder receives method, task goal, public environment, and SDK. It builds
   only the current task Corridor and does not execute the final task.
4. The runner freezes the Corridor, records acceptance/work/capability status, and
   projects the initial current row and reminders.
5. A fresh Worker reads the Corridor and runtime Guide, executes the official task,
   and independently verifies all mutations against the acceptance ledger.
6. A distinct QA session reads and may execute the same frozen Corridor and
   capabilities, reads the same timeline/Guide, independently re-reads public sources,
   and writes one result for every expected acceptance ID.
7. QA `pass`, `blocked`, and `not_assessed` are advisory. A `fail` triggers the one
   frozen repair allowance only when it contains a concrete acceptance-ID witness with
   constraint, observation, and safe replay.
8. The same Worker may perform one bounded repair; the same QA then rechecks the whole
   ledger, not only the prior witness.
9. The agent returns unconditionally to Harbor. QA never suppresses, replaces, or
   short-circuits the benchmark grader.

Every Builder, Worker, QA, repair, and closure model call belongs to the scored agent
cost. Complete role trajectories and runtime identities are retained once in the
ATIF-v1.7 root.

## Experimental no-Gate rule

Do not ask Builder to construct a mandatory approval, workflow, or pre-mutation Gate.
Doing so expands the intervention from task charting to construction and maintenance
of a governance system, and can stop U → C before the domain structure converges.

Validators, planners, bounded write APIs, typed refusals, work rows, and reminders may
remain explicit tools. They are not prerequisites for continuing and cannot become
grading Gates. Long-lived governed systems may add Gates only after establishing Rule
authority, admitted-Fact selectors, projection conformance, and whole-chain
satisfiability; blocked Gate repair follows the separately documented linear-unlock
rule and is not this benchmark procedure.

## Interpretation and contamination

Report aggregate score, every task outcome, Builder construction status, work/capability
validation status, Worker/QA timeout, QA outcome, repair count, SDK digest, cost, and
infrastructure errors. Do not hide null, negative, blocked, or invalid cases.

The strongest accurate description is:

> End-to-end Terminal-Bench 3.0 performance of an agent that used a pre-task-frozen
> reusable SDK to build one fresh task-conditioned Corridor whose Worker and
> independent QA shared the same frozen work rows, capabilities, and advisory runtime
> timeline.

It does not show that Charting Loop outperforms any other Builder method. For that,
run a prospective matched no-Corridor task comparison and then a null/placebo Builder.
