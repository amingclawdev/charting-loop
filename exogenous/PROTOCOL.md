# Exogenous protocol

Freeze a TASKSET, then a STUDY, then one immutable RUN per independent trial. An optional
SCORE receipt binds the exact RUN bytes, task/evaluator identities, WorldRef, subject,
trial, and seed. Corrections create a new run or later version; published core records
are append-only when checked against a base ref.

RUN v2 WorldRefs bind project/run/generation, canonical repository and full immutable
base commit, environment, contiguous RAW ledger prefix, admission receipt/root and Rule,
projector schema/algorithm identity, and derived-state digest. Every field is identity;
timeline presence alone is not an admitted Fact. The subject repository/base and
selected STUDY condition must match the RUN. The RUN environment digest is the
canonical digest of the complete TASKSET environment object. Knowledge condition is exactly `task-only` or
`method-paper`. A v2 method-paper condition is admitted only by an exact local method
catalog match whose entry and immutable STUDY snapshot both say `study_eligible=true`;
scope, theory lineage, provenance catalogs, frozen source commit, method bytes at that
commit, and both eligibility fields must all validate. `adoption_eligible` is
orthogonal, and deprecated `builder_eligible` must equal it. A self-declared flag,
mutable worktree bytes, SCORE, or outcome cannot admit or promote a method.

Every exogenous RUN v2 freezes a closed `measurement_plan`: exact UsageReceipt and
PackageCost schema identities, the ordered construction/guided-execution/
re-entry-revalidation/retry stages, `complete-digest-bound` raw evidence, and required
independent replay. The registry validates this pre-execution declaration but does not
parse runner-local raw evidence or replay bodies. A complete plan is necessary, never
sufficient, for formal comparison; runtime receipts must exact-join the RUN digest.

`RUN.subject.repository_url` is a strict HTTPS identity with a valid host and port and
no credentials, query, fragment, whitespace/control characters, backslash, or dangling
port separator.

The registry validates shapes and immutable joins. It does not prove evaluator honesty,
semantic correctness, causal effect, legitimate authority, direct comparability,
Candidate facade selection, or allowed-action enforcement.

A SCORE is an evaluator receipt and measurement Fact. It never mints a
PathCertificate, either Warranty kind, authority, or eligibility. Optional logs and
attachments are format-free/opaque reminders; presence and format never gate ordinary
participation, validation, or baseline comparison.

Method-index, STUDY, and RUN v1 remain readable under their original shapes. The reader
does not synthesize study/adoption eligibility or a measurement plan for them, so they
remain ineligible for the v2 formal-comparison gate. In method-index v2, `frozen` means
only an immutable study snapshot; the method can retain a draft version identifier and
remain adoption/builder-ineligible.
Optional attachment bodies are never parsed, hashed, listed, or copied into an index.
