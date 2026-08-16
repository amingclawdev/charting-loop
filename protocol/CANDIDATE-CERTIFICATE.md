# Independent Candidate evidence

These records are orthogonal and must have independent owners and immutable bindings.

Before assessment, a prospective runner records an append-only Position ledger. Every
entry is monotonic and hash-linked and binds the observable actor/session, role,
Position, Direction, before/after WorldRef or closed WorldSpan, and content-addressed
action/result references. This ledger is RAW evidence. Its presence or continuity does
not admit a Fact or issue any record below.

- **TraversalReceipt**: exact Candidate, executor, start/end WorldRef, continuous trace,
  freshness, bypass state, and outcome.
- **WorldSpan**: exact endpoints under one project/run/generation/base/environment,
  admission Rule, and projector, with a contiguous same-stream RAW-prefix extension,
  continuous-trace digest, and `closed=true`. Admitted Facts may change between
  endpoints; a base, admission-Rule, or projector change starts a new generation and
  cannot be crossed by one certificate.
- **PathCertificate**: independent judgment that one receipt followed one frozen
  Entrance with fresh evidence and no bypass.
- **EvidentialWarranty**: independent current-consumability assessment for one claim,
  scope, WorldRef, rule version, evidence basis, time, and invalidation predicates.
- **AuthorityWarranty**: independent authorization assessment for an actor–role
  Assignment, act, scope, Rule, WorldRef, provenance, and conflict rule.

A Candidate builder leaves the receipt, certificate, and both warranties absent. A
score does not issue any of them. A
certificate is a historical path witness that makes only its covered path provisionally
charted, not a future-validity, universal-correctness, authority, or causal-effect
claim. Only a live EvidentialWarranty places its covered scope in current C; consuming
an actor–role Assignment also requires its AuthorityWarranty to be live.

An `IndependentQAAssessment` is a separate append-only assessment Fact. Its QA actor and
session differ from Builder and Executor; it binds one frozen subject revision,
Direction, Position, exact world or closed WorldSpan, and the exact Position-ledger
prefix reviewed. Its outcome is `pass`, `fail`, `blocked`, or `not_assessed`. QA cannot
edit the Candidate, and repair creates a new revision. QA pass is required by the
prospective draft-v3 current-C claim but never substitutes for or implies a
TraversalReceipt, PathCertificate, either Warranty, authority, benchmark PASS, or C.
QA failure or missing ledger evidence remains an auditable outcome and does not suppress
official experiment scoring.

The only warranty kinds are `EvidentialWarranty` and `AuthorityWarranty`. Their allowed
states are `live`, `lapsed`, `unknown`, and `not_assessed`. Freshness is a liveness
dimension, not a third warranty. A manual AI assessment is advisory and cannot mint or
renew a warranty.

Re-entry preserves all prior evidence, records the U-state trigger, and opens a new
Candidate revision. It reaches C only after fresh traversal, PathCertificate, and live
scope-bound EvidentialWarranty, with a live AuthorityWarranty before its Assignment is
consumed. Evidence from different revisions cannot be spliced.
