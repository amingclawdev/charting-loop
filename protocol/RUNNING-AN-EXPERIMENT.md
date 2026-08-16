# Running a neutral experiment

This is runner/evaluator guidance, not builder- or task-agent-facing method text.

1. Freeze TASKSET and STUDY manifests before any builder or task session. When the
   TASKSET uses `charting-loop/exogenous-taskset/v2`, also freeze the task's
   `TASK-CONSTRAINTS.json`; its digest is part of the ordered task-list identity.
2. Freeze the builder-visible input manifest, exact official task bytes, public
   environment source, evaluator identity, model/runtime configuration, resources,
   egress policy, assignment, seed, retry policy, and analysis intent. Do not expose
   solutions, hidden tests, verifier bodies, prior outcomes, governance instructions,
   or private evaluator data to builder or task agents.
3. Create immutable RUN records before execution. Resolve repositories and artifacts
   using full commits, trees, content digests, and exact WorldRefs; branch names are
   locators only. Build the runtime image from the frozen source and pin its observed
   digest in each RUN.
4. Apply only the intervention declared by the frozen STUDY. Candidate qualification,
   traversal, PathCertificate, EvidentialWarranty, AuthorityWarranty, governance
   receipts, and independent replay are not admission or scoring prerequisites unless
   that STUDY explicitly declares one of them as the measured intervention.
5. For a task-conditioned Corridor comparison, let a fresh builder choose the branch
   service implementation freely from the frozen Paper 2 research input, public task,
   public environment, and neutral objective. Freeze the resulting service commit and
   tree before starting either task arm.
6. Run treatment and control in fresh, independent environments. Each arm has a fresh
   Worker plus a distinct fresh Independent QA. Match byte-identical official task
   instructions, model, tools, runtime limits, evaluator, retry and seed policies, QA
   instruction, QA timing, permissions, budget, feedback visibility, and exactly one
   bounded Worker repair opportunity. Treatment alone receives service access and the
   frozen minimal consume instruction. A failed or absent service call is an observed
   result, not a reason to suppress official scoring.
   Freeze this topology and ordering in `charting-loop/task-constraint-datum/v2`;
   historical v1 constraints retain their no-repair semantics.
7. Capture a runner-held, append-only Position ledger invisibly and identically for both
   arms. Bind each entry to sequence, previous digest, actor/session, Position,
   Direction, exact world transition, and observable action/result references. Give QA
   the frozen public task, exact candidate result, and permitted observable evidence;
   never hidden tests, verifier bodies, prior scores, or task-specific hints. QA appends
   `pass`, `fail`, `blocked`, or `not_assessed`, cannot edit, and cannot mint PASS,
   certificates, warranties, authority, or C. Ledger presence alone admits nothing.
8. Return the matched visible QA assessment to each original Worker for its one bounded
   repair turn, freeze the resulting revision even when unchanged or failed, and then
   run the official evaluator. After that round, do not qualify, repair, tune, replace,
   or add task guidance to the service or either arm. A ledger or QA failure is an
   auditable result, not a reason to suppress scoring. Shared
   infrastructure readiness checks may run only when identical for both arms and when
   they do not inspect or execute the treatment service.
9. Preserve every passed, failed, blocked, invalid, unscored, and infrastructure-error
   run. An evaluator may append a SCORE receipt bound to the exact RUN, task,
   evaluator, environment, subject, trial, and seed. SCORE is a measurement Fact, not
   a warranty, certificate, authority claim, or causal conclusion.
10. Start experiment-specific audit only after official scoring. Preserve observable
   agent/runner/tool/service logs, exact commits and trees, pre-score container/rootfs
   identity, Position-ledger entries and QA assessments, persistent-file manifests, and
   database files, dumps, transaction logs, or named-volume identities when present.
   Keep scored trees immutable and add audit
   material only in descendant or separate result branches.
11. Never publish credentials, hidden reasoning, unrelated account history, hidden
    benchmark material, or private/unlicensed data. Validate deterministic indexes and
    append-only history with `--base-ref` before publication.

Volunteer or single-pair trials are descriptive. Confirmatory comparison additionally
requires a prospectively frozen assignment and analysis plan, repeated independent
trials, and matched conditions. Those requirements affect the strength of the research
claim; they do not authorize repair beyond the prospectively matched bounded QA round
or deletion of inconvenient outcomes.

`frozen` in method-index v2 means only that exact method bytes are pinned as a research
input. The current study package is `paper2-current-v2` at
`c500c07a2138212e7ddc9ea77ff2a20c379c6492`, with METHOD digest
`sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905`
and SCOPE-DATUM digest
`sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307`.
It is `study_eligible=true`, `adoption_eligible=false`, and
`builder_eligible=false`. Freezing is not adoption, operational authority, publication
maturity, a warranty, or production approval.
