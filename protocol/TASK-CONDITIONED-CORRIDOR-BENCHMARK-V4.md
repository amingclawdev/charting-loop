# Terminal-Bench 3.0 frozen-capability Corridor protocol — v4

Status: prospective engineering/performance protocol. The exact method, agent, SDK,
prompt, task and total-clock identities are frozen before a scored run. A leaderboard
score is end-to-end performance, not a causal estimate or proof that the method caused
an improvement.

## Question

How does one method-instantiated agent perform when each fresh task receives a frozen,
task-neutral Graph Kernel and the Worker and independent QA both receive the exact
Method as diagnostic guidance? The Worker compiles the public authority into the
shared graph while doing the task; QA independently audits both that compilation and
the frozen output before any bounded repair.

The leaderboard profile is not a treatment/control experiment. A separately frozen
matched method/neutral profile may estimate an arm difference on the same task, but a
single task or post-feedback rerun is still descriptive rather than a general causal
result.

## Frozen identities

- Dataset: `terminal-bench/terminal-bench@3.0.0`.
- Dataset content hash:
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
- Population: 74 scored tasks in 7 domains; 4 tasks require GPU-capable execution.
- Agent: `benchmark_agents.harbor_agent:ChartingLoopGraphKernelMethodAgent`.
- Method: `charting-loop-method-v8` at
  `3c3813444a7d43d0a56837e9cb960be86ce26d06`.
- Method digest:
  `sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446`.
- Scope-datum digest:
  `sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af`.
- Agent: graph version `1.1.0`.
- SDK: `corridor_kit` version `0.7.0`, resolved by `KIT_VERSION` plus the canonical
  source-tree digest recorded before each trial starts.

A branch tip, `@latest`, mutable SDK directory, or post-task module update is not an
identity. Any byte change creates a new condition.

## Information and authority boundaries

| Role | Receives | May write | Cannot claim |
|---|---|---|---|
| Runner | frozen identities, one task deadline, task environment, role outputs | AuthoritySnapshot receipt, graph/submission custody, authorized RuleClosure receipts, run metadata | task correctness or Rule semantics |
| Worker | official task, live state, frozen Method/SDK, shared graph | official task state and immutable Rule/Fact/Position/Direction proposals | that graph structure proves acceptance or that a proposal is Rule authority |
| Independent QA | official task, post-Worker state, same Method/SDK/graph | QA assessment only | mutation, Rule-ratification, or grading authority |
| Harbor grader | returned official task state | official score | method causality |

Rule remains the normative authority layer. A work row is an execution projection; a
capability is mechanics; a timeline event is RAW observation; and a reminder is
advisory. None is a Rule, admitted Fact, Gate, Contract amendment, stored answer, or
permission to mutate.

## Frozen reusable capability boundary

The runner hashes and uploads the exact SDK read-only before the scored task starts.
The reusable layer may contain generic JSON/hash/manifest
mechanics, acceptance/work/capability validation, Position timeline projections,
shell-free capture, task-neutral domain operations, an append-only graph, the typed
Rule compiler, reverse semantic projection, and a deterministic read-only Doctor.

It must not contain a benchmark task ID, fixed task offset, opcode recipe, verifier or
oracle material, candidate answer, task fixture, prior-task Fact, or post-outcome
repair. Task-specific Rules and evidence are authored in the trial graph, never baked
into the reusable SDK. A module learned from this task's score, verifier output, or
transcript cannot be added to the frozen condition.

A same-task rerun after modifying the SDK is an engineering regression run. It is not
a fresh task sample, transfer result, or clean leaderboard attempt.

## Independent compile probe before a formal experiment

Compiler development may run one fresh diagnostic session before a formal scored
experiment. That session sees exactly the frozen Method, a runner-frozen
`AuthoritySnapshot`, and the task-neutral Typed Rule compiler interface. It must not receive a
solution, task tests, historical task Graph, official verifier output, prior result,
prior task transcript, hidden evaluator material, or task-specific hint. It emits
`charting-loop/typed-rule-ir/v4`; the deterministic compiler binds the
AuthoritySnapshot, source-clause inventory, Method, compiler/config and implementation,
candidate revision and input policy in one compile-probe manifest.

The AuthoritySnapshot has three separate planes: normative Rule sources, public
task-world Fact material, and supporting inputs. Exact byte custody (retrieval status,
media type, size, digest and runner freeze receipt) is distinct from semantic
extraction (status, extractor, source-byte binding, and the extraction artifact's
frozen UTF-8 bytes/size/digest). Every clause slice names `source_bytes` or
`extraction_artifact`. Readable bytes do not
prove that a PDF, archive or binary was semantically extracted. Source closure remains
unresolved while any normative source is unavailable, malformed, not byte-bound, not
successfully extracted, unmapped or semantically ambiguous.

The clause inventory enumerates every normative clause—including nested, trailing,
exception and optional clauses—with a stable clause-order key and ordered half-open
UTF-8 byte slices before mapping clauses to Rules. Array position is display-only.
Each RuleCandidate binds the exact source slices to semantic roles such as obligation,
domain, applicability, quantifier, condition, outcome, prohibition, witness and
relationship. It declares Rule kind, source-defined domain, applicability, condition
type, expected outcome, witness operators and typed Guidance. Guidance is advisory;
it cannot become Rule authority.

Every dependency declares endpoint semantics, scope, per-endpoint cardinality and one
explicit alignment: keyed join, aggregate-to-members, exact pairs, or source-backed
all-to-all. Missing alignment emits no v4 checklist edge; list order and an undeclared
Cartesian product create no dependency authority. Temporal and state-transition
conditions retain temporal/state witness operators, while static conditions do not
gain artificial time semantics.

The compiler then reverse-projects every candidate back to its exact source slices and
emits `SemanticDelta`: missing semantic roles, uncovered normative byte ranges,
clause-to-Rule mapping gaps, and relationship alignment/cardinality errors. A non-empty
delta cannot be called complete. Repair creates a new immutable `semantic_repair`
candidate bound to its parent and reproduced QA witness; it never overwrites the first
attempt. Independent QA re-reads the public authority rather than trusting the
candidate. The runner persists the exact snapshot root and a reproducible
`rule_candidate_report` containing the IR, compiler report and current Rule record
IDs. QA persists `rule_qa_assessment` against that existing report. QA does not
ratify a Rule. Only a runner/operator `rule_ratification` that revalidates the same
candidate, a complete zero-issue/zero-delta report, the AuthoritySnapshot, reverse
projection, and a passing QA record establishes an authorized `RuleClosure`.

The probe does not solve the task, choose Direction, establish task truth/PASS, block
the run, or become a hidden evaluator. Its output is reviewed but not injected into a
later fresh scored Worker. Historical `typed-rule-ir/v1` through `v3` remain readable
for custody; their missing v4 semantics stay legacy/unassessed and are never
backfilled. Known development tasks are same-task regression fixtures only.

## In-clock graph construction

There is no task-specific Builder phase in this profile. The Worker uses the frozen
task-neutral kernel while doing the task:

1. snapshot public authority and author immutable RuleCandidates;
2. run deterministic compile and reverse projection;
3. preserve an honest incomplete state or write a new semantic-repair revision;
4. freeze a complete scorable task output early;
5. let independent QA audit the same graph, source bytes and output; and
6. after an authorized RuleClosure receipt, create Position checkpoints and effective
   Direction proposals bound to the exact closure.

Graph incompleteness never stops task execution or external grading. The graph is an
inspectable navigation aid, not a pre-mutation Gate. The Worker and QA both receive the
frozen Method as procedural self-diagnosis guidance; the official task sources remain
task Rule authority.

## Position checkpoint, Direction, Guide, and reminders

The runner initializes a hash-linked append-only graph before Worker starts. Each
record binds its predecessor and exact content digest. After an authorized RuleClosure
exists, the Worker may append a whole-state PositionRef checkpoint over the current
RuleClosure digests, admitted Facts, checklist assessments, task/world identity,
scope, roles, artifact revisions and parent Position. Direction is projected from that
exact Position and closure. Entrance and Guide are derived from Direction; neither is
an additional authority plane. Worker and QA receive the same graph:

```text
PositionRef(RuleClosure digests, admitted Facts, checklist/frontier, world)
Direction(PositionRef, same RuleClosure digests) -> ready | blocked | unresolved
Guide(Direction) -> Entrance | typed refusal
```

The projection reports stale closure, missing checklist coverage, dependency-order
violations, invalidation gaps and a Direction bound to the wrong Position. It does not
rewrite history, synthesize evidence, or block execution. Missing graph evidence is
reported as incomplete and never suppresses Harbor grading.

A read-only counterfactual may substitute an explicitly identified hypothetical
Position and/or Rule closure input, hold the other inputs fixed, and project the
resulting Direction and Guide. It must be labeled hypothetical and cannot admit a
Fact, advance or replace the real Position, mutate acceptance, append a real timeline
transition, establish authority, certify PASS, or close a row. Counterfactual replay
is diagnostic evidence, not a Gate or mutation path.

## One task deadline and monotonic submission custody

The official task time limit is one end-to-end deadline. Worker, QA, repair,
and closure are logical handoffs inside that same clock, not separately budgeted
stages. A small finalization reserve may be held inside the total so the runner can
stop the active process, verify custody, restore the last complete Worker submission,
and return to Harbor. It is not extra task time.

Worker freezes the first complete, scorable official task state as soon as it exists
and freezes every later verified improvement as a new immutable version. QA freezes
its assessment separately. Worker and QA are cooperative protocol roles: the role
value is a namespace/provenance label, not a credential, ACL, account boundary, or
permission Gate. QA must write only its assessment and must not replace, invalidate,
or delete a Worker submission; this experiment does not claim hostile-role isolation.
When the remaining time is insufficient for another complete transition, the runner
stops the exact active role, verifies that `latest` exactly matches the selected Worker
manifest, prevalidates all restore targets and staging writes, then atomically replaces
each file. This is not a whole-set transaction; any commit-phase partial prefix is
reported as failure. The runner returns the restored state for official grading. If no
complete Worker snapshot exists, the run reports that fact and returns the live task
state without fabricating one.

Submission freezing is custody, not a Gate, correctness certificate, acceptance
decision, or authority grant. It never makes an incomplete state correct and never
permits work after the task deadline.

## Per-task sequence

1. The preflight doctor verifies clean committed source, exact dataset/method/agent identities,
   Modal and Codex readiness, sufficient operator-attested spend headroom, and the
   unused job identity.
2. The runner derives the one official task deadline, reserves only bounded
   finalization time inside it, hashes and uploads the frozen SDK and Method, verifies
   their remote identities, initializes the graph and submission store, and freezes
   the initial AuthoritySnapshot receipt.
3. The runner freezes `authority_snapshot` and its exact source artifacts. A fresh
   Worker reads the task, Method and kernel; compiles that AuthoritySnapshot to
   an immutable RuleCandidate, repairs any SemanticDelta without overwriting history,
   executes the task, and freezes its first complete scorable state plus each verified
   improvement.
4. A distinct QA session reads the same task, Method, graph and frozen Worker output;
   independently reconstructs the clauses, reverse projection and dependency
   alignment; and freezes its assessment separately from Worker state.
5. The runner replays and freezes `rule_candidate_report`; QA writes a content-bound
   assessment of that report. A runner/operator may ratify only the exact candidate
   revision whose complete zero-delta report, AuthoritySnapshot, reverse projection,
   and passing QA assessment all match,
   establishing RuleClosure. QA cannot self-ratify.
6. Worker records a Position and Direction only against that exact RuleClosure; the
   read-only Doctor recomputes graph integrity, dependency order, checklist/frontier
   alignment and Direction freshness before the next freeze.
7. QA `pass`, `blocked`, and `not_assessed` are advisory. A `fail` triggers bounded
   repair only when it contains a concrete acceptance-ID witness with
   constraint, observation, and safe replay.
8. If time remains, the same Worker may perform repair and freezes a new
   Worker version only after the repaired official state is complete; the same QA may
   then recheck the whole ledger, not only the prior witness.
9. Before returning unconditionally to Harbor, the runner verifies the exact latest
   binding, prevalidates the complete restore set, and restores the latest verified
   complete Worker snapshot by per-file atomic replacement after verifying its exact
   identity. This is the latest complete Worker snapshot; QA never substitutes one.
   QA follows its cooperative
   write boundary, never suppresses or replaces the Worker submission, and never
   short-circuits the benchmark grader.
10. Only after the agent returns, the runner freezes a pre-verifier manifest whose
    `submission` digest is the official verifier input, runs the verifier, and creates
    a digest-bound order receipt. Verifier alignment is generated only in an isolated
    post-hoc namespace; it is read-only, cannot enter Rule/Fact authority, cannot be
    supplied to a fresh task context, and never gates official grading.

Every Worker, QA, repair, and closure model call belongs to the scored agent
cost. Complete role trajectories and runtime identities are retained once in the
ATIF-v1.7 root.

## Experimental no-Gate rule

Do not ask Worker or QA to construct a mandatory approval, workflow, or pre-mutation Gate.
Doing so expands the intervention from task charting to construction and maintenance
of a governance system, and can stop U → C before the domain structure converges.

Validators, planners, bounded write APIs, typed refusals, work rows, and reminders may
remain explicit tools. They are not prerequisites for continuing and cannot become
grading Gates. Long-lived governed systems may add Gates only after establishing Rule
authority, admitted-Fact selectors, projection conformance, and whole-chain
satisfiability; blocked Gate repair follows the separately documented linear-unlock
rule and is not this benchmark procedure.

## Interpretation and contamination

Report aggregate score, every task outcome, Rule-compilation/closure status,
AuthoritySnapshot and SDK digests, total deadline, remaining time at each handoff,
submission/fallback status, QA outcome, repair count, cost, and infrastructure errors.
Do not hide null, negative, blocked, incomplete, or invalid cases.

The strongest accurate description is:

> End-to-end Terminal-Bench 3.0 performance of an agent whose Worker and independent
> QA shared one pre-task-frozen Method and task-neutral Graph Kernel, compiled the
> current public authority in-clock, and retained incomplete compilation honestly.

It does not show that Charting Loop outperforms a neutral prompt. That requires a
prospectively frozen matched method/neutral comparison over enough independent tasks.
