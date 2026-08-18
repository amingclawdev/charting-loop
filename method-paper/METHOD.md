# Charting Loop corridor method — v8

Status: **normative source**. A study or implementation adopts this version only by
pinning an exact frozen catalog identity (source commit, path, content digest, and
scope-datum digest); a branch tip or mutable working-tree copy is not a method input.
The earlier frozen `paper2-current-v2` and `charting-loop-method-v4` through
`charting-loop-method-v7` packages remain independently addressable historical study
inputs. Other Markdown, templates, schemas, and checklists are explanatory or
executable projections and must not silently add requirements.

## 1. Claim boundary

This method specifies how to construct and examine a corridor Candidate. It does not
prove the Charting Loop theory, semantic correctness, real-world authority, causal
benefit, or the truth of an evaluator's judgment. Structural validation proves only
that declared records and immutable joins are coherent.

The P/D/E vocabulary and probabilistic framing originate in the published Theory v1
([Zhang, 2026](https://doi.org/10.5281/zenodo.21844624)). This citation records
scholarly provenance; it does not incorporate the theory paper as a second normative
method source. Repository-specific operational mappings and diagnostic procedures in
this document are method claims. They do not, by themselves, require a new theory
version. A future Theory v2 is warranted only by a material change to the theory's
definitions, factorization, scope, predictions, or falsifiers.

The method has two input planes and one control plane:

- **Rule input plane** — versioned normative constraints that permit, forbid, or select
  transitions within declared scopes.
- **Fact input plane** — admitted, versioned observations or data. A Fact can support a
  Rule application but does not authorize action by itself.
- **Guide control plane** — a deterministic projection
  `Evaluate(Rules, admitted Facts, role/scope, warranties) -> next Entrance | typed refusal`.
  Guide is a function over the two input planes, not a third kind of knowledge source.

A paper, method package, retrieval corpus, or other supporting material is a pinned
`MethodRef` or knowledge input. It may inform Rule construction, but a runtime cannot
promote it or a Fact into an authorizing Rule without an explicit authorized transition.

### Architecture and projection boundary

The named objects in this method are **semantic roles and proof obligations**, not a
required software architecture. Position, Direction, Entrance, Rule, Fact, Guide,
Gate, Contract, Candidate, receipt, certificate, and warranty do not imply separate
services, agents, classes, files, tables, or schema field names. One physical component
may discharge several roles, and one role may be projected across several components,
provided the propositions, identities, transitions, and evidence remain separately
checkable.

A Corridor may therefore be implemented as a prompt or checklist, a rule table, a
static validator, a command-line tool, a deterministic service, a workflow or policy
engine, or a declared composition of these. Conformance depends on semantic and
evidence equivalence to this method, not on naming, module boundaries, deployment
shape, or resemblance to any source system. Repository examples, including Aming
Claw, are practice sources and non-normative projections; none is a reference
architecture.

Work rows, capability modules, timelines, and reminders introduced below are likewise
semantic interfaces, not required classes, files, databases, or services. They may be
represented by any canonically frozen equivalent. Their purpose is to preserve task
decomposition and reusable domain mechanics across implementations without turning a
particular source system into the method.

The method has two navigation variables. **Position (P)** is the checkpointed location
of the governed work over admitted Facts. **Direction (D)** is the effective projection
of frozen objective and applicable Rules at that Position. **Entrance (E)** is the
deterministic Guide result for one transition—an Entrance or typed refusal—not a third
stored state variable or an independent source of authority. Facts principally supply
P; Rules and the frozen objective principally determine D; Guide derives E from their
pinned identities. No component gains an exclusive claim over any semantic role.

Published Theory v1 retains its own P/D/E vocabulary and probability statement. This
two-variable navigation model is a versioned method decision about construction and
replay; it does not silently revise the published theory. Any later theory revision
must be proposed and frozen separately.

## 2. Core objects

### Position

A Position is an immutable, content-addressed **checkpoint** over the governed object,
role binding, exact world, and admitted-Fact state. A checkpoint contains a stable
`PositionRef`, its canonical digest, the admitted-Fact root and admission receipt,
the evidence-prefix watermark from which those Facts were admitted, the applicable
scope, unresolved or conflicting Fact references, and the exact `WorldRef`. Replaying
a decision pins this checkpoint; it does not reconstruct Position from ambient files,
the latest timeline, or an agent summary.

A Position binds the governed object and exact world state to a role. A **role
definition** is a versioned Rule that states duties, permissions, scope, and transition
constraints. A **role assignment** is a separate, provenance-bearing binding of a
holder to that definition and scope. Reusing the same role label does not prove an
assignment. The assignment must also resolve to an admitted Fact; Position cannot use
an assignment that bypasses the Fact plane. At minimum Position names both records, the
object or revision, and an exact `WorldRef`. Evidence from one role cannot be replayed
as evidence authored by another. A worker's self-report is a Fact, never the sole
independent proof of Position.

Raw timeline, log, tool, or evaluator evidence does not enter a Position merely by
existing. It first needs admission under the pinned admission Rule. Creating a
Position checkpoint is an audit and replay operation, not a Gate: a construction
experiment records missing or unresolved checkpoint material without installing a new
runtime permission barrier.

### Direction

Direction has two separately pinned forms:

- the **frozen Direction datum** is the source-complete objective, acceptance ledger,
  governing Rule references, scope, and declared precedence or unresolved conflicts
  frozen for the Candidate; and
- the **effective Direction projection** is
  `ProjectDirection(frozen Direction, Rule closure, Position, scope, warranties)` for
  one exact Position checkpoint.

The effective projection names the applicable and non-applicable Rule IDs with reasons,
current obligations and prohibitions, unresolved conflicts, warranty assumptions, and
its canonical `DirectionDigest`. It does not choose an operation or fill operation
arguments; that is the later Guide/Entrance step. For the same frozen Direction, Rule
closure, Position checkpoint, scope, and warranty states, the effective Direction is
identical.

A later frozen Direction datum supersedes by an explicit transition and creates a new
Candidate; it does not rewrite the meaning of an earlier dispatch. A Position change
may change which frozen Rules apply and therefore yield a new effective Direction
projection without changing the frozen objective. Effective Direction must resolve to
declared Rule authority; placing objective text beside a Guide result cannot bypass the
Rule input plane.

A **counterfactual transition** is a read-only evaluation over explicitly substituted
inputs, not a state transition. `CounterfactualTransition` binds the base
`PositionRef`, base `DirectionDigest`, exact substituted Position and/or Rule-closure
identity, the unchanged remaining inputs, and the resulting projected Direction plus
hypothetical Guide result. The record is marked `hypothetical=true`; identical base,
substitution, scope, and warranty inputs produce the same result. It may explain how a
different admitted state or Rule revision would alter an obligation or proposed
Entrance, but it cannot admit a Fact, advance or replace Position, mutate the frozen
acceptance ledger, append a real transition to the Position timeline, or establish a
certificate, Warranty, authority, PASS, or C. Only separately observed evidence
admitted under the applicable Rule can create a new real Position from which Guide is
run again.

#### Task acceptance ledger

For a task-conditioned Candidate, Direction includes an immutable **task acceptance
ledger** compiled from the complete public task instruction and every public
specification it names as authoritative. The ledger is a map of what success means,
not a stored solution. Each normative clause is either represented by one atomic item
or explicitly recorded as unmapped or ambiguous. Every item has:

- a stable acceptance ID, exact public source reference, normalized statement, and
  required/optional declaration;
- task scope: the objects, paths, record types, phases, quantifier, and applicability
  boundary to which the item applies;
- a decision Rule that says what observation would pass, fail, or leave the item
  unknown; and
- typed relations to other items—`requires`, `subsumes`, `overlaps`,
  `conflicts`, or `derived_from`.

Do not collapse definition, applicability, coverage, and assessment into one status.
`definition_state` says whether the Rule is defined or ambiguous; applicability is
decided for the exact task world; coverage says whether every public normative clause
was mapped; assessment records the observed `pass`, `fail`, `unknown`, or
`not_reached` outcome. A conflict or overlap without source-authorized precedence
remains unresolved. The builder cannot invent priority merely to make the ledger close.

The ledger is frozen inside the Corridor, while applicability and assessment outcomes
are later Facts outside that frozen byte set. Freezing preserves an omission as
faithfully as it preserves a correct map; it does not prove completeness. A consumer
must therefore treat ledger identity and ledger completeness as separate claims.

#### Behavioral acceptance closure

Textual clause coverage is necessary but not sufficient for requirements whose meaning
spans a behavior space. For every universal, negative, stateful, temporal, or coupled
Rule, the ledger also declares the finite behavioral partition used for assessment:
boundary classes, relevant state and operation combinations, transition orderings,
interactions, and applicable metamorphic relations. Each declared partition binds to
acceptance IDs and says what observation would pass, fail, or remain unknown.

This is not a claim that finite tests prove an unbounded property. The ledger records
the covered partition and the unresolved remainder separately. Representative examples
cannot silently stand in for a universal or negative Rule, and checking each Rule in
isolation cannot establish a coupled invariant. When the study labels a Rule high risk,
Independent QA must derive at least one source-grounded observation that is independent
of the Builder's own harness or report `blocked`/`not_assessed`. These obligations stay
non-gating in the construction-experiment profile.

#### Work backlog and reusable capability modules

A task-conditioned Corridor may compile the acceptance ledger into an immutable
**work backlog**. A **work row** is a bounded execution projection: it has a stable row
ID, acceptance-ID bindings, declared dependencies, task scope, explicit done-when
conditions, selected capability IDs, and advisory reminders. A row is not a new Rule,
Fact, Gate, authority source, or independent definition of success. Its acceptance
bindings must cover the frozen ledger without inventing, weakening, or silently
dropping a requirement; dependency cycles and dangling acceptance or capability IDs
are invalid projections.

A **capability module** is reusable domain mechanics with a stable ID, version, digest,
entrypoint, input and output contracts, applicability signals, and declared side
effects. Examples include a generic binary inventory, a schema inspector, or a
replay-capture primitive. The reusable module contains mechanics, not task Rules,
fixed offsets, candidate answers, hidden evaluator knowledge, or outcome-derived
patches. A task Builder selects and binds applicable modules to work rows, then adds
task-specific adapters inside the Corridor. Module presence or applicability never
authorizes execution, and a mutating side effect must remain explicit.

For a reportable construction experiment, the runner freezes the reusable capability
pack before exposing the scored task, records its exact byte identity, and forbids
learning new module behavior from the task's later score, verifier output, or role
transcript. A same-task feedback rerun may test engineering regression but is not a
fresh leaderboard or transfer sample.

### Guide

Guide is the deterministic control-plane projection defined above. It first resolves
the pinned Position checkpoint and effective Direction, then evaluates
`Guide(PositionRef, DirectionDigest) -> Entrance | typed refusal`. For the same exact
Rules, admitted Facts, role definition and assignment, scope, warranty states,
`WorldRef`, Position checkpoint, and effective-Direction digest, it returns the same
single result. An
implementation may use caches or indexes, but observable selection cannot depend on an
unbounded search, branch tip, ambient state, or undeclared ranking choice.

When a work backlog is declared, a runtime Guide may project the current row, its
bounded capability set, and reminder items from the frozen rows plus the visible
Position-ledger prefix. New admitted Facts create a new Position checkpoint and may
change the effective Direction projection; they do not alter the frozen Direction
datum. The row projection cannot alter acceptance Rules, mark a row complete without
observation, or promote a reminder
into an authorizing predicate. A **reminder** is an advisory, replayable statement
attached to a row state such as ready, entered, before mutation, before completion, or
blocked. Missing or ignored reminders remain observable but never prevent task
execution or external evaluation unless a separately declared long-lived-system Rule
authorizes an explicit Gate.

#### Rule closure, Contract binding, and Gate conformance

A **Rule closure** is the exact applicable Rule set for one role, scope, and
`WorldRef`, including every Rule ID, version, digest, source-authorized precedence or
unresolved conflict, and the closure digest. Rule is the normative authority layer.
An operational **Contract** may be a useful versioned container that binds a Rule
closure to interfaces, identities, and evidence fields, but it is not a third input
plane or an independent source of authority. Changing a Contract changes normative
meaning only when an authorized transition changes its Rule closure or binding; that
transition creates an explicit new revision rather than silently editing the old one.

Rule closure has two separate proof obligations:

- **Rule consistency:** within one revision, scope, and `WorldRef`, no two applicable
  Rules have an unresolved requirement to produce incompatible verdicts, actions, or
  state. Any precedence that resolves a conflict is itself source-authorized and
  pinned. An unresolved conflict produces a typed `rule_conflict`; repairing a Gate
  or Guide locally cannot resolve it.
- **Rule-transition coherence:** across a declared path, the admitted output Facts,
  identities, scopes, and warranty states of each transition are admissible inputs to
  the next transition under the pinned Rule revisions. A Rule change, identity
  rotation, or invalidation is an explicit transition to a new revision or generation,
  never an ambient reinterpretation of earlier evidence.

A **Gate** is an optional enforcement projection
`Check(Rule closure, admitted Facts, role/scope, warranties, WorldRef) -> permit | typed block`.
It can block an action, but it cannot invent a Rule, admit a Fact, synthesize missing
evidence, or amend a Contract. Every Gate predicate maps to a pinned Rule ID and the
exact admitted-Fact selector it evaluates. Gate conformance is complete when no
applicable Rule is silently omitted and sound when no predicate imposes an orphan
condition that lacks Rule authority. A Gate, Guide, and resulting Entrance for one
decision must bind the same Rule-closure digest, Position checkpoint, effective-
Direction digest, admitted-Fact root, role/scope, `WorldRef`, warranty states, and
verdict. A stale projection or disagreement produces
a typed `projection_mismatch`, not a fallback decision.

**Gate-chain coherence** is stronger than pairwise Gate success. Every declared
permit path must be jointly satisfiable: a legal output of one Gate is admissible to
the next, and this remains explicit through retry, resume, repair, identity or fence
rotation, fan-out, fan-in, merge order, invalidation, and terminal transitions.
Intentional denial branches end in a typed block, but incompatible downstream evidence
demands must not make every Rule-permitted state unable to progress. A later Gate must
not require evidence that an earlier legal transition could never produce. Whole-chain
analysis includes blocked and bypassed paths; a no-PASS bypass can reveal later
dependent blocks but cannot make the chain coherent or establish C.

### Entrance

Entrance is the derived transition result of Guide evaluation, not a third navigation
variable, checkpoint, Rule, Fact, or authority plane. A Guide evaluation has exactly
one semantic result. A successful result is one **Entrance**; otherwise it is one typed
refusal with a stable reason code. The result binds the source `PositionRef`,
`DirectionDigest`, Rule-closure digest, and evaluation algorithm identity, so replaying
the same inputs returns the same result. The Entrance
binds:

1. the frozen task and frozen Direction datum plus effective `DirectionDigest`;
2. the starting Position checkpoint and exact `WorldRef`;
3. the applicable Rule set;
4. one deterministic, consumable instruction with a pinned operation identity and
   version, canonical input binding, closed lookup or selection scope, declared result
   cardinality, and content or closure digest;
5. a unique allowed-action string set, its canonical set digest, exactly one declared
   action-transition Rule with matching ID/version/scope/ref and the same digest, and an
   explicit blocked outcome; and
6. the assigned role permitted to traverse it.

The Entrance may be serialized across several files, commands, interfaces, messages,
or physical actions, but those are projections of the same entrance identity. Multiple
UI buttons or files are not multiple semantic Entrances. A key, query, or human-readable
reference is acceptable only when its resolution is deterministically bounded; an
unconstrained lookup merely defers the decision.
Giving the executor a large file and telling it to use grep, search, or RAG formally
pushes bytes but semantically pulls the instruction at execution time. That pattern is
not a consumable Entrance unless the selection scope, digest, rule, and result bound are
already frozen. Choosing any undeclared path is a bypass.

These pins are structural declarations. A manifest validator cannot by itself
dereference an operation or selection-scope digest, prove that the declared operation
ran, or prove closed runtime selection. A real Candidate needs a GuideReceipt or
profile-equivalent observation and a consume-time verifier to establish what the
runtime actually selected and invoked.

### Candidate

A Candidate is a version-identifiable proposal for a corridor revision. An open
Candidate may still be built and corrected; it is neither immutable nor certifiable.
A frozen Candidate revision seals its semantic closure: the selected Guide result,
role-bound Position, implementation artifact closure (including its runner-owned Guide
binding), pinned
MethodRefs/knowledge inputs, Rule and Fact planes, exact WorldRef, and known limits.
Only that frozen revision is immutable and eligible for traversal or certification.
Any semantic change after freezing creates a new revision. A Candidate, open or frozen,
makes no certificate, warranty, authority, charted-state, or score claim by itself.

## 3. Exact worlds

A `WorldRef` is exact rather than ambient or moving-target-relative. It contains:

- the project, run, and generation identities, or profile-declared equivalents;
- the canonical governed-world identity and an immutable base revision;
- the environment or fixture digest;
- the RAW ledger stream identity, contiguous prefix watermark, and prefix digest;
- the admission receipt and admitted-root digest plus the admission Rule revision and
  digest;
- the projector schema version and algorithm identity, version, and digest; and
- the derived-state digest.

The active environment, “current,” a mutable label, or an unpinned version is not a
`WorldRef`. A software/Git profile may require a credential-free canonical HTTPS
repository URL and full commit; a database, API, image, device, or physical-process
profile must declare an equivalently immutable identity and canonical serialization.
Changing any listed identity or digest creates a different `WorldRef`.
Timeline presence alone is not an admitted Fact: only the admission receipt/root under
the pinned admission Rule can move evidence into the Fact plane.

A Position checkpoint canonically joins one `WorldRef`, admitted-Fact root, role
definition and assignment, governed-object revision, evidence watermark, and unresolved
Fact set. Any change to one of those fields creates a new `PositionRef`. The checkpoint
does not duplicate RAW evidence and cannot admit it; it is the replay key for the state
that the Guide actually evaluated.

A `WorldSpan` is closed only when it binds exact start and end `WorldRef` values over
the same project, run, generation, governed-world identity, immutable base revision, environment,
admission Rule, and projector. Its end may extend only the same RAW ledger by a
contiguous prefix. The admitted Fact subset and derived state may change as newly
present evidence is admitted, but every such change yields a new endpoint `WorldRef`.
A base-revision, admission-Rule, or projector change ends the old span and requires a
new generation and Candidate revision; no certificate may bridge those worlds. An
open-ended “until now” span cannot certify a traversal, and an admitted-prefix summary
cannot substitute for the RAW prefix.

### Implementation profiles

Every use declares one profile whose additional encodings and enforcement choices are
frozen with the Candidate. A profile may strengthen the core but cannot weaken it or
silently change the meaning of a core object.

- The **construction-experiment profile** freezes the acceptance ledger, work backlog,
  selected capability pack, Guide result, Candidate, evidence visibility, and scoring order, but does not install new blocking
  runtime Gates. Incomplete internal closure remains visible as `blocked` or
  `not_assessed` while the executor and external evaluator continue.
- The **long-lived governed-system profile** may enforce declared Gates after their Rule
  authority, Fact selectors, projection conformance, and whole-chain satisfiability are
  established. Its recovery procedure uses the linear-unlock rule in Section 6.
- A **software/Git projection** may encode an Entrance as facade/interface/operation,
  canonical arguments such as `argument_mode` and `opaque_key`, and a closed lookup
  scope; it may encode a WorldRef with a strict HTTPS repository URL and full commit.
  These are profile fields, not universal vocabulary.
- A **non-Git projection** supplies equivalent canonical identities—for example a
  database snapshot, API version, image digest, device state, signed record set, or
  bounded physical-process checkpoint—and declares how they are serialized and
  verified.

### Append-only Position ledger

A prospective execution maintains a runner-held, append-only **Position ledger** over
the observable work. Each entry has a monotonically increasing sequence, the preceding
entry digest, its own canonical digest, observation time, actor and session, role,
Position checkpoint, frozen-Direction and effective-Direction identities, the exact before/after `WorldRef` or closed
`WorldSpan`, and content-addressed action, result, and artifact references. Corrections
append a new entry; they never rewrite an earlier observation. Logs, database snapshots,
tool calls, service receipts, and evaluator outputs may be referenced when observable,
but credentials, hidden reasoning, and hidden benchmark material are excluded.

The Position ledger is RAW observation, not an admitted Fact. Only the pinned admission
Rule and receipt/root can move selected evidence into the Fact plane. Ledger presence,
continuity, or a matching hash cannot by itself produce PASS, a PathCertificate, either
Warranty, authority, or current C. A missing, discontinuous, or unavailable ledger is
reported as evidence loss; it does not erase the run or suppress an official score.

If the Corridor declares work rows, row events are appended to this same runner-owned
ledger rather than written back into the frozen backlog. A deterministic projection
derives `pending`, `ready`, `in_progress`, `blocked`, `done`, or `not_applicable` and
names the current row. Multiple active rows, an unknown row reference, or a missing
dependency observation is reported as projection inconsistency; it does not rewrite
history or mint a blocking Gate. Worker and QA may query the same projected row,
bounded capability list, and reminders when the study freezes that visibility.

### Independent QA

For a current-C or consumability claim, an **Independent QA** actor and
session are distinct from the Candidate Builder and the Executor. QA binds the exact
frozen subject revision, Direction, Position, `WorldRef` or closed `WorldSpan`, and the
Position-ledger prefix it actually reviewed. It emits one append-only assessment Fact:
`pass`, `fail`, `blocked`, or `not_assessed`. Builder self-tests and executor success
claims remain ordinary Facts and are never the sole independent support for QA pass.

The QA protocol forbids QA from editing the Candidate or official task state. A repair
is performed by the Executor/Worker and creates a new revision with a new assessment;
the failed or blocked assessment remains. QA pass is additional evidence and never
substitutes for, issues, or implies a TraversalReceipt, PathCertificate,
EvidentialWarranty, AuthorityWarranty, authority, benchmark PASS, or current C. In an
experiment, QA timing and visibility are frozen study variables. QA failure does not
authorize deletion, repair beyond the frozen task-level deadline, or suppression of
scoring.

In the bounded cooperative-agent experiment profile, Worker and QA are
protocol-conformant roles rather than hostile security principals. A role label in a
submission store is a namespace and provenance assertion, not a credential, account,
ACL, or authorization Gate. Conformance in that profile requires the agents and runner
to obey the declared write boundary and retain evidence of the role/session that acted;
it does not require the store to defend against a process deliberately impersonating
another role. A security-adversarial profile would need to declare and evaluate its
own enforcement mechanism separately.

When a task acceptance ledger exists, QA reads and may execute the same frozen
Corridor as the executor, but it must also independently re-read the original public
task sources. Corridor-assisted QA checks each stable acceptance ID, its exact
applicability, and the ledger's source coverage. It may report `pass` only when every
required applicable item passes, every non-applicable item has evidence, the expected
ID set is exact, and no clause, relation, applicability, or result remains unmapped,
unresolved, unknown, or unexpectedly not reached. A concrete `fail` needs a
replayable witness tied to an acceptance ID. Otherwise the correct outcome is
`blocked` or `not_assessed`.

Closing a reported witness is not task closure. After repair, QA re-evaluates the
entire ledger and repeats its source-completeness check. This protects against a
shared-map failure in which Builder, Worker, and QA all reason correctly from the same
incomplete Corridor.

When frozen work rows and capabilities exist, QA uses the same row definitions,
capability identities, and runner timeline prefix as the Worker. It may replay a
selected capability and check row done-when evidence, but a row status or reminder is
never sufficient evidence for an acceptance result. QA still binds each conclusion to
the acceptance ledger and original public sources.

For universal, negative, stateful, temporal, coupled, or study-declared high-risk
acceptance Rules, QA also checks the declared behavioral partitions, interactions,
transition orders, boundary classes, and applicable metamorphic relations. Re-running
only the Builder's examples or harness is not independent support. QA derives at least
one source-grounded observation through an independently selected probe when feasible;
otherwise it preserves the uncovered remainder and reports `blocked` or
`not_assessed` rather than upgrading representative coverage to whole-rule closure.

### Total deadline and monotonic submission custody

For a bounded single-task experiment, freeze one total task deadline. Builder,
Executor/Worker, Independent QA, repair, and closure are logical handoffs that consume
the same remaining clock; they do not own independent hard time allocations. A profile
may expose advisory pacing targets, but crossing one cannot terminate a complete
submission, discard progress, or suppress scoring. The runner may reserve a small,
declared portion of the same total clock only for process quiescence, snapshot
verification, restoration, evidence flush, and return to the external evaluator. This
reserve is not a model phase or an additional task budget.

Submission custody is monotonic. As soon as a Worker has one complete, scorable task
state, it freezes an immutable submission revision covering every declared output or
task-state path and repeats that operation after each verified improvement. A newer
revision becomes current only after all declared bytes and identities are closed and
verified. A selected latest reference binds exactly to the manifest role, sequence,
snapshot identity, and tree digest. Incomplete work, a timed-out repair, QA judgment,
or a later partial mutation
cannot replace or delete the newest complete Worker revision. At normal return or when
the task deadline is reached, the runner promotes/restores that newest complete Worker
revision before external scoring. If none exists, it reports `no_complete_submission`
and must not manufacture one.

QA freezes each completed assessment as a separate append-only audit revision against
the same Corridor and Worker revision. QA may request repair, but its snapshot never
becomes the task submission and its verdict cannot prevent restoration or external
grading. A submission snapshot is custody evidence, not acceptance evidence, a Gate,
a PathCertificate, authority, or current C. Restore must run with the task actor's
existing operating-system authority; the runner may not use snapshot restoration to
grant access the Worker did not possess. Before the first destination mutation, a
file-based restore validates the complete declared set of blobs, identities,
destinations, parents, modes, and staging writes. It then atomically replaces each file
individually. This does not claim a whole-set or cross-filesystem transaction: a
commit-phase operating-system failure or path race may leave a truthfully reported
restored prefix. File-based profiles enumerate absolute task paths; profiles with
databases, services, or other world state provide an equivalent task-conditioned
freeze/restore adapter whose closed identity is audited before use.

## 4. Construction procedure

1. **Pin the method.** Select one exact cataloged method version and verify its source
   commit, path, content digest, and scope-datum digest. More than one historical
   version may remain independently study-eligible; “latest” is never a valid
   MethodRef. Study eligibility permits a package to be frozen as a research input,
   while `adoption_eligible=false` (and its legacy projection
   `builder_eligible=false`) means it is not approved for operational adoption.
2. **Freeze exogenous inputs.** A runner freezes the task, Direction, fixtures,
   evaluator/scorer, model/runtime constraints, and initial `WorldRef`. Empirical task,
   run, score, and optional-log data remain under `exogenous/`; they are not imported
   into this method paper.
3. **Compile task acceptance.** Decompose every normative clause in the public task
   instruction and named public specifications into the task acceptance ledger. Give
   each item a stable ID, source reference, scope, Rule, and typed relations. Re-read
   the sources, record every unmapped or ambiguous clause, and never mark coverage
   complete while either list is non-empty. For universal, negative, stateful,
   temporal, or coupled Rules, declare behavioral partitions, boundary classes,
   interactions or transition orders, applicable metamorphic relations, and the
   unresolved remainder. This is frozen-Direction construction, not task execution.
4. **Compile work and reusable mechanics.** Project the acceptance graph into bounded
   work rows whose bindings cover the complete acceptance-ID set. Give every row stable
   dependencies, scope, done-when conditions, selected capability IDs, and advisory
   reminders. Validate dependency acyclicity and all joins. Select reusable capability
   modules only from a task-neutral pack frozen before the scored task, verify their
   versions, digests, contracts, applicability, and side effects, and keep task-specific
   adapters inside the Candidate.
5. **Freeze inputs.** Inventory the Rule and admitted-Fact planes with stable references
   and scope. Pin supporting papers or packages as MethodRefs/knowledge inputs; reject
   implicit promotion into Rules. Freeze the acceptance ledger and work backlog with
   Direction, and freeze the selected capability identities with the Candidate.
6. **Checkpoint Position and project Direction.** Name the Candidate revision,
   versioned role-definition Rule, separate authority- and liveness-bearing assignment
   Fact, governed object, admitted-Fact root and evidence watermark, and exact
   `WorldRef`; hash them into one `PositionRef`. Declare which independent Facts can
   establish the assignment. Project the frozen Direction and applicable Rule closure
   at that Position into one effective `DirectionDigest`, retaining non-applicability
   reasons and unresolved conflicts.
7. **Compile Guide and one result.** The runner freezes the deterministic Guide binding
   over `PositionRef`, `DirectionDigest`, Rules, admitted Facts, role/scope, and
   warranties before builder dispatch.
   Materialize one Entrance with a bounded consumable instruction, or one typed refusal
   with a durable reason. The Entrance binds its effective Direction to the declared
   Direction-compilation Rule and its canonical allowed-action set to the declared
   action-transition Rule carrying the identical action-set digest; a typed refusal
   binds its governing Rule and evaluated input context. The runner pins the operation,
   canonical input digest, selection-scope identity/digest, and result bound using the
   declared profile. A physically co-located Contract remains runner-owned and
   read-only; location does not make it builder-writable.
8. **Build the open Candidate.** Give the builder only the declared Entrance and pinned
   MethodRef/knowledge inputs. The builder writes only the explicitly builder-owned
   implementation surface, excluding the frozen Guide contract, and returns completion
   or a blocker. The open proposal remains mutable and uncertifiable.
9. **Freeze the Candidate.** Seal the implementation tree and all declared inputs by
   digest into one semantic closure. From this point, repair creates a new revision;
   freezing alone does not place any scope in C.
10. **Record the Position ledger.** Start the runner-held, hash-linked append-only stream
   before execution and bind every observable transition to its Position checkpoint,
   frozen and effective Direction, actor/session, and exact world identities. Do not expose the audit stream
   to an agent unless a frozen study declares that visibility as an intervention.
   When work rows exist, append row events outside the frozen Candidate and project the
   same current-row Guide and advisory reminders for each declared consumer. Admit
   newly observed evidence under the frozen admission Rule, create a new Position
   checkpoint, and recompute effective Direction before deriving a later Entrance.
11. **Freeze the first complete submission.** The Worker freezes a complete, scorable
    task-state revision as soon as one exists and freezes each verified improvement.
    Logical phase changes consume one task-level clock and never invalidate the newest
    complete revision. Submission custody remains separate from Candidate freezing and
    from acceptance.
12. **Assess independently.** A distinct Independent QA session reviews the exact
    frozen revision, the complete task acceptance ledger, the original public task
    sources, and the Position-ledger prefix available to it, then appends `pass`,
    `fail`, `blocked`, or `not_assessed`. QA cannot edit. Any permitted repair
    produces a new revision and consumes the same frozen task-level deadline. Freeze a
    repaired submission only after it is complete; otherwise retain the prior Worker
    revision. After repair, re-assess the entire ledger rather than only the prior
    witness.
13. **Promote for scoring.** At normal return or total-deadline exhaustion, stop the
    active role, establish process quiescence, verify and restore the newest complete
    Worker submission, and return unconditionally to the external evaluator. Preserve
    every QA assessment separately. Report absence or restore failure without claiming
    success.
14. **Traverse independently.** A runner or evaluator executes the exact Candidate once
   over a closed `WorldSpan`, records the actual path, freshness checks, bypass status,
   and outcome, and signs or otherwise identifies the receipt issuer.
15. **Certify the demonstrated path.** An independent PathCertificate may make only its
   certificate-covered path provisionally charted. No other Candidate scope is implied.
16. **Establish current consumability.** Only scope with
    a QA `pass`, PathCertificate, and live EvidentialWarranty enters current,
    scope-indexed C. QA pass is not a substitute for either record. Consuming the
    actor–role Assignment additionally requires its EvidentialWarranty and
    AuthorityWarranty to be `live`; elsewhere AuthorityWarranty gates only when the
    applicable Rule or tier requires it.
17. **Preserve outcomes.** Passed, failed, blocked, protocol-invalid, and infrastructure
    outcomes remain indexable exogenous Facts. A task score cannot rewrite the Candidate
    or method.

## 5. Orthogonal evidence and warranty surfaces

The following four certification and warranty record surfaces are independent. Exactly
two are warranty kinds: `EvidentialWarranty` and `AuthorityWarranty`.

- **TraversalReceipt** records what happened to one Candidate over one closed
  `WorldSpan`. It is an execution Fact, not a judgment of validity.
- **PathCertificate** states whether that receipt followed the frozen Entrance with
  fresh evidence and no bypass. It binds the Candidate, receipt, Rule set, and issuer;
  a passing certificate makes only the witnessed path provisionally charted.
- **EvidentialWarranty** states that a named claim was independently supported at a
  named `WorldRef` and time, with invalidation predicates. It may be
  `live`, `lapsed`, `unknown`, or `not_assessed`. Only a `live` warranty makes its
  certificate-covered scope currently charted (C). When Guide consumes an actor–role
  Assignment, this Warranty must also bind the admitted Assignment Fact and its current
  lifecycle validity.
- **AuthorityWarranty** states that an independent issuer supports a declared actor's
  authority for one role assignment, act, scope, Rule, and `WorldRef`. It has the same
  four states. Temporal freshness is liveness within a warranty, never a third warranty
  kind or an additional navigation variable.

A passing score is not a PathCertificate. A PathCertificate is not an Evidential
Warranty. An EvidentialWarranty is not an AuthorityWarranty. Authority evidence does
not prove traversal. Missing authority evidence means `not_assessed`, never approved.

The append-only Position ledger and `IndependentQAAssessment` are additional evidence
surfaces, not a fifth warranty or a replacement for any record above. QA may cite an
exact ledger prefix, but timeline presence alone never admits a Fact. For a prospective
current-C claim, QA pass joins the same frozen subject, Direction, Position, and world;
the certificate and live warranties must still be established by their own issuers.

Raw user–AI or authority logs are optional, format-free reminders that live outside the
Candidate in exogenous run storage. A Candidate may carry only a consent-aware pointer
or manifest; raw log bytes are excluded from its semantic payload and identity. Log
presence, shape, or completeness never gates participation, validation, ordinary
comparison, or either Warranty. A strict study may assess declared logs under its own
profile, but absence remains `unknown` or `not_assessed` and cannot be promoted to an
AuthorityWarranty. The executor cannot issue an independent warranty for its own claim,
and an AI cannot create real-world authority by citing this method.

Before runtime, or when no live warranty is available, a declared paper-based drift
diagnosis may identify unresolved Position, Direction, Entrance-derivation, or warranty
conditions at a critical point.
Its advisory `AssessmentReceipt` binds the claim, Rule, frozen evidence, `WorldRef`,
scope, time, and method version. It is not a Warranty and cannot mint, renew, or revoke
one; authorize action; satisfy a gate; produce PASS; or count as independent
verification.

For a paper-grounded failure diagnosis, classify the invariant that the observed
decision violates rather than the file, module, actor, or message that exposed it:

- **P (Position):** the selected checkpoint locates the wrong actor, role, object,
  layer, admitted-Fact state, or exact world.
- **D (Direction):** the frozen objective, governing Rule closure, applicability, or
  effective projection at that Position is wrong, unauthorized, incomplete, or
  silently superseded.
- **E (Entrance result):** Position and Direction are adequate, but Guide cannot derive
  one legal transition or selects a result other than the single declared Entrance.
  This is a transition-result failure class, not a third navigation variable.
- **X (execution):** the authorized Entrance is correct, but its action is executed
  incorrectly; X is recorded outside the P/D navigation state and Entrance-result
  classification.

The evaluator records the selected invariant, frozen evidence, uncertainty, and any
counter-witness. A composite mechanism may violate more than one invariant. This rubric
is an advisory method procedure, not a Warranty, estimator, or empirical result.

## 6. U → C re-entry

`U` is an unresolved state: the Candidate is blocked, failed, stale, superseded, or
otherwise cannot support the next claimed transition. Constructing a replacement
Candidate is not itself U → C. Re-entry follows the complete chain
`U → new open Candidate → frozen Candidate → IndependentQAAssessment(pass) → fresh
traversal → PathCertificate → live EvidentialWarranty → scope-indexed C`. QA pass never
replaces the traversal, certificate, or Warranty. Before the Assignment is consumed,
its separate AuthorityWarranty must also be `live`; other authority gates apply only when their Rule
or tier requires one. The new Candidate revision has:

- a new candidate or revision identity;
- an explicit link to the prior Candidate and re-entry reason;
- a newly frozen Direction datum, Position checkpoint, derived Entrance, and
  `WorldRef`; and
- new implementation and traversal evidence.

Evidence from the prior revision remains historical and cannot be spliced into a
certificate or Warranty for the new revision. A PathCertificate alone reaches only the
provisionally charted path; stale, unknown, or absent warranty state leaves the claimed
scope outside current C. Re-entry is available after any outcome; it is not a backedge
that mutates history.

The proof obligations above describe when current C may be claimed; they do not require
an experimental Corridor to install a blocking runtime gate. During construction
experiments, incomplete acceptance, QA `blocked`, or QA `not_assessed` must remain
visible while the executor and external evaluator continue. Making the new obligations
mandatory preconditions would change the intervention and greatly increase U→C work.
Gate construction belongs to a separately declared long-lived-system profile after the
structure is stable.

If such a long-lived profile introduces a gate too early and the gate blocks because
required evidence cannot yet exist, preserve the block and use an explicitly
authorized no-PASS bypass/waiver to finish the original path. Carry one diagnostic
root through every downstream dependent bypass; later gates may also require bypass
because the first one intentionally left evidence gaps. This **linear unlock** exposes
one gate defect at a time. It never converts the bypassed path into PASS or C.

## 7. Composite mechanisms and proof-obligation order

Physical modules, documents, tools, and agents may combine responsibilities. For
example, one handoff can carry a Position checkpoint, its effective Direction, and the
derived Entrance; the method does not require a separate component per semantic role.
Composition does not collapse propositions:
Position, Direction, Entrance, EvidentialWarranty, and AuthorityWarranty must remain
separately named and their evidence receipts separately checkable.

The proof-obligation order is: pin method and exact world; compile source-complete
task acceptance including applicable behavioral partitions; admit Rules and Facts;
establish a consistent Rule closure and coherent Rule transitions; bind role definition
and assignment; checkpoint Position; project effective Direction; for a profile that
declares Gates, prove Gate conformance and whole-chain coherence; evaluate Guide to
one tagged result from the same Position, closure, and Fact root; freeze the semantic closure;
traverse one base world; certify the demonstrated path; establish a live scope-bound
EvidentialWarranty; then establish a live AuthorityWarranty where the assignment,
Rule, or tier requires it. A later obligation cannot retroactively satisfy an earlier
one.

## 8. Authority and conflicts

Authority is external to the method. Multiple authority actors are permitted, but each
claim must resolve actor, act, scope, version, provenance, and applicable conflict Rule.
An AI may activate a Rule only inside a pre-authorized envelope and inherits no broader
permission. When a cataloged method paper is adopted, it defines method Rules and a
construction specification. It still never supplies the task-specific Direction or an
external authority grant. Research-input eligibility does not imply operational
adoption eligibility.

## 9. Probability and experimental-unit bridge

For decision opportunity `i`, let
`Z_i = (R_def,i, R_asg,i, WorldRef_i, Datum_i, history_i)`, where the role definition is
a Rule and the assignment is an authority- and liveness-bearing Fact binding. The v8
method records navigation state as `(P_i, D_i)` and records `E_i` as the Guide's tagged
transition result conditional on that state. A study may still report the published
theory bridge `Pr(P_i, D_i, E_i | Z_i)` and its conditional chain
`Pr(P_i | Z_i) Pr(D_i | P_i, Z_i) Pr(E_i | P_i, D_i, Z_i)`, but must not reinterpret
that notation as three independent stored variables. Marginal success rates must not
be multiplied, and roles or events must not be treated as independent samples merely
because they are recorded separately.

A decision opportunity is a repeated observation. A run or scenario is the cluster and
primary experimental unit unless a later protocol justifies a different unit.
`not_reached` outcomes remain present rather than being dropped or silently recoded.
Failure-surface classification under Section 5 is an evaluator procedure, not
estimation. Estimator definitions and choices, confidence intervals, power, sample
size, and aggregate experimental results belong to a later Paper 3 and are not fixed
here.

## 10. Non-normative worked examples

The repository's
[`service-plan-corridor-e2e`](../demos/service-plan-corridor-e2e/README.md) engineering
demo exercises a deliberately small protocol fixture: paper-guided diagnosis before a
live warranty, a frozen Candidate projection at one exact WorldRef, bounded Guide
consumption, a same-generation contiguous-RAW-prefix extension, typed stale refusal, a new projection,
and fresh synthetic path records. These projections and fixture-labeled certificate and
warranty records do not constitute a second Candidate definition, independent issuance,
or a method-level claim that C has been established. The default parity record invokes
one deterministic evaluator rather than two agents. One digest-bound, sanitized
Docker/Codex pair is retained only as a runner-reported engineering observation.
Neither is a benchmark, an effect estimate, an authority assessment, or evidence that
this method is ready for operational adoption.

An Aming Claw Contract handoff illustrates one possible composite projection: one bound
handoff may jointly carry a Position checkpoint, effective Direction, a role definition
plus live assignment, and one derived Entrance. It is neither privileged nor required.
Any use as evidence must pin an exact
repository commit and trace cutoff, then map distinct receipts to each proposition;
this paragraph does not claim that Aming Claw implements every abstract obligation.

## 11. Conformance

A v8 implementation conforms only if it:

- preserves an exact role definition and separate role assignment; checkpoints Position
  over admitted Facts, evidence watermark, scope, governed object, and exact world; and
  never treats raw timeline presence as an admitted Fact or a checkpoint as a Gate;
- separates the frozen Direction datum from the effective Direction projection at one
  Position, pins applicable and non-applicable Rules, unresolved conflicts, warranties,
  and `DirectionDigest`, and keeps operation selection out of that projection;
- uses a declared deterministic Guide to return exactly one tagged, bounded, consumable
  Entrance or typed refusal from the pinned `PositionRef` and `DirectionDigest`, treats
  the result as derived rather than a third navigation variable, and recognizes that
  structure alone cannot prove runtime determinism;
- binds the Entrance action set and digest to exactly one declared action-transition
  Rule, and pins the profile-declared operation, canonical inputs, closed selection
  scope, and result cardinality;
- uses exact `WorldRef` and closed `WorldSpan` identities;
- keeps Rule and Fact input planes distinct from the Guide control plane and from
  MethodRef/knowledge inputs;
- treats Rule as the normative authority layer and any operational Contract as a
  versioned Rule-closure container/binding, never as an independent authority source;
- proves Rule consistency and Rule-transition coherence, and represents unresolved
  conflict, revision change, identity rotation, and invalidation explicitly;
- when Gates are declared, maps every Gate predicate to a pinned Rule and admitted-Fact
  selector, binds Gate and Guide to the same Position, effective Direction, closure,
  and verdict, and checks whole-chain satisfiability across retry, resume, repair,
  fan-out, and fan-in;
- freezes a task acceptance ledger whose atomic items retain source, scope, Rule, and
  typed relations; keeps definition, applicability, coverage, and assessment states
  distinct; and reports unmapped, ambiguous, or unresolved requirements rather than
  silently dropping them;
- for universal, negative, stateful, temporal, or coupled Rules, declares the assessed
  behavioral partitions, boundary classes, interactions or transition orders,
  applicable metamorphic relations, and unresolved remainder without claiming finite
  examples prove an unbounded property;
- when a work backlog is declared, preserves stable row IDs, complete acceptance
  bindings, acyclic dependencies, scope, done-when conditions, and selected capability
  IDs without treating a row as authority;
- binds every reusable capability module to an exact version, digest, input/output
  contract, applicability declaration, and side-effect level; keeps reusable mechanics
  free of task answers and post-outcome learning; and keeps task adapters inside the
  task-specific Candidate;
- records mutable row progress only in the runner-owned hash-linked Position ledger,
  derives current-row Guide and reminder views deterministically, gives Worker and QA
  the same declared view, and keeps every reminder advisory and non-gating;
- requires Corridor-assisted Independent QA to account for the exact acceptance-ID set
  and independently re-check public source completeness, while treating witness closure
  as narrower than whole-task closure; for high-risk behavioral Rules it also requires
  an independently selected source-grounded probe when feasible, otherwise preserving
  `blocked` or `not_assessed`;
- in a cooperative-agent experiment profile, treats Worker/QA role labels as
  namespaces and provenance rather than credentials or permission Gates, requires each
  role to obey its declared write boundary, and makes no adversarial-role isolation
  claim without a separately declared security profile;
- for bounded single-task experiments, uses one frozen total deadline rather than
  phase-owned hard allocations, freezes complete Worker submissions monotonically,
  versions QA assessments separately, binds `latest` exactly to the selected manifest,
  prevalidates the complete restore set, and uses truthfully reported per-file atomic
  replacement before external scoring without converting custody into a Gate,
  whole-set transaction claim, or acceptance claim;
- keeps the four record surfaces separate, recognizes exactly two warranty kinds, and
  keeps optional authority logs non-gating;
- represents open and frozen Candidate states, makes semantic edits create new frozen
  revisions, and completes U → C only through fresh traversal, PathCertificate, and a
  live scope-bound EvidentialWarranty;
- keeps experimental acceptance/QA incompleteness non-gating and reports it as
  `blocked` or `not_assessed` while preserving external evaluation;
- declares the exact implementation profile and proves semantic/evidence equivalence
  without requiring any named source system's modules, services, schema fields, or
  deployment shape; and
- reports eligibility from the exact frozen method catalog rather than inferring it
  from this mutable file or from version recency.

Conformance does not imply that the method works better than a control. That question
belongs to separately frozen, exogenous studies and repeated independent trials.
