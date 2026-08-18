# Charting Loop corridor method and experiment substrate

This repository separates a draft corridor method from the empirical data used to test
it. Current status: **public release live and replication-invitation ready**. Six
sanitized arm summaries from three matched attempts on `production-planning` are
published through immutable result branches and the machine release registry. A
separate immutable public-summary branch records an official 19/19
`ico-path-patch` engineering run whose complete Method conformance was not established.
The public index therefore covers two distinct tasks, but only the first has a matched
comparison. The second is a same-task adaptive recovery after verifier feedback, not
an independent reproduction. Structural validation works, but no aggregate, causal,
multi-task-efficacy, benchmark-wide, production,
semantic-correctness, leaderboard, or real-world-authority result has been established.

## Read the theory

The method and experiment substrate build on Ying Zhang's *The Charting Loop: A
Four-Layer Probabilistic Theory of Uncharted-to-Charted Work in Agent Systems*. Read
the exact published v1 record at
[Zenodo (DOI 10.5281/zenodo.21844624)](https://doi.org/10.5281/zenodo.21844624).
`CITATION.cff` records this DOI as a related theory reference; it is not the DOI of
this software repository.

## Replicate the method

The preferred public test is method transfer: freeze an unseen multi-step task and an
exact method package, let a fresh builder construct a task-conditioned Corridor, then
compare matched Worker-plus-independent-QA arms with and without that Corridor. Do not
download a same-task solution service and call that method replication.

Choose the page for your audience:

- **Human invitation:** [`docs/REPLICATION-INVITATION.md`](docs/REPLICATION-INVITATION.md)
  explains the motivation, hypothesis, Corridor, and simple matched design.
- **Human result index:**
  [`docs/EXPERIMENT-RESULTS.md`](docs/EXPERIMENT-RESULTS.md) lists one row per distinct
  benchmark task and keeps repeated attempts grouped under that task.
- **Human task results:**
  [`docs/PRODUCTION-PLANNING-RESULT.md`](docs/PRODUCTION-PLANNING-RESULT.md) explains the
  matched-arm evidence, while
  [`docs/ICO-PATH-PATCH-RESULT.md`](docs/ICO-PATH-PATCH-RESULT.md) records the separate
  full-method smoke sequence, its 15/19 partial score, the protocol/SDK adjustments,
  and its publication boundary.
- **Post-hoc AI result analysis:**
  [`docs/AI-RESULT-ANALYSIS-RUNBOOK.md`](docs/AI-RESULT-ANALYSIS-RUNBOOK.md) contains the
  step-by-step case-analysis procedure and complete copy-ready prompts. It is a reading
  aid for completed results, not experimental builder, Worker, QA, or runner context.
- **AI/operator experiment runbook:**
  [`docs/AI-REPLICATION-RUNBOOK.md`](docs/AI-REPLICATION-RUNBOOK.md) indexes the detailed
  prospective execution sequence. It is runner context, not experimental builder,
  Worker, or QA context.
- **Authoritative runner protocol:**
  [`protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md`](protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT-V2.md)
  controls the prospective experiment.
- **Human release checklist:**
  [`docs/PUBLIC-RELEASE-CHECKLIST.md`](docs/PUBLIC-RELEASE-CHECKLIST.md) governs review
  and publication of an exact ref. Machine success does not authorize a push.

Public releases contain summaries and digests by default; solution code, writeback
SQL, databases, detailed logs, raw sessions, trajectories, hidden evaluator material,
and internal Git history remain embargoed or restricted under
[`protocol/PUBLIC-RELEASE-BRANCHES.md`](protocol/PUBLIC-RELEASE-BRANCHES.md).

The public repository is
[amingclawdev/charting-loop](https://github.com/amingclawdev/charting-loop).

## Authority map

- `method-paper/METHOD.md` is the sole normative method source.
- `method-paper/VERSIONS.json` catalogs it as `draft` and
  `builder_eligible=false`.
- `catalog/` records author provenance and claim/source relationships.
- `protocol/` contains runner-facing data contracts; it does not add method rules.
- `templates/corridor/` is the minimal v2 Candidate skeleton.
- `templates/run/` is the neutral runner/evaluator envelope.
- `demos/` contains non-normative, subscription-free engineering examples.
- `exogenous/` holds tasksets, studies, runs, scores, and optional opaque evidence.
- `templates/legacy-corridor-v1/` preserves the complete v1 skeleton.
- `registry/` remains the legacy v1 public index.
- `tools/corridor_registry.py` preserves that v1 path while also validating the v2
  Candidate/template projections.

The method separates Rule and Fact input planes from a deterministic Guide control
plane. Guide evaluates exact Rules, admitted Facts, complete Position, and both
Warranty references to return one tagged bounded, consumable Entrance or typed refusal.
Supporting papers and
packages are pinned MethodRefs/knowledge inputs, not Guide. Position binds a versioned
role definition and a separate holder assignment admitted through the Fact plane. The
runner freezes the Guide contract before builder dispatch, even when that read-only
contract is physically co-located with implementation bytes. Effective Direction is
joined to a declared Rule rather than injected beside the Guide result. Complete exact
WorldRef endpoints and same-generation contiguous-RAW-prefix WorldSpan evidence keep
traversal receipt, path certificate, EvidentialWarranty, and AuthorityWarranty
orthogonal. Authority logs are optional and non-gating; missing means `not_assessed` or
`unknown`, never approved.

Repair does not rewrite a Candidate. A blocked, failed, stale, or superseded state U
opens a new Candidate revision. It re-enters scope-indexed C only after the new revision
is frozen, freshly traversed, independently path-certified, and covered by a live
EvidentialWarranty; creating or freezing the proposal is not C.
Consuming an actor–role Assignment additionally requires its independently issued
AuthorityWarranty to be live.

## Validate the repository

```sh
python3 demos/service-plan-corridor-e2e/run_demo.py --check
python3 -m unittest discover -s tests -v
python3 tools/corridor_registry.py validate-theory
python3 tools/corridor_registry.py validate-task
python3 tools/corridor_registry.py validate-method
python3 tools/corridor_registry.py validate-corridor templates/corridor --allow-template
python3 tools/corridor_registry.py validate-corridor templates/legacy-corridor-v1 --allow-template
python3 tools/corridor_registry.py validate-registry
python3 tools/corridor_registry.py build-index --check
python3 tools/exogenous_registry.py validate-run templates/run --allow-template
python3 tools/exogenous_registry.py validate-registry
python3 tools/exogenous_registry.py build-index --check
python3 tools/public_release.py validate-registry
python3 tools/public_release.py summarize-registry
```

CI supplies the pull-request or push base commit to both exogenous registry commands so
append-only history is enforced. Local publication checks should likewise pass
`--base-ref <base-sha>`.

The history scanner is a public-ref check, not a generic internal-main validator. Run
`public_release.py check` against the separately curated no-parent public root described
in `docs/PUBLIC-RELEASE-CHECKLIST.md`; it intentionally rejects inherited internal
history such as deleted Finder metadata.

The v2 Candidate template is intentionally open, non-indexable, template-only, and
structurally validated while the method is builder-ineligible. Structural validation
checks declared contracts and closed joins; it cannot prove that a runtime Guide is
deterministic. The separate
[`service-plan-corridor-e2e`](demos/service-plan-corridor-e2e/README.md) demo validates
synthetic consume-time GuideReceipt, traversal, certificate, and warranty-record joins
without unlocking the Candidate profile, changing Candidate identity, or claiming that
method-level C has been established.
The exogenous registry can still record neutral task-only and external-system trials.
Optional attachment bodies and `exogenous/local/` are never parsed or indexed.
Candidate `optional-evidence/` is pointer-only; raw optional bytes remain exogenous.

See `MIGRATION-v1-v2.md` for the compatibility boundary and `CONTRIBUTING.md` for
publication rules. Project-authored content is available under Apache License 2.0; see
`LICENSE`, `THIRD_PARTY_NOTICES.md`, and `CITATION.cff` for the license, vendored-input
provenance, and citation metadata.
