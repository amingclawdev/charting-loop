# Non-normative runtime-evidence profile

`charting-loop/runtime-evidence-bundle/v1` records a synthetic engineering fixture for
the runtime-evidence lifecycle. It is deliberately separate from
`charting-loop/candidate/v2`: its `candidate_projections` are fixture-local projections,
not another Candidate schema or a claim that a real Candidate has been certified.
Appending runtime evidence cannot change Candidate identity, make the method paper
builder-eligible, establish scope-indexed C, or turn an engineering smoke into a
benchmark result.

The bundle contains complete exact `WorldRef` values, frozen Candidate projections, Guide
receipts, traversal receipts, path certificates, EvidentialWarranty and
AuthorityWarranty assessments,
U-state and re-entry records, and a task-only/Corridor parity fixture. Authority
remains an orthogonal optional surface. Missing authority is recorded as
`not_assessed`, never inferred as approval.

Each fixture Candidate projection admits its Position surfaces explicitly: the
`role_definition_id` resolves to one `RoleDefinition` Rule, and the
`assignment_fact_id` resolves to one `ActorRoleAssignment` Fact whose actor, role,
scope, WorldRef, authority source, and liveness match Position. The
EvidentialWarranty joins that admitted assignment to the certificate-covered Direction
evidence; the AuthorityWarranty instead joins the assignment's authority source and
role-governing Rule. An unrelated Direction Rule cannot stand in for that authority
binding.

## Record contracts

- `charting-loop/guide-receipt/v1` binds one Candidate projection, exact WorldRef,
  canonical Rule/Fact/Position inputs and both Warranty references, deterministic
  evaluator identity, request key, and exactly one Entrance or typed refusal.
  Certification-canary receipts may have null Warranty references because they are
  evidence used before issuance; consuming the actor–role Assignment requires both
  referenced Warranties to be `live`.
- `charting-loop/traversal-receipt/v1` binds one Guide receipt, executor, closed
  same-generation contiguous-RAW-prefix `WorldSpan`, ordered trace events, liveness
  checks, bypass state, and outcome.
  A zero-event or cross-base span is invalid.
- `charting-loop/path-certificate/v1` is a separately recorded fixture decision about
  one Candidate projection and one traversal. It requires a fresh, accepted,
  zero-bypass, exact Guide-result-consumption trace. A distinct fixture issuer label
  does not establish governance independence, and the record never proves other paths,
  future worlds, authority, or method efficacy.
- `charting-loop/evidential-warranty/v1` is a separately recorded fixture assessment of
  one admitted actor–role Assignment's factual/lifecycle validity and one
  certificate-covered claim/scope at a WorldRef. `live` makes only that covered scope
  current; `lapsed`, `unknown`, and `not_assessed` do not. A later assessment is
  appended rather than rewriting an earlier one.
- `charting-loop/authority-warranty/v1` is the second and only other Warranty kind. It
  independently binds the actor–role Assignment, governing Rule, actor, act, scope, and
  WorldRef. It uses the same four states. Missing optional authority logs never mint or
  gate this record.

## Required fixture sequence

The service-plan example validates the shape and joins of this synthetic sequence:

1. an advisory U-state diagnosis opens and freezes Candidate `r0` at `W0`;
2. a canary consumes the exact Guide result; fresh traversal and fixture
   PathCertificate precede independent live EvidentialWarranty and AuthorityWarranty
   records that project a synthetic `C0` state and consumable Assignment;
3. runtime Guide consumption returns one bounded stage-1 Entrance at `W0`;
4. the declared checkpoint extends the same ledger prefix from `W0` to `W1` without
   changing the base commit;
5. a new `lapsed` EvidentialWarranty assessment is appended and `r0` returns the typed
   refusal `stale_world_ref` before another mutation;
6. re-entry opens and freezes Candidate projection `r1`; new canary, traversal,
   certificate, and live EvidentialWarranty plus AuthorityWarranty assessments project
   synthetic `C1`; and
7. the runtime Guide returns one bounded stage-2 Entrance and the shared evaluator
   checks the task output.

The default task-only and Corridor arms are deterministic parity projections from one
common evaluator invocation; they are not two independent agent runs. `TASK_PASS` is
common to both projections. `CORRIDOR_E2E_PASS` is treatment-only and never contributes
to the task score. The separately stored Docker pair is a digest-bound, sanitized,
runner-reported observation rather than part of this schema's certification chain.

Structural validation proves only these declared bytes and joins. It does not establish
that the method outperforms a control, that a public evaluator is a hidden oracle, that
an authority is legitimate, or that the same behavior generalizes beyond this fixture.

## Public observable-result derivative

The public result evidence schemas documented in `MANIFEST-SCHEMA.md` are a separate
post-hoc derivative, not an extension of this synthetic runtime bundle and not a new
gate. A derivative may bind contemporaneous observable command receipts to a frozen
service revision, full-log digest, writeback digests, pre-score image, and official
evaluator receipt. It may not manufacture a missing event, infer hidden reasoning, or
upgrade a digest-only source to independently verified evidence.

When the historical STUDY/RUN shape differs from what actually executed, the public
result may add `charting-loop/public-execution-amendment/v1`; it must set
`frozen_study_overwritten=false`. Missing timing, usage, seed, retry, or predecessor
receipts remain typed unavailable/waived fields. The companion
`charting-loop/public-attempt-disposition-ledger/v1` records counted and invalid
attempts without manufacturing a replacement RUN.

The safe-public receipt keeps task identifiers and mechanism-relevant outcomes. It
removes subscription authentication, credential values, host-private paths, hidden
reasoning, and hidden tests; credential-bearing full logs remain controlled and
content-addressed. This profile supports audit of the observed sequence and custody
joins. It does not prove that Corridor caused an outcome, certify a Candidate, mint a
Warranty, or generalize a one-task matched comparison.

## Prospective Position-ledger and QA projection

Prospective draft-v3 runners may append `charting-loop/position-ledger-entry/v1` records
and `charting-loop/independent-qa-assessment/v1` records outside the frozen Candidate.
This section is a runner-facing projection; the current synthetic bundle remains v1 and
does not silently gain required fields.

A Position-ledger entry contains a stream id, positive monotonic sequence, previous
entry digest (null only at sequence 1), canonical entry digest, observed time,
actor/session and role ids, Position and Direction refs/digests, exact before/after
WorldRef refs or one closed WorldSpan digest, and bounded content-addressed action,
result, and artifact refs. Corrections append. The ledger prefix is runner-held,
agent-invisible unless a frozen study declares otherwise, and identical in capture
policy across matched arms. It may reference observable logs, databases, files, service
receipts, and evaluator output; it excludes credentials, hidden reasoning, hidden tests,
and verifier bodies.

An Independent-QA assessment contains its distinct QA actor/session, frozen subject
revision and semantic digest, Direction and Position digests, exact world or closed-span
digest, reviewed ledger stream/sequence/prefix digest, bounded public QA instruction,
outcome (`pass`, `fail`, `blocked`, or `not_assessed`), findings, observed time, and its
own canonical digest. The issuer cannot be the Builder or Executor. The assessment is
an additional Fact only. It never issues or implies a GuideReceipt, TraversalReceipt,
PathCertificate, EvidentialWarranty, AuthorityWarranty, authority, benchmark PASS, or
current C. Missing or discontinuous ledger evidence yields `blocked` or `not_assessed`;
it never deletes a run or prevents the frozen evaluator from scoring it.

## CL-014 manual acceptance profile

`charting-loop/ai-acceptance-record/v1` is a runner-local evidence package for a bounded
real-AI acceptance pilot. It is not part of Candidate identity, not an exogenous index,
and not a formal comparison or benchmark result. Its authoritative inputs are supplied
out of band to the validator: successful full STUDY/catalog and RUN validation facts,
exact raw-byte digests, the evidence root, and a separately invoked replay verifier
receipt. Booleans copied from an input manifest, RUN index, or the record itself do not
establish those facts. Each RUN fact also pins the canonical digest of its complete
record binding, so changing a projected runner, task, assignment, condition, or nuisance
field breaks the join to the validated source.

The record contains exact treatment/control RUN bindings, the selected STUDY MethodRef
and catalog eligibility pin, the canonical measurement plan, per-attempt usage receipts
and derived package costs, raw evidence, all attempts, selected matched pairs, an
independent replay projection, and the derived gate. Failed and repaired attempts are
append-only peers: repair ancestry does not delete or relabel the failed observation.
Builder construction and treatment execution remain distinct attempts, sessions,
invocations, receipts, and raw artifacts. For each selected pair they bind the same
completed treatment RUN; `run_bindings` deduplicates that RUN and the distinct control
RUN. Builder evidence is not disguised as a treatment attempt merely to satisfy a join.

Raw evidence paths are normalized relative paths resolved beneath an explicit evidence
root. The validator rejects absolute paths, traversal, symlinks, missing/non-regular
files, digest mismatches, incomplete coverage, and records whose replay verifier shares
the assembling runner's identity, session, or invocation. Replay success is accepted
only when the separate receipt binds the complete canonical payload and actual evidence
digests.

A pair is clean only when its builder, treatment, and control attempts exist, their
complete append-only repair lineages use fresh sessions and RUNs not reused by another
clean pair, and the selected attempts have successful outcomes. Builder
and treatment share one completed corridor/method-paper RUN but remain separate
attempts; control uses a distinct completed task-only/task-only RUN. RUNs and attempts
cannot be reused across selected pairs. The paired RUNs bind one STUDY and task plus
equal closed runtime/evaluator/trial/seed conditions plus a canonical WorldRef
comparison projection that excludes only the necessarily distinct RUN id. That
projection is neither a WorldRef nor a WorldSpan. Builder/treatment
Candidate and common-condition digests equal the pair; control Candidate is null. Each
non-control Candidate digest must equal an owned `candidate-artifact` file-byte digest,
while control may not own that evidence kind. The treatment condition equals the exact
MethodBinding condition. The pilot gate requires at least two distinct clean pairs,
successful trusted validation, and successful independent replay. The gate is derived,
never caller-declared. Even when it opens, it fixes these
claim fields:

- `instrumented_acceptance_pilot_ready: true` means only that the declared bounded pilot
  evidence is complete enough for the next instrumented acceptance step;
- `formal_comparison_ready`, `benchmark_result`, `causal_claim_allowed`, and
  `adoption_claim_allowed` remain `false`; and
- `authority_warranty_state` remains `not_assessed`.

The public helper uses the closed operator-input schema
`charting-loop/acceptance-input/v1` and requires an explicit manual confirmation. It
does not run a model, open a network connection, synthesize a session, retry an attempt,
or overwrite an existing acceptance record.

### UsageReceipt and PackageCost

Each attempt has exactly one `charting-loop/usage-receipt/v1`. A receipt binds the exact
RUN id and raw-byte digest, session and attempt ids, and canonical measurement-plan
digest. Its ordered stages are:

1. `construction`;
2. `guided_execution`;
3. `reentry_revalidation`; and
4. one or more `retry` records, including an explicit `not_applicable` retry when none
   occurred.

The first three stages appear exactly once and in that order. Further records are all
`retry`. Within one UsageReceipt, every stage-record `stage_receipt_id` and stage-record
`attempt_id` is unique; top-level UsageReceipt `receipt_id` and attempt coverage are
unique across the acceptance package. A retry names a core-stage attempt id in the same
receipt and the exact corresponding `retry_of_stage`; core stages carry null retry
ancestry. `assessment_status` is `measured`, `not_assessed`, or `not_applicable`, but
the three core stages are always applicable: `not_applicable` is reserved for the one
and only no-retry sentinel and cannot coexist with another retry record. All six usage
metrics—input tokens, cached input tokens, output tokens,
reasoning output tokens, wall time milliseconds, and tool calls—are non-negative JSON
integers when measured; booleans are rejected even though Python treats them as integer
subclasses. Canonical evidence additionally caps each integer at 4096 bits so hostile
JSON cannot escape the fail-closed validator through integer serialization limits.
Every metric is null when not measured or not applicable. Cached input is a
subset of input tokens, and reasoning output is a subset of output tokens; neither is an
additive extra charge.

`charting-loop/package-cost/v1` is derived from the exact UsageReceipt and cannot be
declared independently. Its primary `construction_plus_execution` view counts each
applicable stage exactly once, including rooted retries, and is null with explicit
missing stages unless every required applicable measurement exists. Secondary views are
marked non-additive. `execution_only` projects guided execution, re-entry validation,
and their retries. `amortized` combines the same measured construction and execution
quantities over a positive integer reuse count using an exact numerator/denominator;
the acceptance package uses the default `assumed_reuses: 1` derivation. Neither
secondary view may be added to the primary view. Any applicable `not_assessed` stage
makes usage incomplete and keeps the pilot gate closed; an explicit `not_applicable`
retry is the required no-retry declaration, not proof that no retry occurred.

For each clean pair the validator derives two non-overlapping reporting buckets.
`corridor_e2e` is the full builder plus treatment lineage, including superseded failed
attempts and every construction, guided-execution, re-entry, and retry measurement.
`control_task` is the full selected control lineage. This is the primary comparison
cost boundary. If any lineage measurement is incomplete, its bucket carries null totals,
`complete: false`, and explicit missing-stage identifiers rather than a partial number
that looks complete. The non-additive `execution_only` view cannot replace total Corridor
cost; it exists only for reuse and amortization analysis. Cached-input and reasoning-
output figures remain subset detail and are never added again.

### Independent replay closure

The replay receipt comes from a separate verifier identity, session, and invocation.
Its payload digest closes over the record schema and complete canonical acceptance
input: source-validation digest; exact RUN bindings; MethodRef/catalog binding;
measurement plan; raw
artifact paths and actual byte digests; attempt ids, session provenance, repair ancestry,
metadata and outcomes; UsageReceipts and derived PackageCosts; Candidate and common-
condition joins; and every matched-pair selection. It deliberately excludes the replay
projection itself and the derived gate. A separate outcome digest covers sorted attempt
outcomes and derived clean-pair ids. Coverage of only artifact or attempt ids is
insufficient. The runtime recomputes these digests and accepts a positive replay verdict
only when the out-of-band verifier receipt binds them exactly.

Manual confirmation and distinct manifest session strings are not freshness evidence.
Opening the trusted pilot gate requires a distinct actual
`charting-loop/ai-session-receipt/v1` file for every attempt. The receipt binds exact
attempt/session/invocation/agent fields, and its issuer identity/session/invocation must
differ from assembler, agent, and RUN-runner identities. These byte-bound independent
declarations corroborate provenance but are not signed authentication or proof of
freshness. Without them the record remains structurally inspectable but
`instrumented_acceptance_pilot_ready` is false.

Accordingly, this v1 profile supports an auditable engineering acceptance gate. It
does not establish real-world authority, defeat a dishonest operator, or upgrade the
result to a formal comparison.
