# Charting Loop corridor method — prospective draft v3

Status: **prospective, un-cataloged working draft**. This file is the sole normative
method source in this repository, but these worktree bytes are not a cataloged study
input and are not builder-eligible. The frozen `paper2-current-v2` package remains
unchanged at its cataloged source commit; a study that names it receives those exact
v2 bytes, not this prospective amendment. Other Markdown, templates, schemas, and
checklists are explanatory or executable projections and must not silently add
requirements.

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

The architectural correspondence is dominant, not one-to-one: Facts principally
supply the substrate for Position (P); Rules principally anchor Direction (D) while
also constraining P and Entrance (E); Guide principally delivers E while recomputing or
checking the relevant P and D projection. P, D, and E are not independent probability
factors, and no component gains an exclusive claim over one of them.

## 2. Core objects

### Position

A Position binds the governed object and exact world state to a role. A **role
definition** is a versioned Rule that states duties, permissions, scope, and transition
constraints. A **role assignment** is a separate, provenance-bearing binding of a
holder to that definition and scope. Reusing the same role label does not prove an
assignment. The assignment must also resolve to an admitted Fact; Position cannot use
an assignment that bypasses the Fact plane. At minimum Position names both records, the
object or revision, and an exact `WorldRef`. Evidence from one role cannot be replayed
as evidence authored by another. A worker's self-report is a Fact, never the sole
independent proof of Position.

### Direction

Direction is the frozen objective and acceptance datum for this Candidate. A later
Direction supersedes by an explicit transition and creates a new Candidate; it does not
rewrite the meaning of an earlier dispatch. The effective Direction must resolve to a
declared compilation Rule; placing objective text beside a Guide result cannot bypass
the Rule input plane.

### Guide

Guide is the deterministic control-plane projection defined above. For the same exact
Rules, admitted Facts, role definition and assignment, scope, warranty states, and
WorldRef, it returns the same single result: a next Entrance or a typed refusal. An
implementation may use caches or indexes, but observable selection cannot depend on an
unbounded search, branch tip, ambient state, or undeclared ranking choice.

### Entrance

A Guide evaluation has exactly one semantic result. A successful result is one
**Entrance**; otherwise it is one typed refusal with a stable reason code. The Entrance
binds:

1. the frozen task and Direction;
2. the starting Position and exact `WorldRef`;
3. the applicable Rule set;
4. one deterministic, consumable instruction whose declared facade ID/version/digest,
   nested interface ID/version/digest/operation, canonical argument digest
   (`argument_mode` plus `opaque_key`), and lookup-scope ID/version/digest are pinned,
   closed, bounded, and single-result;
5. a unique allowed-action string set, its canonical set digest, exactly one declared
   action-transition Rule with matching ID/version/scope/ref and the same digest, and an
   explicit blocked outcome; and
6. the assigned role permitted to traverse it.

The Entrance may be serialized across several files, commands, or interfaces, but those
are projections of the same entrance identity. Multiple UI buttons or files are not
multiple semantic Entrances. An opaque key is acceptable only when its lookup is
deterministically bounded; an unconstrained key or query merely defers the decision.
Giving the executor a large file and telling it to use grep, search, or RAG formally
pushes bytes but semantically pulls the instruction at execution time. That pattern is
not a consumable Entrance unless the selection scope, digest, rule, and result bound are
already frozen. Choosing any undeclared path is a bypass.

These pins are structural declarations. A manifest validator cannot dereference the
facade, interface, or lookup-scope digests, prove that the interface operation ran, or
prove closed runtime selection. Navigation-keyword rejection is only an auxiliary
fail-closed check; a real Candidate needs a GuideReceipt and consume-time verifier to
establish what the runtime actually selected and invoked.

### Candidate

A Candidate is a version-identifiable proposal for a corridor revision. An open
Candidate may still be built and corrected; it is neither immutable nor certifiable.
A frozen Candidate revision seals its semantic closure: the selected Guide result,
role-bound Position, implementation tree (including its runner-owned Guide contract), pinned
MethodRefs/knowledge inputs, Rule and Fact planes, exact WorldRef, and known limits.
Only that frozen revision is immutable and eligible for traversal or certification.
Any semantic change after freezing creates a new revision. A Candidate, open or frozen,
makes no certificate, warranty, authority, charted-state, or score claim by itself.

## 3. Exact worlds

A `WorldRef` is exact rather than branch-relative. It contains:

- the project, run, and generation identities;
- the canonical repository identity as a strict HTTPS URL and full immutable base
  commit; the URL has
  a valid host and port and no credentials, query, fragment, whitespace/control
  characters, backslash, or dangling port separator;
- the environment or fixture digest;
- the RAW ledger stream identity, contiguous prefix watermark, and prefix digest;
- the admission receipt and admitted-root digest plus the admission Rule revision and
  digest;
- the projector schema version and algorithm identity, version, and digest; and
- the derived-state digest.

A branch is only a location hint. “Current,” a short commit, or an unpinned tag is not a
`WorldRef`. Changing any listed identity or digest creates a different `WorldRef`.
Timeline presence alone is not an admitted Fact: only the admission receipt/root under
the pinned admission Rule can move evidence into the Fact plane.

A `WorldSpan` is closed only when it binds exact start and end `WorldRef` values over
the same project, run, generation, repository identity, full base commit, environment,
admission Rule, and projector. Its end may extend only the same RAW ledger by a
contiguous prefix. The admitted Fact subset and derived state may change as newly
present evidence is admitted, but every such change yields a new endpoint `WorldRef`.
A base-commit, admission-Rule, or projector change ends the old span and requires a new
generation and Candidate revision; no certificate may bridge those worlds. An
open-ended “until now” span cannot certify a traversal, and an admitted-prefix summary
cannot substitute for the RAW prefix.

### Append-only Position ledger

A prospective execution maintains a runner-held, append-only **Position ledger** over
the observable work. Each entry has a monotonically increasing sequence, the preceding
entry digest, its own canonical digest, observation time, actor and session, role,
Position and Direction identities, the exact before/after `WorldRef` or closed
`WorldSpan`, and content-addressed action, result, and artifact references. Corrections
append a new entry; they never rewrite an earlier observation. Logs, database snapshots,
tool calls, service receipts, and evaluator outputs may be referenced when observable,
but credentials, hidden reasoning, and hidden benchmark material are excluded.

The Position ledger is RAW observation, not an admitted Fact. Only the pinned admission
Rule and receipt/root can move selected evidence into the Fact plane. Ledger presence,
continuity, or a matching hash cannot by itself produce PASS, a PathCertificate, either
Warranty, authority, or current C. A missing, discontinuous, or unavailable ledger is
reported as evidence loss; it does not erase the run or suppress an official score.

### Independent QA

For a prospective current-C or consumability claim, an **Independent QA** actor and
session are distinct from the Candidate Builder and the Executor. QA binds the exact
frozen subject revision, Direction, Position, `WorldRef` or closed `WorldSpan`, and the
Position-ledger prefix it actually reviewed. It emits one append-only assessment Fact:
`pass`, `fail`, `blocked`, or `not_assessed`. Builder self-tests and executor success
claims remain ordinary Facts and are never the sole independent support for QA pass.

QA cannot edit the Candidate. A repair creates a new revision with a new assessment;
the failed or blocked assessment remains. QA pass is additional evidence and never
substitutes for, issues, or implies a TraversalReceipt, PathCertificate,
EvidentialWarranty, AuthorityWarranty, authority, benchmark PASS, or current C. In an
experiment, QA timing and visibility are frozen study variables. QA failure does not
authorize deletion, repair beyond the frozen budget, or suppression of scoring.

## 4. Construction procedure

1. **Pin the method.** Select one cataloged method version. The cataloged
   `paper2-current-v2` package is `study_eligible=true` and may be frozen as a research
   input, while `adoption_eligible=false` (and its legacy projection
   `builder_eligible=false`) means it is not approved for operational adoption. This
   prospective draft v3 is not cataloged or study-eligible.
2. **Freeze exogenous inputs.** A runner freezes the task, Direction, fixtures,
   evaluator/scorer, model/runtime constraints, and initial `WorldRef`. Empirical task,
   run, score, and optional-log data remain under `exogenous/`; they are not imported
   into this method paper.
3. **Freeze inputs.** Inventory the Rule and admitted-Fact planes with stable references
   and scope. Pin supporting papers or packages as MethodRefs/knowledge inputs; reject
   implicit promotion into Rules.
4. **Bind Position.** Name the Candidate revision, versioned role-definition Rule,
   separate authority- and liveness-bearing assignment Fact, governed object, and exact
   `WorldRef`. Declare which independent Facts can establish the assignment.
5. **Compile Guide and one result.** The runner freezes the deterministic Guide contract
   over Rules, admitted Facts, role/scope, and warranties before builder dispatch.
   Materialize one Entrance with a bounded consumable instruction, or one typed refusal
   with a durable reason. The Entrance binds its effective Direction to the declared
   Direction-compilation Rule and its canonical allowed-action set to the declared
   action-transition Rule carrying the identical action-set digest; a typed refusal
   binds its governing Rule and evaluated input context. The runner pins the facade,
   interface operation, exact argument digest, lookup-scope identity/digest, and
   single-result bound. A physically co-located contract remains runner-owned and
   read-only; location does not make it builder-writable.
6. **Build the open Candidate.** Give the builder only the declared Entrance and pinned
   MethodRef/knowledge inputs. The builder writes only the explicitly builder-owned
   implementation surface, excluding the frozen Guide contract, and returns completion
   or a blocker. The open proposal remains mutable and uncertifiable.
7. **Freeze the Candidate.** Seal the implementation tree and all declared inputs by
   digest into one semantic closure. From this point, repair creates a new revision;
   freezing alone does not place any scope in C.
8. **Record the Position ledger.** Start the runner-held, hash-linked append-only stream
   before execution and bind every observable transition to the frozen Position,
   Direction, actor/session, and exact world identities. Do not expose the audit stream
   to an agent unless a frozen study declares that visibility as an intervention.
9. **Assess independently.** A distinct Independent QA session reviews the exact frozen
   revision and the ledger prefix available to it, then appends `pass`, `fail`,
   `blocked`, or `not_assessed`. QA cannot edit. Any permitted repair produces a new
   revision and is bounded by a previously frozen budget.
10. **Traverse independently.** A runner or evaluator executes the exact Candidate once
   over a closed `WorldSpan`, records the actual path, freshness checks, bypass status,
   and outcome, and signs or otherwise identifies the receipt issuer.
11. **Certify the demonstrated path.** An independent PathCertificate may make only its
   certificate-covered path provisionally charted. No other Candidate scope is implied.
12. **Establish current consumability.** Under this prospective draft, only scope with
    a QA `pass`, PathCertificate, and live EvidentialWarranty enters current,
    scope-indexed C. QA pass is not a substitute for either record. Consuming the
    actor–role Assignment additionally requires its EvidentialWarranty and
    AuthorityWarranty to be `live`; elsewhere AuthorityWarranty gates only when the
    applicable Rule or tier requires it.
13. **Preserve outcomes.** Passed, failed, blocked, protocol-invalid, and infrastructure
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
  kind or a P/D/E factor.

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
diagnosis may identify unresolved P/D/E or warranty conditions at a critical point.
Its advisory `AssessmentReceipt` binds the claim, Rule, frozen evidence, `WorldRef`,
scope, time, and method version. It is not a Warranty and cannot mint, renew, or revoke
one; authorize action; satisfy a gate; produce PASS; or count as independent
verification.

For a paper-grounded failure diagnosis, classify the invariant that the observed
decision violates rather than the file, module, actor, or message that exposed it:

- **P (Position):** the located actor, role, object, layer, or world state differs from
  the actual governed state.
- **D (Direction):** the frozen objective, acceptance datum, or governing version used
  by the decision is wrong, unauthorized, or silently superseded.
- **E (Entrance):** Position and Direction are adequate, but no legal transition is
  available or the selected transition is not the single declared Entrance.
- **X (execution):** the authorized Entrance is correct, but its action is executed
  incorrectly; X is recorded outside the P/D/E navigation factor set.

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
- newly frozen Direction, Entrance, Position, and `WorldRef`; and
- new implementation and traversal evidence.

Evidence from the prior revision remains historical and cannot be spliced into a
certificate or Warranty for the new revision. A PathCertificate alone reaches only the
provisionally charted path; stale, unknown, or absent warranty state leaves the claimed
scope outside current C. Re-entry is available after any outcome; it is not a backedge
that mutates history.

## 7. Composite mechanisms and proof-obligation order

Physical modules and agents may combine responsibilities. For example, one handoff can
materialize Direction, role-bound Position, and Entrance; the method does not require a
separate component per P/D/E factor. Composition does not collapse propositions:
Position, Direction, Entrance, EvidentialWarranty, and AuthorityWarranty must remain
separately named and their evidence receipts separately checkable.

The proof-obligation order is: pin method and exact world; admit Rules and Facts; bind
role definition and assignment; evaluate Guide to one tagged result; freeze the semantic
closure; traverse one base world; certify the demonstrated path; establish a live
scope-bound EvidentialWarranty; then establish a live AuthorityWarranty where the
assignment, Rule, or tier requires it. A later obligation cannot retroactively satisfy
an earlier one.

## 8. Authority and conflicts

Authority is external to the method. Multiple authority actors are permitted, but each
claim must resolve actor, act, scope, version, provenance, and applicable conflict Rule.
An AI may activate a Rule only inside a pre-authorized envelope and inherits no broader
permission. When a cataloged method paper is adopted, it defines method Rules and a
construction specification. It still never supplies the task-specific Direction or an
external authority grant; this checked-in draft is not adopted for builder use.

## 9. Probability and experimental-unit bridge

For decision opportunity `i`, let
`Z_i = (R_def,i, R_asg,i, WorldRef_i, Datum_i, history_i)`, where the role definition is
a Rule and the assignment is an authority- and liveness-bearing Fact binding. The
relevant joint quantity is `Pr(P_i, D_i, E_i | Z_i)`. If a study factorizes it, only the
conditional chain
`Pr(P_i | Z_i) Pr(D_i | P_i, Z_i) Pr(E_i | P_i, D_i, Z_i)` is admissible; marginal
success rates must not be multiplied, and roles or events must not be treated as
independent samples merely because they are recorded separately.

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
this draft method is ready for adoption.

An Aming Claw Contract handoff remains a useful future composite-mechanism example: one
bound handoff may jointly carry Direction, a role definition plus live assignment, and
one Entrance. That example must pin an exact repository commit and trace cutoff, then
map distinct evidence receipts to each proposition. Its worked-example commit, trace,
GuideReceipt, PathCertificate, and live EvidentialWarranty references remain
`TODO/unresolved`; this paragraph does not claim that Aming Claw currently implements
every abstract obligation above.

## 11. Conformance

A v2 implementation conforms only if it:

- preserves an exact role definition, separate role assignment, and role-bound Position;
- uses a declared deterministic Guide to return exactly one tagged, bounded, consumable
  Entrance or typed refusal, while recognizing that structure alone cannot prove runtime
  determinism;
- binds the Entrance action set and digest to exactly one declared action-transition
  Rule, and pins the declared facade/interface operation, canonical arguments, and
  closed lookup scope at cardinality one;
- uses exact `WorldRef` and closed `WorldSpan` identities;
- keeps Rule and Fact input planes distinct from the Guide control plane and from
  MethodRef/knowledge inputs;
- keeps the four record surfaces separate, recognizes exactly two warranty kinds, and
  keeps optional authority logs non-gating;
- represents open and frozen Candidate states, makes semantic edits create new frozen
  revisions, and completes U → C only through fresh traversal, PathCertificate, and a
  live scope-bound EvidentialWarranty; and
- reports this version as draft, `study_eligible=true`, and
  `adoption_eligible=false`/`builder_eligible=false`.

Conformance does not imply that the method works better than a control. That question
belongs to separately frozen, exogenous studies and repeated independent trials.
