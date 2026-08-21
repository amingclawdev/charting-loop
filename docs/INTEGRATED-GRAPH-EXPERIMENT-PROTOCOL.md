# Method-guided Position/Direction Graph Kernel experiment protocol

Protocol ID: `method-guided-graph-kernel-experiment-v1`

Status: prospective protocol. It defines a study that has not yet been run. It does
not amend the frozen Method, reclassify an earlier result, or claim that the design is
effective.

## Why this protocol exists

Building a mature Corridor is normally a long-horizon engineering loop: mechanisms
are introduced, blocking conditions are discovered, the implementation is repaired,
and the system is replayed until the path stabilizes. Compressing that whole process
into a short benchmark task mainly measures whether a task-specific Builder can finish
in time. That is not the question this study is meant to ask.

This protocol therefore supplies both arms with the same frozen, task-neutral graph
infrastructure. The task-time agent performs the semantic work itself. The experiment
asks whether Method guidance changes that work when infrastructure is held fixed.

## Three frozen identity layers

### Method profile

The Treatment input is the normative `charting-loop-method-v8` package:

- source commit: `3c3813444a7d43d0a56837e9cb960be86ce26d06`;
- Method digest:
  `sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446`;
- Scope Datum digest:
  `sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af`.

The readable source is [`method-paper/METHOD.md`](../method-paper/METHOD.md), but a
study must bind the exact catalog identity and bytes. The published Theory remains a
separate source: commit `cf5ac479e208a2401b9358527d58df48e22c0670`, blob
`083ca2c18dbbb44804208d081b70e7a161df1187`, and SHA-256
`f557af476441e814e4d86041969c18fde2299a6a47d28658bdeb8cec2d7296c1`.
The Theory motivates the diagnosis; Method v8 supplies the operational guidance.

### Protocol profile

The protocol freezes the arm construction, task clock, graph semantics, custody,
submission rule, QA schedule, telemetry, and claim boundary described below. Protocol
changes create a new protocol revision; they never silently alter Method v8.

### Study profile

A Study profile pins the prospective task set, task and evaluator digests, model and
runtime, reasoning effort, tools, network policy, total task clock, Kernel bytes,
prompts, QA rubric, seeds when available, and all retry and invalid-run rules. It also
declares the exact Treatment and Control context manifests before either arm starts.

## Three work profiles

The identity layers above must not be confused with three different ways of applying
Charting Loop:

- **Diagnostic application profile.** A task-time agent uses the Method to diagnose
  drift between the current Position, governing Rules, projected Direction, and the
  next attempted transition. This is the primary profile tested here.
- **Long-horizon Corridor engineering profile.** An engineering process repeatedly
  builds mechanisms, encounters blocks, repairs the system, and replays it until a
  durable Corridor stabilizes. This process can take many iterations and is not
  compressed into a benchmark Builder stage or counted as a task arm in this Study.
- **Frozen Corridor traversal profile.** A later agent consumes a previously built and
  frozen task-conditioned Corridor. Existing matched observations used this profile;
  it remains valid, but it estimates a different intervention from the primary Study.

A report names the profile it actually ran. Evidence from one profile is not silently
reclassified as evidence for another.

## Estimand and matched arms

The estimand is the incremental effect of Method guidance **conditional on the shared
Kernel**, not the total effect of every possible Charting Loop implementation.

- **Treatment:** the frozen task, frozen Method profile, and frozen Kernel K.
- **Control:** the same frozen task and byte-identical Kernel K, with a neutral
  task-execution instruction in place of Method guidance.

The only intended arm difference is Method guidance. Kernel documentation,
affordances, tools, context placement, task bytes, model/runtime, task clock,
submission rule, and scoring are otherwise matched. Both conditions retain the same
graph-writing ability; Control is not an infrastructure ablation.

## What Kernel K contains

K is a frozen task-neutral Position/Direction Graph Kernel. It provides only:

- append-only graph records and deterministic node/edge identities;
- immutable snapshots, content digests, replay, and crash recovery;
- Worker artifact custody and the final QA handoff;
- structural schema and referential-integrity checks; and
- protocol telemetry that is explicitly non-authoritative.

K does **not** include task Rules, task acceptance criteria, verifier knowledge,
answers, solution logic, a planner, a domain adapter that interprets task meaning,
truth inference, completion authority, or a blocking completeness Gate. Mechanical
task I/O and custody binding may exist outside K when the benchmark harness requires
them, but those bytes and affordances must be identical across arms and must not add
solving semantics.

There is no task-specific Builder phase. Any runner-owned setup before the official
clock is limited to frozen Kernel and harness materialization. Extracting task Rules,
interpreting evidence, planning checkpoints, and proposing Direction are task-time
Worker behavior and therefore part of what is measured.

## Graph semantics

### Rule and Fact authority

The Study freezes a `RuleAdmissionPolicy` and `FactAdmissionPolicy` before either arm
starts. The Worker may append a proposed Rule node only with an exact source binding
into the frozen public task or another Study-authorized Rule source. A proposal becomes
an authorized `RuleRevision` only through the policy's source-authorized ratification
transition, which emits a content-addressed `RuleRatificationReceipt`. K verifies the
source and transition identity; neither the Worker, graph membership, nor K creates
new normative authority. A dependency edge states that one Rule's applicability or
satisfaction depends on another; it does not make either Rule true.

A proposed Fact binds an observation to evidence and the Position at which it was
observed. It enters the admitted-Fact root only through the frozen FactAdmissionPolicy,
whose source selector and replay result are bound in a `FactAdmissionReceipt`. The
receipt authorizes inclusion under that policy; it does not promote an observation
beyond the cited evidence. Fact admission does not authorize a Rule. Rule authorization
does not admit a Fact. K must preserve that distinction and may not infer either
authority from a well-formed record or a QA opinion.

### Position and Direction

`PositionCheckpoint` is a content-addressed whole-state checkpoint. It binds the task
and world identities; governed-object revision; role definitions, assignments, and
scope; current artifact root; authorized RuleRevision and applicable Rule closure;
admitted-Fact root and admission-receipt watermark; unresolved conflicts; and the
relevant task-timeline root. It is not a per-Rule checkpoint or merely a progress label.

At a Position, the Worker writes a semantic `DirectionProposal` grounded in the
applicable Rules and cited timeline evidence. Direction is intentionally not fixed:
new admitted Facts or a new Position may require reprojection.

K may then freeze a `DirectionSnapshot` that binds the proposal, exact Position,
applicable Rule closure, evidence references, and producer identity. That snapshot is
a candidate, not truth, a PASS, an instruction from K, or authorization to mutate the
task. K checks structure and identity only. Treatment asks the Worker to use Method v8
to diagnose the Position/Direction relationship; Control receives a neutral
task-execution instruction and the same graph operations.

## Task-time execution and fail-soft behavior

Each arm receives one official task clock. There is no fixed Builder/Worker/QA budget
inside that clock because there is no task-specific Builder and primary QA is
post-score. During task execution the Worker may create Rule and Fact nodes, checkpoint
Position, propose and reproject Direction, and freeze complete artifact revisions.

On every append K performs structural validation only: schema, digest, identity,
referential integrity, and append-only history. A structurally invalid mutation fails
closed and is zero-write; its advisory error does not terminate ordinary task work, and
the last valid graph remains available. A structurally valid but incomplete or
contradictory graph is preserved as evidence and reported to the Worker as an advisory
limitation. It does not block ordinary task work, synthesize missing evidence, or
convert uncertainty into a Gate decision.

Throughout the task, complete Worker artifact revisions are frozen into continuous
latest-valid custody. The latest-valid pointer advances atomically only after a
revision's bytes and manifest validate; an incomplete or invalid revision cannot
replace the previous valid snapshot. At the official deadline the harness submits the
latest valid frozen Worker snapshot that existed before the deadline. A later audit
cannot replace it. If no such snapshot exists, the Study records the predeclared
no-submission or invalid outcome rather than constructing one after the fact.

## QA schedule

Per-Direction review during the task is Worker self-diagnosis, not an independent QA
Gate. Treatment's Worker performs that diagnosis with Method guidance; Control's
Worker uses its neutral instruction. K records both without deciding which semantic
Direction is correct.

After the Worker snapshot is frozen and official scoring has completed, one fresh QA
session performs a full-path audit under a separate audit-only budget. QA reads the
original task, the scored Worker snapshot, and the complete Rule/Fact/Position/
Direction path. It reports supported, unsupported, contradictory, or not-assessed
findings with witnesses. It does not repair the submission, change the official score,
or create a Gate for the already completed task.

The arm-native QA observation follows its arm's context: Method-guided in Treatment
and neutral in Control. Those outcomes are mechanism evidence, not an isolated QA
effect estimate. Any cross-arm claim specifically about QA quality requires a separate
preferably blinded re-audit using a byte-identical QA Method and byte-identical audit
rubric on both frozen paths; otherwise the QA comparison remains descriptive only.

## Replay and observables

Replay reconstructs graph state from frozen bytes and verifies identity joins. It does
not replay hidden reasoning or assert semantic correctness. Reprojection is measured
by the sequence of Position-bound DirectionSnapshot identities, not by asking K to
choose a Direction.

Protocol telemetry may record revision-scoped convergence observables such as repeated
Direction digests, unchanged artifact digests, repeated failure signatures, unresolved
Rule conflicts, or Positions with no newly admitted evidence. These observables reset
when the relevant Rule revision, task revision, or artifact revision changes. They are
diagnostic and non-gating: no threshold grants PASS, proves contraction, forces
termination, or blocks the Worker.

## Evidence and reporting

Retain every valid, failed, timeout, blocked, infrastructure-invalid, and unscored arm.
For each arm publish or seal, as policy permits:

1. the Study profile and exact input manifests;
2. Kernel commit/tree/digest and proof that both arms used byte-identical K;
3. Method identity for Treatment and neutral-instruction digest for Control;
4. task-time graph events, Worker snapshot custody, timing, usage, and official score;
5. the post-score QA report and its separate budget; and
6. contamination, retry, network, redaction, and missing-evidence dispositions.

Report the arm difference, dispersion across repeated fixed-config runs, and the
smallest evidence-supported mechanism account. A score difference alone does not prove
that Method caused it. A single task does not establish multi-task efficacy. A
non-blinded arm-native QA comparison does not establish a QA effect.

## Implementation boundary

This protocol does not require a Method v9. An optional future Method profile may
formalize the integrated executor-authoring pattern, but the primary Study remains a
Protocol profile using frozen Method v8.

An optional future repair-loop Study may let witnessed post-score QA findings drive a
new Worker revision. It must be preregistered as a different Study with a new task
clock, submission rule, and estimand; it cannot rewrite the primary non-repair result.

Kernel K may be implemented as Corridor Kit 0.6 by a clean rewrite. Compatibility with
earlier Kit versions is not a requirement when migration would reintroduce a
task-specific Builder, task adapters, blocking Gates, or hidden authority. Historical
Kit bytes and results remain immutable evidence; a rewrite receives a new identity and
must pass the same task-neutrality, replay, and matched-arm checks before a Study is
launched.
