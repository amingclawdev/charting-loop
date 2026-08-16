# Scope datum for prospective draft v4

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
- Repository design cutoff: 2026-08-16.
- Experience boundary: checked-in v1 protocol plus the ratified CL-008 through CL-015
  architecture decisions and their cataloged claims, followed by a generic review of
  the distinction between executor self-report, independently replayable observation,
  and independent assessment. No task identifier, score, failure string, test name,
  repair hint, or empirical outcome is imported into builder-visible method text.

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

Prospective draft v3 adds two method-level evidence decisions without revising Theory
v1: a runner-held hash-linked append-only Position ledger, and an Independent QA role
whose assessment is distinct from builder and executor self-report. The ledger is RAW
observation and QA is an additional assessment Fact; neither can mint a certificate,
Warranty, authority, PASS, or current C. Experiment-facing QA visibility, timing, repair
budget, matched-arm topology, and scoring order remain protocol variables. These bytes
are deliberately un-cataloged; the frozen `paper2-current-v2` representation and its
source/scope digests remain unchanged.

Prospective draft v4 adds a task acceptance ledger to Direction and strengthens
Corridor-assisted Independent QA. The ledger atomizes every public normative task
clause with a source reference, scope, decision Rule, and typed relationship, while
keeping definition, applicability, coverage, and assessment states distinct. QA uses
the same frozen Corridor as the Worker but independently re-reads the public task
sources, accounts for the exact acceptance-ID set, and treats witness closure as
narrower than whole-task closure. Missing or incomplete acceptance makes internal
closure `blocked` or `not_assessed`; it does not gate execution or the external
evaluator.

This amendment was prompted by a post-hoc review of one excluded benchmark smoke run
in which a genuine QA witness was repaired but a different public acceptance
dimension remained omitted. Only that abstract failure shape informed the method.
The task identifier, task files, hidden-verifier material, solution details, score,
role transcripts, and repair content remain in git-ignored exogenous custody and are
not imported into these builder-visible bytes. The observation does not retroactively
change the frozen v2 method, the earlier matched study, or the already-completed smoke
run. These v4 bytes are deliberately un-cataloged and not study-eligible.
