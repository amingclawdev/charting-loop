# Scope datum for Charting Loop corridor method v8

This non-normative datum freezes the source and judgment boundary used to draft
`METHOD.md`.

- Primary published theory source: *The Charting Loop: A Four-Layer Probabilistic
  Theory of Uncharted-to-Charted Work in Agent Systems*, version v1,
  DOI `10.5281/zenodo.21844624`.
- Exact published representation: `paper/charting-loop-zenodo.pdf` at source commit
  `cf5ac479e208a2401b9358527d58df48e22c0670`,
  `sha256:f557af476441e814e4d86041969c18fde2299a6a47d28658bdeb8cec2d7296c1`.
- Consulted drafting snapshot: `internal-v5-arxiv-initial` at commit
  `e0dd3a466654011ecf0cb6d8f32e9cbbc4c3cc99`. It is retained only as non-primary
  drafting provenance and is not a public theory dependency of this method version.
- Repository design cutoff: 2026-08-17.
- Experience boundary: checked-in v1 protocol plus the ratified CL-008 through CL-015
  architecture decisions and their cataloged claims, followed by generic reviews of
  executor self-report versus independently replayable observation, task-acceptance
  omission, and authority-layer/Gate-chain failure shapes. Aming Claw is a practice
  source that helped expose those shapes; it is not a reference architecture or
  evidence that the method works. No task identifier, score, failure string, hidden
  test, repair hint, or empirical outcome is imported into builder-visible method text.

Draft v2 added repository-specific construction decisions—Rule/Fact input planes, a
deterministic Guide control plane, separate role definition and assignment, one bounded
tagged semantic Entrance or typed refusal, open/frozen Candidate states, complete
WorldRef identity and same-generation RAW-prefix WorldSpan closure, exactly two
warranty kinds with optional non-gating authority logs, scope-indexed U → C re-entry,
composite mechanisms, and a conditional probability bridge. The
catalog marks which claims are derived from the theory and which are new method
decisions. Operational P/D/E construction and failure diagnosis belong to this method;
estimator definitions, confidence intervals, power, sample size, and experimental
results belong to Paper 3. Those method-level mappings do not alone trigger a Theory v2.
A future theory release requires a material change to definitions, factorization,
scope, predictions, or falsifiers.

Draft v3 added two method-level evidence decisions without revising Theory
v1: a runner-held hash-linked append-only Position ledger, and an Independent QA role
whose assessment is distinct from builder and executor self-report. The ledger is RAW
observation and QA is an additional assessment Fact; neither can mint a certificate,
Warranty, authority, PASS, or current C. Experiment-facing QA visibility, timing, repair
budget, matched-arm topology, and scoring order remain protocol variables. These bytes
are deliberately un-cataloged; the frozen `paper2-current-v2` representation and its
source/scope digests remain unchanged.

Version v4 adds a task acceptance ledger to Direction and strengthens
Corridor-assisted Independent QA. The ledger atomizes every public normative task
clause with a source reference, scope, decision Rule, and typed relationship, while
keeping definition, applicability, coverage, and assessment states distinct. QA uses
the same frozen Corridor as the Worker but independently re-reads the public task
sources, accounts for the exact acceptance-ID set, and treats witness closure as
narrower than whole-task closure. Missing or incomplete acceptance makes internal
closure `blocked` or `not_assessed`; it does not gate execution or the external
evaluator.

Version v4 also makes an existing architectural implication explicit: Rule is the
normative authority layer, while an operational Contract is only a versioned container
or binding for a Rule closure. Conformance therefore requires Rule consistency,
Rule-transition coherence, Gate-to-Rule conformance, and whole Gate-chain coherence.
A Gate may check applicable Rules against admitted Facts but cannot create authority,
and Gate, Guide, and Entrance projections for one decision must share the same Rule
closure, Fact root, role/scope, `WorldRef`, warranty state, and verdict. These are
method-level proof obligations for a profile that declares Gates, not a requirement
that a benchmark Builder install blocking runtime governance.

Version v4 also states the architecture boundary explicitly. Its named objects are
semantic roles and proof obligations, not mandatory services, agents, modules, files,
schema fields, or deployment topology. Facade/interface fields and Git commit identity
belong to a software/Git projection; other profiles may use prompts, checklists, rule
tables, validators, workflow engines, database snapshots, API versions, device states,
or other canonically frozen equivalents. Construction experiments use a nonblocking
profile so that internal `blocked` or `not_assessed` outcomes remain observable without
changing external execution. Long-lived governed systems may add Gates only with Rule
authority, Fact selectors, projection conformance, whole-chain coherence, and the
linear-unlock recovery rule.

Version v5 adds an implementation-neutral execution projection prompted by a fresh
benchmark construction failure shape: a Builder could enumerate many acceptance
items yet spend most of its remaining budget rebuilding generic domain mechanics,
while Worker and QA lacked a shared current-task projection. The method now permits an
immutable work backlog compiled from acceptance IDs, task-neutral reusable capability
modules frozen before scored task exposure, and runner-owned row events projected into
the same advisory current-row Guide and reminders for Worker and QA. A work row remains
a projection, a capability remains mechanics, and a reminder remains advisory; none is
a new Rule, Fact, Gate, authority source, task answer, or proof of acceptance.

The task identifier, task bytes, binary offsets or opcodes, verifier material, model
transcripts, score, and candidate repair remain outside these method bytes. Only the
abstract failure shape—acceptance without executable decomposition and repeated
reconstruction of reusable mechanics—informed v5. The bundled binary capability pack
is generic and read-only: it inventories ELF identity, reports changed ranges, and
binds shell-free replay inputs without encoding any task-specific patch.

Version v6 corrects a runtime allocation failure at the method/profile boundary. A
bounded task now has one total deadline shared by Builder, Worker, QA, repair, and
closure; those names are logical handoffs rather than independent hard budgets. The
Worker freezes the first complete scorable task-state revision and every verified
improvement. QA freezes assessments separately and remains advisory. At normal return
or total-deadline exhaustion, the runner restores the newest verified Worker revision
before external scoring; incomplete later work cannot displace it. Snapshot custody is
not a Gate, acceptance result, certificate, or authority source, and restoration may
not expand the Worker's operating-system authority.

Only the abstract failure shape informed v6: a phase-local cutoff can destroy a viable
in-progress submission even when the enclosing task still has time, and an incomplete
later repair can overwrite a previously scorable state. No task identifier, task
bytes, solution, verifier material, score, transcript, or snapshot payload is imported
into these method bytes. Deadline lengths, finalization reserve, output paths, model,
runtime, and scorer remain protocol variables frozen by each study.

Version v7 narrows the custody claim and hardens its non-security correctness
obligations. In the cooperative-agent experiment profile, Worker and QA role values are
namespaces and provenance labels, not credentials, accounts, ACLs, or permission Gates;
the agents self-obey their declared write boundaries. This is an explicit trust
boundary, not an adversarial-role isolation claim. The selected latest reference must
match its manifest role, sequence, snapshot ID, and tree digest exactly. File restore
prevalidates every declared target, blob, identity, mode, and staging write before the
first destination mutation, then performs per-file atomic replacement. It does not
claim a generic whole-set or cross-filesystem atomic transaction, and a commit-phase
failure must expose any already-restored prefix without reporting success.

Only the abstract review findings informed v7: a syntactically valid latest reference
can disagree with its manifest, multi-file validation interleaved with mutation can
change an earlier target before a later invalid target is discovered, and authorization
machinery would add an experimental Gate outside the cooperative-role threat model. No
task identifier, task bytes, solution, verifier material, score, transcript, snapshot
payload, credential, or subscription information is imported into these method bytes.

Version v8 resolves a method-level modeling ambiguity without revising published
Theory v1. The method now treats Position and Direction as its two stored navigation
variables: Position is a content-addressed checkpoint over admitted Facts and the exact
world, while effective Direction is the deterministic projection of the frozen
objective and applicable Rule closure at that checkpoint. Entrance is the tagged Guide
result for one transition, not a third stored state variable or authority source. The
published theory's P/D/E vocabulary and conditional probability bridge remain cited as
provenance; any change to theory definitions, predictions, or falsifiers is deferred to
a separately proposed and frozen theory version.

Version v8 also strengthens task acceptance from textual clause coverage to declared
behavioral coverage. Universal, negative, stateful, temporal, and coupled Rules name
their finite partitions, boundary classes, relevant interactions or transition orders,
applicable metamorphic relations, and unresolved remainder. High-risk Rules require an
independently selected source-grounded QA probe when feasible; otherwise QA reports
`blocked` or `not_assessed`. These remain non-gating construction-experiment
obligations. The abstract review finding was that replaying representative positive
examples can preserve a wrong Direction projection when negative or interacting states
were never represented. No task identifier, task bytes, solution, verifier material,
score, transcript, or repair content is imported into v8.

This amendment was prompted by a post-hoc review of one excluded benchmark smoke run
in which a genuine QA witness was repaired but a different public acceptance
dimension remained omitted. Only that abstract failure shape informed the method.
The task identifier, task files, hidden-verifier material, solution details, score,
role transcripts, and repair content remain in git-ignored exogenous custody and are
not imported into these builder-visible bytes. The observation does not retroactively
change the frozen v2 method, the earlier matched study, or the already-completed smoke
run. Version v4 is frozen as a separate, exactly addressed research package; the v2
package and its catalog identities remain unchanged. Study eligibility is a catalog
property of exact bytes and never implies operational adoption eligibility.
