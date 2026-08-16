# Executable manifest contracts

This page is a runner-facing projection of executable schemas; it is not a second
method source. `method-paper/METHOD.md` is the sole normative source for the corridor
method.

## Version dispatch

| record family | legacy schema | current schema | dispatch rule |
|---|---|---|---|
| exogenous run | `charting-loop/exogenous-run/v1` | `charting-loop/exogenous-run/v2` | validate only against the exact selected run version |
| exogenous study | `charting-loop/exogenous-study/v1`, `charting-loop/exogenous-study/v2` | `charting-loop/exogenous-study/v3` | v1/v2 retain `protocol_sha256`; v3 resolves the exact declared `protocol_ref` |
| task set | `charting-loop/exogenous-taskset/v1`, `charting-loop/exogenous-taskset/v2` | `charting-loop/exogenous-taskset/v3` | v1/v2 retain the single release-root TaskSet; v3 uses a versioned taskset-id path |
| task constraint | `charting-loop/task-constraint-datum/v1` | `charting-loop/task-constraint-datum/v2` | v1 retains the no-repair pair; v2 validates the matched Worker-QA and Position-ledger policy |
| method catalog | `charting-loop/method-index/v1` | `charting-loop/method-index/v2` | validate only against the exact selected catalog version |
| public release registry | — | `charting-loop/public-release-registry/v1` | preserve the exact ordered row sequence; existing rows and v1 policy are append-only |

The remaining runner-facing dispatches are:

- `charting-loop/corridor/v1`: complete pilot v1 envelope under
  `templates/legacy-corridor-v1/`, validated by the preserved v1 path in
  `tools/corridor_registry.py`.
- `charting-loop/candidate/v2`: minimal, non-indexable draft Candidate under
  `templates/corridor/`.
- `charting-loop/registry-entry/v1`: legacy v1 public registry only.
- `charting-loop/exogenous-score/v1`: neutral evaluator record under `exogenous/`.
- `charting-loop/public-release-registry/v1`: public branch custody records under
  `exogenous/registry/PUBLIC-RELEASES.json`; it is a publication index, not experiment
  evidence and not a method rule.

Schema versions are not interchangeable. Dispatch is by the literal `schema_version`; a
runner must not up-convert, down-convert, or otherwise infer one version from the
other. In particular, no v2 field may be mapped or inferred into v1
authority/evaluation/certificate fields. A v1 record retains its exact historical
contract, and a v2 record must satisfy its complete current contract.

## Public release registry projection

The v1 public release registry has the closed top-level fields `schema_version`,
`branch_namespaces`, `public_artifact_classes`, `restricted_artifact_classes`,
`release_policy`, and `releases`. Its namespace catalog is deterministic:

- custody: `main`;
- Corridor artifacts:
  `corridor/<dataset>/<release>/<taskset>/<task>/<construction>/<build>/<candidate>/<revision>`; and
- result summaries:
  `results/<dataset>/<release>/<taskset>/<task>/<study>/<run>/<arm>/<result-release>`.

An immutable release row contains exactly `sequence`, `release_id`, `branch_kind`,
`branch_ref`, `identity`, `commit_sha`, `tree_sha`, `artifact_manifest_path`,
`artifact_manifest_sha256`, `visibility`, `contamination_status`,
`contamination_facts`, `outcomes`, `sealed_artifacts`, `publication_evidence`, `claims`,
`released_at`, and `supersedes_release_id`. Full Git object identifiers and `sha256:`
digests are required.
The validator resolves the commit, recomputes its tree and committed manifest digest,
checks the live branch locator, and joins non-genesis releases to the declared public
base ancestry. Sequence is contiguous and one-based; an existing row may not be
deleted, edited, or reordered. A correction is a new row that names an earlier row
through `supersedes_release_id`.

The closed identity object represents benchmark dataset/release/taskset/task,
method/protocol/study, construction/build/candidate/revision, and
launch/attempt/run/arm/result release; inapplicable fields are null. Results carry an
exact six-state outcome count (`pass`, `fail`, `blocked`, `invalid`, `timeout`, and
`unscored`) plus their total. Contamination facts explicitly record upstream-oracle and
local-artifact visibility/publication times, evaluated model and knowledge-cutoff
declaration, runtime and network policy, counting disposition, exact method
attribution, and `training_ingestion=not-inferred`. Sealed artifact records carry only
digest, size, media type, license status, provenance, source ref, custody, and release
trigger. The publication-evidence object holds nullable maintainer-clearance and task-
retirement refs; the corresponding ref becomes mandatory before the public-after state.

The registry begins empty because invitation readiness is not a remote publication.
Only a separately authorized release appends a row. `public-summary` permits the
closed public classes in the registry; it does not make solution-shaped content safe.
Task-specific executable code, SQL, databases, trajectories, raw or detailed logs,
hidden evaluator bytes, and internal Git history remain embargoed or restricted.
`tools/public_release.py` validates the registry and scans an explicitly allowlisted Git
ref, its exact staged tree, and reachable named blobs. The tool does not authorize a
push or establish the truth of a scientific claim. `summarize-registry` deterministically
renders the separate release index to stdout; it never edits or mixes release custody
into `exogenous/registry/EXPERIMENTS.md`, which remains the run index.

`charting-loop/exogenous-study/v3` replaces the ambient single-protocol assumption with
a closed `protocol_ref` containing exactly `path` and `sha256`. The path is repository-
relative beneath `protocol/`, and the target must be a present regular non-symlink file
whose raw bytes match the digest. Historical v1/v2 studies retain their exact
`protocol_sha256` contract; they are not rewritten when a later versioned protocol is
introduced. Protocol versioning therefore creates a new STUDY datum rather than
changing the meaning of an earlier one.

`charting-loop/task-constraint-datum/v2` adds closed `qa` and `position_ledger`
objects. It freezes construction QA outside the pair and byte-identical matched QA,
repair, scoring, and append-only ledger policies inside both arms. It neither exposes
the ledger to the Worker/builder nor changes the sole treatment difference. Historical
v1 data retain their exact `no-repair-after-pair-freeze` semantics.

`charting-loop/exogenous-taskset/v3` keeps the v2 task, constraint, environment, and
evaluator contracts but locates each immutable variant at
`benchmarks/<dataset-id>/<release>/tasksets/<taskset-id>/TASKSET.json`. This permits
multiple prospective constraint profiles for one exact upstream release without
rewriting the release-root v1/v2 TaskSet consumed by an earlier STUDY.

## Exact v2 `WorldRef` projection

The `world_ref` in `charting-loop/exogenous-run/v2` is a closed identity object. These
lists project the exact field sets enforced by `tools/exogenous_registry.py` and used by
`templates/run/RUN.json`:

- `WORLD_REF_KEYS`: `project_id`, `run_id`, `generation_id`, `repository_url`, `base_commit`, `environment_sha256`, `evidence_prefix`, `derived_state_sha256`
- `PREFIX_KEYS`: `stream_id`, `through_sequence`, `prefix_sha256`, `admission`, `projector`
- `ADMISSION_KEYS`: `receipt_id`, `admitted_root_sha256`, `rule_revision`, `rule_sha256`
- `PROJECTOR_KEYS`: `schema_version`, `algorithm_id`, `algorithm_version`, `algorithm_sha256`

The identity therefore binds the project, run, and generation identifiers; a canonical
HTTPS repository URL; the complete immutable 40-lowercase-hex base commit; the
environment digest; and the derived-state digest. Its raw-ledger prefix binds the
stream identifier, the non-negative contiguous-prefix watermark and digest, the
admission receipt and admitted-root digest together with the admission-rule revision
and digest, and the projector schema plus algorithm identifier, version, and digest.

Every component in those closed field sets is identity-bearing. Changing any component,
including any nested prefix, admission, or projector component, creates a different
`WorldRef`; runners must not normalize distinct components into the same identity.

## Current method eligibility projection

`method-paper/VERSIONS.json` records `paper2-current-v2` as the unique current study
package under `charting-loop/method-index/v2`. It is frozen at
`f58e065ad5d035b55fc8668b094e42327382345a`, with METHOD digest
`sha256:ce9c94c12660c57a8dc34c98afd46c644b07214a2f9e7a9a494078fbe7be0905`
and SCOPE-DATUM digest
`sha256:c0764df57d20b5d66500ec75c8f8fcd5e0dd5c5029bd35783caca6a68133e307`.
Its eligibility snapshot is `status=frozen`, `study_eligible=true`,
`adoption_eligible=false`, and `builder_eligible=false`: it may be frozen into a study
but is not approved for adoption or builder execution. The retained `draft-v2` row is
historical and `study_eligible=false`. The v1 method-index contract remains a distinct
legacy dispatch and does not acquire these v2 fields by inference. A frozen research
package does not imply publication maturity, a warranty, or operational adoption.

`method-paper/METHOD.md` remains the sole normative method source. This manifest only
projects the catalog and validator contract for runners; it does not create or override
method rules, status, or eligibility.

See `CORRIDOR-SCHEMA.md` for Candidate structure and
`CANDIDATE-CERTIFICATE.md` for the independent evidence surfaces. Optional authority
evidence is outside the required v2 Candidate payload. Neutral run schemas and strict
join rules are implemented in `tools/exogenous_registry.py`.
