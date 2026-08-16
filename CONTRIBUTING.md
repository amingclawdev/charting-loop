# Contributing

Protocol/code changes and immutable exogenous outcomes—including failed, blocked,
invalid, and unscored runs—are welcome.

For a new trial:

1. Freeze a canonical TASKSET and STUDY.
2. Add one immutable `exogenous/runs/<run-id>/RUN.json`; add `SCORE.json` only when
   an evaluator has issued it.
3. Use full commits and SHA-256 digests. Branches are hints, never identity.
4. Keep raw or private material in ignored `exogenous/local/`. Public attachments are
   optional, require consent, and are intentionally opaque to the validator.
5. Never commit credentials, hidden reasoning, unrelated account history, or unlicensed
   third-party transcripts.
6. Corrections and repairs create new records/revisions; do not edit published core
   manifests. Maintainers should validate append-only history with
   `--base-ref <main-sha>`.

The current method paper is draft, `study_eligible=true`, and
`adoption_eligible=false`/`builder_eligible=false`. It may be frozen in a valid Paper 3
study, but must not be presented as operationally adopted or production-approved.

## Main branch and experiment boundary

`main` is the custodial paper and index surface. It may contain the frozen paper and
theory/method text, runner-facing protocol contracts that add no method rules,
provenance catalogs, immutable indexes, and tooling or tests whose only effect is to
validate or rebuild that custody. It must not contain an experiment-built Corridor
service, an arm-specific implementation, a task-specific scaffold or answer, or raw
benchmark results. Those artifacts stay on experiment or result branches. After
audit, `main` may record only their immutable full-commit, tree, and content
identities.

For a branch-building study, freeze the builder-input manifest and neutral objective
before dispatch. Repository policy does not choose or narrow the implementation.
Material not named by that manifest—including contributor or governance instructions,
prior results, hidden evaluator material, solutions, and solution-shaped scaffolds—is
not exposed to the builder session.

Task-constraint data are runner-facing custody records, not prompts. They may freeze
the public task/environment identity, matched-arm policy, resources, egress, and
post-score evidence plan, but must not prescribe the service design or add task hints.

Declare which intervention the study measures before building the branch:

- In an availability study, the builder receives only the declared method input and a
  neutral construction objective. Treatment and control receive byte-identical
  official benchmark instructions; only treatment can access the frozen branch
  service. Discovery and use are optional uptake outcomes.
- In a task-conditioned consumption study, the exact public benchmark task is frozen
  before builder dispatch. The builder receives that task, the declared method input,
  the public environment, and a neutral objective, and is otherwise free to implement
  the branch service. Treatment receives the same official task bytes as control plus
  only the declared service access and a minimal instruction to consume it. A
  consumption attempt is part of treatment compliance, but its failure or absence is
  an observed outcome and never suppresses official scoring.

Both modes use the same model, tools, runtime limits, evaluator, and retry policy for
the matched task runs. Once the builder branch and pair are frozen, do not qualify,
repair, tune, or add task guidance to either arm until both runs finish. A shared
infrastructure readiness check may run before dispatch only when it is identical for
both arms and neither inspects nor executes the branch service. The prospective
task-conditioned procedure is specified in
[`protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT.md`](protocol/TASK-CONDITIONED-CORRIDOR-EXPERIMENT.md).

After both arms finish, apply the frozen evaluator before experiment-specific audit or
repair. Preserve the score, observable runner, tool, and service logs, exact commits
and trees, environment or container identities, and a content-addressed manifest of
actual persistent state, including database files or volumes when present. Keep the
scored tree immutable; add audit material only in a descendant result commit or a
separate result branch. Never publish credentials, hidden reasoning, unrelated account
history, or unlicensed or private data.

Schemas, validators, and indexes on `main` preserve record structure and publication
only. They do not add experiment-facing method requirements, select an implementation,
qualify a service, or gate dispatch or scoring unless a separately frozen study
explicitly declares that intervention.

## Public release contributions

Public branches use the deterministic namespaces in
[`protocol/PUBLIC-RELEASE-BRANCHES.md`](protocol/PUBLIC-RELEASE-BRANCHES.md): custody on
`main`; one dataset/release/taskset/task/construction/build/candidate/revision per
`corridor/...` branch; and one dataset/release/taskset/task/study/run/arm/result-release
per `results/...` branch. The full typed identity remains authoritative and the branch
is only its locator. A new task or correction gets a new branch segment and release row;
never rewrite an existing row in `exogenous/registry/PUBLIC-RELEASES.json`.

The public default is summaries and digests. Keep executable task-specific services,
solution code, writeback SQL, databases, detailed agent logs, raw sessions,
trajectories, hidden evaluator material, and internal Git history off every proposed
public ref. Use the exact visibility states `public-summary`,
`embargoed-solution-bearing`, `restricted-on-request`, and
`public-after-retirement-or-maintainer-clearance`. For an active benchmark,
exact-service replay remains embargoed unless the benchmark maintainer has approved
publication. Method-transfer replication on an unseen task is the preferred public path.

Do not merge an internal experiment branch and delete sensitive files at its tip: the
deleted objects remain reachable. Recreate curated public commits from the intended
clean custody base. Before requesting review, stage the exact candidate and run:

```sh
python3 tools/public_release.py validate-registry --base-ref <public-base-commit>
python3 tools/public_release.py check \
  --ref HEAD --allow-ref HEAD --base-ref <public-base-commit> --allow-dirty
```

After the candidate is committed, repeat the check without `--allow-dirty` against its
full commit. The checker covers the Git index, selected ref tree, and reachable history;
`.gitignore` is not evidence of absence. Complete
`docs/PUBLIC-RELEASE-CHECKLIST.md`, obtain independent content review, and get explicit
owner authorization for the exact remote and refs. A passing validator never grants
permission to push.

Run the full command set in `README.md` before opening a PR. Structural validity does
not establish semantic truth, evaluator honesty, causal effect, or legitimate
real-world authority. Report those limits explicitly.
