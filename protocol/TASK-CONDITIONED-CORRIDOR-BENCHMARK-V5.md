# Terminal-Bench 3.0 parallel Rule/Witness Corridor protocol — v5

Status: prospective successor engineering/performance protocol. It changes the
task-neutral Kit and in-clock compiler architecture; it does not amend frozen Method
v8. A same-task rerun after this change is regression evidence, not fresh causal or
transfer evidence.

## Question and boundary

Can a method-guided agent compile public task authority fast enough for useful
execution when source interpretation is partitioned once, Rule semantics and
source-only witnesses are authored independently in parallel, and a deterministic
integrator plus whole-ledger QA establish RuleClosure?

The official task is the only task authority. The Method is diagnostic guidance; the
Kit is task-neutral mechanics; Harbor's verifier is run only after the agent returns.
No verifier output, hidden test, prior task transcript, candidate solution, or
task-specific hint may enter source partitioning, Rule compilation, witness
compilation, repair, Position, or Direction.

## Frozen identities

- Dataset: `terminal-bench/terminal-bench@3.0.0`, content hash
  `sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
- Agent: `benchmark_agents.harbor_agent:ChartingLoopGraphKernelMethodAgent`, graph
  version `1.3.0`.
- Method: unchanged `charting-loop-method-v8` at
  `3c3813444a7d43d0a56837e9cb960be86ce26d06`, digest
  `sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446`.
- Scope datum digest:
  `sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af`.
- SDK: `corridor_kit` version `0.8.0` plus the canonical source-tree digest recorded
  before the run.

Any byte change creates a new condition. V4 stays readable and immutable; v5 creates
new schemas and never backfills historical authority.

## Four-stage in-clock lifecycle

1. **Source partition.** A source-partition Worker freezes the plane-typed
   AuthoritySnapshot, complete ordered clause inventory, and a deterministic
   ownership manifest. Every clause has exactly one owner or remains unresolved.
   Boundary clauses are read-only context. Source-clause/lane dependency stubs and one
   global lane remain explicit; this stage never predicts future Rule or edge IDs.
2. **Parallel compile.** A Rule-lane Worker and an independent source-witness Worker
   receive the same frozen partition. The Rule worker emits source-bound Rules,
   checklists, typed predicates and dependencies. The witness worker sees public
   source and partition only—never candidate Rules, checklists, or other candidate
   witnesses—and emits positive, negative and boundary witnesses.
3. **Whole-ledger QA and RuleClosure.** The runner joins both digest-bound products
   deterministically, rejects coverage holes, duplicate ownership, dangling or
   incompatible types, missing cross-lane dependencies, temporal collapse,
   source-witness mismatch and incomplete integration, and freezes one v5 candidate.
   Independent QA reconstructs the whole ledger from public source. Only a passing
   same-candidate assessment permits runner/operator ratification.
4. **Execution and frozen-result QA.** After RuleClosure, the same Rule Worker projects
   Position, Direction and pre-action tests, implements, freezes complete scorable
   revisions, and receives independent QA. The latest valid Worker freeze remains the
   deadline fallback.

All four stages share one official task deadline. There are no phase budgets and no
pre-mutation Gate. Incomplete graph state remains visible but never prevents task
work, snapshot custody, fallback, or external grading.

## Source partition and parallel products

The source partition product binds the AuthoritySnapshot, complete clause inventory,
Method/config digests, revision and `source-partition-manifest/v1`. Ownership is
one-to-one. Boundary visibility does not authorize another lane to reinterpret the
clause. The global lane owns coupled, temporal-global and integration constraints.

Each Rule lane and witness lane binds the canonical source-partition-product digest.
The witness package records role/session/input-envelope identity and explicitly states
that Rule, checklist and candidate-witness visibility were false. This is a
cooperative protocol invariant, not an ACL or credential Gate.

V5 typed predicates retain stable operators; typed inputs and outputs; producer,
precondition and dependency references; and task-neutral semantic fields. Temporal
and state predicates name distinct event/transition time variables and distinct
before/after/chain outcomes. Closed conditional domains require positive and negative
source classification for each declared subject. Every lane retains positive,
negative and boundary witnesses.

## Deterministic integration and repair

The integrator binds normalized predicate, operator-schema, source-witness,
source-witness-binding, hard-dependency-closure, lane-package, cross-lane-edge,
compiler-implementation and Method digests. `RuleClosure` additionally binds the
passing QA assessment and frozen candidate identities. A digest establishes identity,
not semantic truth.

QA findings are machine-addressable: lane, Rule, source, witness, error type, complete
impact Rules and minimal rerun lanes. Witness repair receives only a frozen source-safe
projection of affected lanes and public source refs; it never reads QA prose or Rule
semantics. A repair impact includes changed Rules, all hard
dependants, invalidated nodes, incident cross-lane edges and both endpoints,
conflict/overlap components, temporal/global owners, and the integrator package.
Repairs may run in parallel only when these complete impact sets are disjoint. After
any differential repair, independent QA rechecks the whole ledger; prior PASS areas
may be reused as identity-bound evidence but do not exempt the new whole-ledger
assessment.

## Task-neutral regression mutations

Before a scored run, local tests must reject or classify incomplete at least:

- an erased temporal input variable;
- collapsed before/after outcomes;
- a falsely closed applicability domain contradicted by source witnesses;
- a dropped cross-lane dependency declaration; and
- a witness envelope that can see candidate Rule semantics.

These are generic schema mutations, not benchmark task fixtures. Official verifier
comparison remains a post-hoc alignment record and cannot ratchet hidden evaluator
semantics into the compiler.

## Claims

A v5 run may report official reward, wall time, partition time, Rule and witness lane
times, parallel critical path, assembly time, QA/repair time, compiler/closure
identities, and post-hoc verifier alignment. It may not claim method causality from a
leaderboard run, generality from one task, or fresh transfer from a task already used
for verifier-informed repair.
