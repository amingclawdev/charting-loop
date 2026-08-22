# Method-guided in-clock Graph Kernel experiment protocol

Protocol ID: `method-guided-graph-kernel-experiment-v1.2`

Status: prospective, unlaunched protocol. It supersedes the unlaunched v1.1 execution
schedule for new jobs; it does not rewrite v1.1, Method v8, Theory v1, or any prior
result. The implementation condition is Graph Agent v1.1.0 plus the exact committed
Corridor Kit tree pinned by each Study profile.

## Why this revision exists

A mature task-conditioned Corridor is normally produced by a long engineering loop:
build mechanisms, expose blocks, repair them, replay the path, and repeat until the
system stabilizes. A short benchmark Builder phase cannot reasonably compress that
process. It mainly measures construction speed and consumes the task clock before the
agent can solve the task.

This Study instead tests the **diagnostic application profile**. Both arms receive a
small byte-identical, task-neutral Graph Kernel. The task-time Worker uses it while
solving: it records source-bound Rules, admitted Facts, whole-state Position
checkpoints, and Position-bound Direction proposals. No task-specific Corridor or
answer is prepared before the task clock.

The other two profiles remain distinct. Long-horizon Corridor engineering is an
iterative system-building intervention, while frozen Corridor traversal gives a later
agent a previously built task-conditioned aid. Evidence from either profile is not
silently reclassified as evidence for this Study.

## Frozen identities and matched arms

Treatment receives the official task, the frozen `charting-loop-method-v8` bytes, and
Kernel K. Neutral Control receives the same task and byte-identical K, with the frozen
neutral instruction replacing Method guidance. Worker and QA in each arm receive that
arm's same condition. The only intended arm difference is Method guidance.

Each launch pins task/evaluator bytes, model, effort, runtime, Graph Agent v1.1.0,
Kernel tree digest, prompt templates, one total task deadline, retry policy, private
upload policy, and all invalid-run dispositions. Method v8 remains the exact cataloged
package at source commit `3c3813444a7d43d0a56837e9cb960be86ce26d06`, Method digest
`sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446`,
and Scope Datum digest
`sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af`.
This protocol revision changes the Study schedule, not the Method.

## Kernel authority boundary

K provides append-only records, hash identities, replay, immutable graph revisions,
and monotonic Worker submission custody. It has no task Rules, verifier knowledge,
answer, truth inference, planner, completion authority, or blocking Gate.

- A Rule proposal enters a Position only after a receipt binds its current revision to
  an authorized public source. Revising the Rule invalidates the old ratification.
- A Fact proposal binds evidence and a known Position. Admission requires a current
  ratified admission Rule and an explicit receipt.
- A Position is a whole-state checkpoint over the current ratified Rule closure,
  admitted Fact receipts, task/world identity, scope, roles, and artifact revisions.
- A Direction is proposed by the Worker against one exact Position. K checks identity
  and reference closure; it never chooses the semantic Direction.
- Reused Position or Direction IDs, unknown references, conflicting identities, and
  structurally invalid appends fail closed and leave the graph bytes unchanged.

Graph validity means only structural validity. It cannot establish correctness,
deliverability, PASS, authority to mutate the task, or convergence.

For the CL-110 task-neutral projection, each ratified Rule may be compiled into
source-bound acceptance checklist items that preserve its exact scope, quantifier,
behavioral partitions, evidence requirement, and three-way decision rule. Typed
normative, work-row, and evidence dependencies distinguish hard order, conflict,
invalidation, and explicitly non-ordering relations. Position remains one whole-state
identity, with `row_progress` and `acceptance_assessment` projections; every effective
Direction binds that exact Position's checklist and ready/blocked/unresolved frontier.
These operational records do not replace Rule authority.

Immediately before pairing a Worker snapshot with a graph revision, the harness runs
the read-only graph Doctor over the live bytes, copies them, and runs the same Doctor
again at QA intake. The paired manifest binds graph/byte digest, Doctor schema/code/
report digest, PositionRef, Direction digest, and acceptance root. Byte mismatch or a
`structurally_invalid` graph makes that graph revision non-auditable evidence, but it
does not erase a verified Worker snapshot, prevent deadline fallback, or prevent the
official verifier. `structurally_valid_but_incomplete` remains auditable honest
evidence. `acceptance_assessed_complete` is still not official PASS.

## One-clock execution sequence

There is one official task clock and no fixed Builder, Worker, QA, or repair allocation.
The harness uses this sequence entirely **before** the official verifier:

1. The Worker solves the task with its frozen arm condition and K. It creates a
   complete scorable output early and freezes Worker revision 1.
2. The harness freezes the exact graph revision paired with that Worker snapshot.
3. The harness binds matching pre-freeze and QA-intake Doctor reports to the immutable
   graph/Worker pair; arm-native QA re-runs the Doctor and audits the pair under the
   same remaining task clock.
4. QA may recommend repair only with an identity-bound, replayable witness naming the
   observation, expected condition, evidence, replay procedure, Position, and exact
   Worker snapshot. QA is advisory; it neither mutates output nor acts as a Gate.
5. If such a witness exists and time remains, the harness resumes the **same Worker
   session**. The Worker reproduces the witness, rejects unsupported advice, repairs
   when justified, verifies the full task, and freezes a newer complete revision.
6. The same QA session audits that newer Worker/graph pair. Steps 4–6 repeat while a
   newer freeze exists, a witnessed repair is requested, and the one task clock remains.
7. At deadline or a non-repair decision, the harness restores the latest valid Worker
   freeze and returns. Only then does Harbor run the official verifier.

Invalid, missing, contradictory, unwitnessed, or `not_assessed` QA report cannot
erase a valid Worker freeze, authorize repair, block return, create PASS, or prevent
official grading. If a repair fails or does not produce a newer valid freeze, custody
continues to point to the previous valid revision.

## Replay, convergence observations, and QA scope

QA audits the full Rule→Fact→Position→Direction→artifact path, not every individual
Direction as a blocking transition. Worker self-diagnosis occurs continuously; the
independent QA boundary occurs after each complete frozen Worker revision, where there
is a stable object to replay and a repair can still affect the task.

The Study may report repeated Direction digests, unchanged artifact digests, repeated
failure signatures, unresolved Rule conflicts, and Positions without newly admitted
evidence. These are revision-scoped convergence observations. They reset when the
relevant Rule, Position, world, or artifact revision changes. No threshold proves a
contraction theorem, forces termination, grants PASS, or becomes a new Gate.

## Prospective probes and reporting boundary

The first v1.2 regression uses two previously observed tasks, each with Method and
Neutral arms: `bun-sourcemap-leak` probes Rule authoring/Fact admission, and
`music-harmony` probes Position-to-Direction reprojection. They are adaptive same-task
engineering probes, not fresh transfer tasks, independent replications, leaderboard
submissions, or multi-task causal proof.

Retain every Worker and QA trajectory, every Worker freeze, every paired frozen graph,
all audit reports, invalid append attempts, timing/usage, final restore identity,
official verifier output, and private Harbor custody. Report the complete revision and
audit sequence, not only the final score. A score difference remains conditional on K;
a single pair or adaptive rerun does not establish general Method efficacy.

The CL-109 launch attempts are not official Study results: all four original jobs are
invalid because the harness raised a retained finalization exception. Their post-hoc
diagnostic verifier output is mechanism evidence only. The two observed shapes were
a universal acceptance boundary narrowed to one observed partition, and Direction
projected before sufficient source Facts with a local check mistaken for whole-task
acceptance. The generic checklist, dependency, Position binding, and Doctor behaviors
above address those shapes without embedding task names, task solutions, or verifier
answers in the Kit.

## Launch rule

No paid job may start until the v1.2 prompts, graph replay boundaries, one-clock loop,
doctor identity, runbook commands, focused/full tests, and independent QA all pass at
one clean committed HEAD. Any semantic change creates a new protocol/agent identity;
it does not silently modify this revision or ratchet a failed run into evidence.
