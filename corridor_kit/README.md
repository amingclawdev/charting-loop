# Corridor kit

`corridor_kit` is a small, task-neutral reference implementation for the mechanical
part of U → C. It lets a fresh Builder start from known-good evidence plumbing rather
than rebuilding JSON parsing, hashing, manifests, scratch isolation, and command
capture on every task.

The kit keeps execution ownership explicit: the Builder authors task-specific
`ACCEPTANCE.json`, `WORK_ITEMS.json`, selected `CAPABILITIES.json`, and bounded
`WITNESSES.json`; the runner owns the hash-linked Position timeline, freezing, and
custody outside the Corridor; the external evaluator owns official deliverability. Position,
Direction, Entrance, Guide, and reminder views are deterministic projections over
those surfaces; they do not create authority.

It is not a Corridor for any particular task. It contains no Rule or Fact supplied by
a benchmark, no domain validator, no candidate answer, no evaluator fixture, and no
authority to mutate a target. It also creates no mandatory workflow, approval, or
pre-mutation Gate. Every command is an advisory tool that a Builder, Worker, or QA may
choose to run.

## Reuse boundary

The frozen reusable layer is deliberately small:

- strict `charting-loop/task-acceptance-ledger/v2` parsing and validation, including
  positive, negative, boundary, state, temporal, and coupled verification obligations;
- strict `charting-loop/task-work-backlog/v1` row, dependency, and join validation;
- strict `charting-loop/capability-registry/v1` version, digest, contract,
  applicability, and side-effect validation;
- append-only `charting-loop/position-event/v1` observations, runner-admitted Facts,
  and deterministic current-row, Guide, and reminder projections;
- canonical JSON, content hashes, and deterministic source-tree manifests;
- labeled inventories of the public task world;
- atomic JSON/report writes;
- isolated, shell-free argv execution with replayable stdout and stderr;
- generic read-only ELF inventory, changed-range comparison, and replay binding; and
- a digest-bound, solution-free Method capsule plus honest acceptance, evidence,
  source-map, replay, work, capability, authoring-contract, and witness surfaces that
  begin uncompiled where task content is required; and
- one deterministic aggregate authoring report that reuses the acceptance, work,
  capability, and Method-capsule validators, reports every JSON surface digest and
  exact identity join, and separates structural validity from task readiness.

Each Builder must still compile the current task's acceptance items, Rule/Fact map,
coupled constraints, work rows, capability selections, domain checks, fixtures, and task adapter. Those bytes belong to
the task-specific Corridor and must never be copied from an earlier benchmark task.

The integrated benchmark executor is a separate, shorter profile. It has no Builder
and does not pretend to construct a mature Corridor inside a task clock. Worker and
QA instead share an append-only graph while doing and auditing the task. A Rule remains
immutable authority; `acceptance_checklist_item` records are source-bound operational
views that retain the Rule's obligation, scope, quantifier, behavioral partitions,
evidence requirement, and pass/fail/unknown decision rule. An incomplete, ambiguous,
or unsupported compilation remains explicit rather than becoming a weaker Rule.

Before a formal experiment, a fresh diagnostic session may compile the public task
into `charting-loop/typed-rule-ir/v4`. It sees only the frozen Method, a runner-frozen
AuthoritySnapshot, and the compiler interface. AuthoritySnapshot separates three
planes—normative Rule sources, public task-world Fact material, and supporting
inputs—and keeps exact byte custody separate from semantic extraction status and
extractor/artifact identity. A complete extraction freezes derived UTF-8 bytes, size,
digest and source-byte binding; every slice names `source_bytes` or
`extraction_artifact`. Readable bytes are not proof of successful extraction.

A separate source-clause inventory enumerates every normative clause, including
nested, trailing, exception, prohibition, and optional clauses, with a stable
clause-order key and ordered half-open byte slices before mapping clauses to Rules.
Array position is display-only. RuleCandidates may bind multiple disjoint or
cross-source slices and label obligation, domain, applicability, quantifier,
condition, outcome, prohibition, witness, and relationship roles. Their provenance
digest resolves the clause/order identity and exact source bytes.

Every relationship declares endpoint semantics, scope, per-endpoint cardinality and
an explicit keyed, aggregate-to-members, exact-pairs, or source-backed all-to-all
alignment. V4 never projects an edge from list order or an undeclared Cartesian
product. The compiler reverse-projects each candidate to its source slices and emits
SemanticDelta for missing roles, unmapped normative ranges, clause-to-Rule gaps, and
relationship alignment errors. Non-empty delta is incomplete, not a weaker PASS.

The resulting manifest binds AuthoritySnapshot, clause inventory, Method,
compiler/config and implementation, candidate revision and input policy. The immutable
first attempt is retained. A `semantic_repair` revision binds its parent digest and a
reproduced QA witness; it never overwrites history. The runner freezes
`authority_snapshot`, then an exactly reproducible `rule_candidate_report`; QA appends
`rule_qa_assessment` against that report but cannot ratify. Only a runner/operator
receipt that revalidates the current candidate, complete zero-issue/zero-delta report,
AuthoritySnapshot, reverse projection, and passing QA assessment establishes
RuleClosure. The
probe is not injected into the scored Worker; a same-task probe after verifier-informed
changes is regression evidence, not fresh efficacy or transfer.

The v1 through v3 compilers remain readable for historical custody. Missing v4
semantics remain explicitly legacy/unassessed and are never backfilled. New integrated
runs use v4.

Typed Rule IR makes the semantic compilation boundary explicit. Each Rule declares a
required/optional level, applicability predicate, kind, quantifier, source-defined
subject domain, condition branches and outcomes, semantic dependencies, and the
witness operators required to distinguish those outcomes. An open domain introduced
by language such as "including" cannot be closed by enumerating only produced output;
a collective ordering Rule cannot silently become a per-subject ordering Rule. The
compiler projects only cells authorized by each Rule and its declared alignment.
`per_subject` projection cannot become one aggregate check, and a temporal condition
cannot compile without a temporal operator. Natural-language interpretation remains
the agent's responsibility; the SDK makes its result inspectable and replayable rather
than pretending to infer task truth.

At Position assessment time, applicable checklist cells use pass/fail/unknown. A
conditional optional cell may be `not_applicable` only with unknown status and an
admitted Fact proving that its applicability predicate is false. Doctor treats that
cell as resolved without converting it into PASS. Omission, an empty domain, or a
missing witness is never equivalent to N/A. Doctor remains read-only and non-Gating.

`typed_dependency` records distinguish normative, work-row, and evidence relations.
Only `requires`, `produces_fact_for`, and `precondition_for` impose a hard order.
For `requires`, `from_ref` depends on `to_ref`; for `produces_fact_for` and
`precondition_for`, `to_ref` depends on `from_ref`.
`overlaps`, `derived_from`, `subsumes`, and `can_parallelize_with` do not serialize
work. A `conflicts` edge blocks the affected frontier until a current ratified source
Rule authorizes a `dependency_resolution`; `invalidates` requires downstream
assessment and Direction reprojection after upstream evidence changes.

The graph retains one whole-state Position identity with two checkpoint projections:
`row_progress` and `acceptance_assessment`. Both bind the whole current Rule closure,
checklist, admitted-Fact root, artifact revisions, task/world identity, scope, roles,
and parent Position. A Direction binds the exact Position plus its checklist and
ready/blocked/unresolved frontier. It is not a free-floating status and cannot be
reused after Position or upstream evidence changes.

The acceptance report keeps three questions separate. `coverage.status` and
`source_mapping_status` say whether every public normative clause has a ledger
location. `definition_closure_status` says whether mapped clauses and acceptance
items are unambiguous. `construction_readiness_status` says whether the coupled
requirements can be replayed together. A clause may therefore be mapped while its
meaning remains explicitly ambiguous; that is complete source mapping but incomplete
definition closure, and it cannot produce task readiness.

Each compiled acceptance item also carries six explicit behavioral verification
partitions: positive behavior, prohibited or negative behavior, boundary cases,
state transitions, temporal behavior, and coupled interactions. A partition that is
truly inapplicable still contains an explicit reason; an omitted or empty partition
is not silently treated as covered. These are Rule-derived audit obligations, not
hidden tests or evaluator knowledge.

## Commands

From the repository root:

```sh
python3 -m corridor_kit init /tmp/charting-loop/corridor \
  --method-version charting-loop-method-v8 \
  --method-digest sha256:METHOD_DIGEST \
  --method-scope-digest sha256:SCOPE_DIGEST
python3 -m corridor_kit validate-capsule \
  /tmp/charting-loop/corridor/METHOD-CAPSULE.json \
  --kit /tmp/charting-loop/corridor/KIT.json \
  --expected-method-version charting-loop-method-v8 \
  --expected-method-digest sha256:METHOD_DIGEST \
  --expected-method-scope-digest sha256:SCOPE_DIGEST
python3 -m corridor_kit validate \
  /tmp/charting-loop/corridor/ACCEPTANCE.json --allow-draft
python3 -m corridor_kit validate-capabilities \
  /tmp/charting-loop/corridor/CAPABILITIES.json --allow-draft
python3 -m corridor_kit validate-work \
  /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json --allow-draft
python3 -m corridor_kit authoring validate \
  /tmp/charting-loop/corridor --allow-draft \
  --expected-method-version charting-loop-method-v8 \
  --expected-method-digest sha256:METHOD_DIGEST \
  --expected-method-scope-digest sha256:SCOPE_DIGEST
python3 -m corridor_kit survey \
  --root specification=/app/public/SPEC.md \
  --root source=/app/public/src \
  --output /tmp/charting-loop/builder-scratch/world.json
python3 -m corridor_kit capture \
  --output /tmp/charting-loop/builder-scratch/runs/baseline \
  --cwd /app -- python3 -m public_package.tests
```

For the no-Builder benchmark profile, initialize, append, replay, and independently
inspect the graph with:

```sh
python3 -m corridor_kit rules compile /tmp/charting-loop/TYPED-RULE-IR.json \
  --run-classification fresh_task_pre_experiment \
  --output /tmp/charting-loop/TYPED-RULE-COMPILATION.json
python3 -m corridor_kit graph init /tmp/charting-loop/GRAPH.jsonl
python3 -m corridor_kit graph append /tmp/charting-loop/GRAPH.jsonl \
  --type authority_snapshot --actor runner --body-file /tmp/authority-snapshot.json
python3 -m corridor_kit graph append /tmp/charting-loop/GRAPH.jsonl \
  --type task_source_artifact --actor runner --body-file /tmp/source.json
python3 -m corridor_kit graph append /tmp/charting-loop/GRAPH.jsonl \
  --type source_clause --actor worker --body-file /tmp/clause.json
python3 -m corridor_kit graph append /tmp/charting-loop/GRAPH.jsonl \
  --type rule_proposal --actor worker --body-file /tmp/rule-candidate.json
# The runner freezes a reproducible rule_candidate_report; QA appends its assessment.
# Only a passing, same-candidate QA record permits an exact rule_ratification.
# Only then may Position and Direction bind the resulting RuleClosure digest.
python3 -m corridor_kit graph replay /tmp/charting-loop/GRAPH.jsonl
python3 -m corridor_kit graph doctor /tmp/charting-loop/GRAPH.jsonl
python3 -m corridor_kit graph query /tmp/charting-loop/GRAPH.jsonl \
  --kind active-context --max-chars 24000
python3 -m corridor_kit graph query /tmp/charting-loop/GRAPH.jsonl \
  --kind edge-source-trace --ref SEDGE-...
```

The immutable index stores each declared semantic Rule edge once and links its
typed checklist expansions by ID. An edge trace exposes its endpoint Rule/record
identities, declared relationship and alignment, direct source slices or declared
derivation inputs, condition kinds, checklist rows, and witness obligations. The
relationship expectation is `source_bound` only for explicit frozen relationship
slices; otherwise it remains `unresolved`. The Kit never guesses `requires`,
ordering, conflict, or other business meaning from a Rule or condition kind.

`active-context` deterministically selects the latest Position's open checklist,
hard ancestors, immediate dependants, conflict/invalidation edges, source traces,
and witness obligations. A character cap limits expanded detail, while compact hard
constraint IDs are always retained. Truncation reports exact omitted IDs and their
digest; it never causes a second model call.

A successor Direction may add `semantic_bindings`. Every entry binds the exact
Position, current Rule ID and record, semantic-edge IDs where applicable, one
checklist row, and its deterministic witness-obligation IDs. Concrete task action is
not a Direction field; it belongs to the later execution transition. Aggregate ID
lists or a timeless/global-union witness cannot close a typed temporal checklist.
Missing or incompatible witnesses keep that checklist and verified claim open, but
they never block freezing a complete scorable snapshot or running the external
grader.

The Doctor is deterministic and read-only. It recomputes chain integrity, hard-edge
topological order, checklist/Position alignment, Direction freshness, invalidation
closure, declared behavioral-partition and typed coverage-cell completeness, and
witness operator/Rule-semantics alignment. For v4 it also recomputes AuthoritySnapshot
manifest/receipt and byte/extraction separation, representation-specific UTF-8 slice
bounds and digests, clause/role closure, exact relationship edge sets/cardinality,
candidate-report/QA/RuleClosure bindings, and whether
Position and Direction bind the same current closure. These are mechanical checks
only: Doctor does not decide whether selected prose expresses the right semantics or
whether a derivation is logically true. Its report binds the exact graph
bytes, graph identity, Doctor code, Position, Direction, and acceptance root. Its only
classifications are `structurally_invalid`, `structurally_valid_but_incomplete`, and
`acceptance_assessed_complete`. None is task truth, official PASS, delivery or mutation
authority, or a blocking Gate. A valid but incomplete graph remains honest evidence;
an invalid graph revision cannot erase the latest verified Worker submission.

Inspect the reusable binary pack without selecting it for a task:

```sh
python3 -m corridor_kit capabilities builtins
python3 -m corridor_kit binary inventory ./program
python3 -m corridor_kit binary diff ./before ./after
python3 -m corridor_kit binary replay --input program=./program -- ./check ./program
```

After the Builder compiles and the runner freezes all three task surfaces, the runner
appends observations and both Worker and QA may read the same projections:

```sh
python3 -m corridor_kit timeline append /tmp/charting-loop-position/POSITION.jsonl \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --actor runner --event-type run_initialized --status observed
python3 -m corridor_kit runtime guide \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json \
  --timeline /tmp/charting-loop-position/POSITION.jsonl
python3 -m corridor_kit runtime reminders \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json \
  --timeline /tmp/charting-loop-position/POSITION.jsonl
```

The runtime first computes a content-addressed `PositionRef` checkpoint from the
frozen work digest, visible timeline prefix, and runner-admitted Fact root. It then projects `Direction` from
that PositionRef, the transitive frozen Rule closure selected by the current row,
and the applicable frozen capabilities. `Entrance` and `Guide` are derived from that
Direction rather than acting as independent authority. Worker and QA therefore see
the same position-relative acceptance boundary. Direction exposes current-row Facts,
six-partition witness coverage, and remaining witness gaps; adding a Fact changes the
PositionRef and Direction digest but never changes the frozen Rule closure.

Worker and QA may author concise candidate observations, but only the runner may
admit them. Admission strictly binds role, Corridor digest, PositionRef, work row,
acceptance ID, obligation partition, source, witness, replay, and candidate identity,
then appends one hash-linked `facts_admitted` event. Malformed, stale, conflicting,
or unbound candidates fail closed without becoming Facts or blocking task execution:

```sh
python3 -m corridor_kit timeline admit-facts \
  /tmp/charting-loop-position/POSITION.jsonl \
  --candidate /tmp/fact-candidates.json \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --actor runner --expected-role worker \
  --expected-corridor-digest sha256:CORRIDOR \
  --expected-position-ref sha256:POSITION \
  --expected-candidate-ref worker-snapshot-0001
```

For diagnosis, a caller may request a read-only counterfactual projection by
substituting a Position or acceptance ledger. The result is explicitly
`hypothetical=true`; it cannot admit Facts, replace Position, mutate acceptance,
append a real timeline transition, establish authority, certify PASS, or close work:

```sh
python3 -m corridor_kit runtime counterfactual \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json \
  --timeline /tmp/charting-loop-position/POSITION.jsonl \
  --substitute-position /tmp/hypothetical-position.json
```

Draft validation exists only so the initial scaffold can state its incompleteness
honestly. Before runner-owned freezing, run `validate` without `--allow-draft`; a final
ledger needs at least one atomic acceptance item, complete source coverage, and a
replayable entrypoint before it may report construction readiness `ready`.

## Authoring contract and coupled witnesses

`AUTHORING.json` is identical in every scaffold. Its exact surface descriptors name
Builder-owned files separately from runner and external-evaluator surfaces. Its
boundaries are fixed: advisory and read-only validation, no mutation authority, no
blocking Gate, no task solution, no evaluator material, and no inferred task answer.
It contains no task ID, Rule, domain algorithm, candidate, or outcome-derived repair.

`WITNESSES.json` starts empty with `state=uncompiled` and a null acceptance digest.
After the Builder compiles it, each witness has exactly a stable `witness_id`, one or
more known `acceptance_ids`, one or more explicit `obligation_partitions`, a disposition
from `pass`, `deny`, `hold`, or `refusal`, and a replay object. The replay object contains a non-empty direct `argv`, at least
one labeled input ref and digest, one result ref and digest, and `shell=false`.
The surface is bounded to finite witness, acceptance-ID, argv, input-ref, and string
sizes. Its coverage projection lists covered and missing acceptance-ID/partition pairs;
even complete coverage with all `pass` dispositions cannot infer task PASS, an answer,
authority, or official deliverability.

`authoring validate` loads strict JSON without following symlinks and reuses the
existing normative validators instead of reimplementing their schemas. It reports raw
file and canonical-JSON SHA-256 identities per surface plus exact work→acceptance,
witnesses→acceptance, and kit→Method-capsule joins. Missing, malformed, symlinked, or
digest-mismatched surfaces fail closed. `structurally_valid` says only that these
schemas and joins are sound; `task_ready` says the task surfaces are fully compiled.
`officially_deliverable` always remains external and `not_assessed`.

The runner, not the Builder, freezes the resulting task-specific Corridor. Worker and
QA then receive the same frozen bytes and digest. Both independently re-read public
task sources; QA audits Corridor evidence instead of assuming the Corridor proves
itself.

The compact capsule contains only Builder invariants, required surface names, and
the frozen Method identities. It is not a substitute authority for the Method and
contains no task Rule, Fact, candidate, or solution. `EVIDENCE.json`,
`SOURCE-MAP.json`, and `REPLAY.json` remove repeated plumbing while remaining
honestly uncompiled until the Builder maps the current public task.

QA uses the same typed semantic validator before its raw assessment is frozen and
again when the harness reads it:

```sh
python3 -m corridor_kit qa validate \
  --path /tmp/charting-loop/qa/assessment.json \
  --freeze /tmp/charting-loop/FREEZE.json
```

Contradictory or incomplete semantics normalize to `not_assessed`; the raw report is
not rewritten and cannot trigger repair. This classification is advisory and never
prevents benchmark grading.

The bundled `corridor_kit.domain.binary` pack contains no benchmark identifier,
opcode recipe, fixed offset, verifier knowledge, or candidate patch. Its descriptor
digest identifies the declared contract, while the SDK tree digest binds its
implementation bytes. Timeline row states remain RAW observations: they do not prove
done-when conditions, authorize mutation, or suppress the external evaluator.

`capture` invokes an argv with `shell=False`; metacharacters are data rather than an
implicit shell program. It records argv and the working directory, so callers must not
put credentials, subscription tokens, or other secrets in command arguments. Public
release still requires the repository's normal result sanitization.

## Monotonic submission custody

The kit can preserve complete task-state versions without knowing a benchmark or
domain. The Worker explicitly lists every absolute output or task-state path that
belongs to one complete, scorable version:

```sh
PYTHONPATH=/opt/charting-loop-sdk python3 -m corridor_kit submission freeze \
  --root /logs/agent/submissions --role worker \
  --path /absolute/task-output --path /absolute/task-checksum
```

Run `submission freeze` again after each verified improvement. Each version is
immutable, content-addressed, and linked to the preceding role version; `latest`
advances only after all declared regular-file bytes are closed. `submission list` and
`submission verify` audit the stored versions. Verification binds a selected `latest`
reference exactly to the manifest role, sequence, snapshot ID, and tree digest.
Freeze and list output also distinguishes the initial checkpoint, a byte-changing
content revision, and a byte-identical validation re-freeze. It reports sequence,
parent, changed-file count, content-revision index, and last-freeze time without
including solution bytes.

`submission restore` validates every blob, destination, parent, mode, and staging
write before changing a declared destination. It then performs one atomic replacement
per file. This is not a whole-set transaction: an operating-system failure or path
race during the replacement loop can leave a reported prefix restored. Restore uses
only the caller's existing operating-system authority and cannot expand it.

Worker and QA are cooperative protocol roles. The `--role` value is a namespace and
provenance label, not a credential, ACL, account boundary, or permission Gate. QA uses
role `qa` for versioned assessment files and is instructed to write only its
assessment; the store does not enforce that instruction against a hostile process. A
QA snapshot is never a Worker submission. Snapshots do not prove acceptance,
authorize mutation, or create a workflow Gate. Symlinks, special files, relative
paths, corrupt blobs, duplicate destinations, and incomplete references fail closed.
For database or service state that cannot be represented by regular files, a
task-specific Corridor adapter must first materialize and restore an equivalent closed
checkpoint.

The benchmark adapter additionally copies the exact frozen Corridor, `FREEZE.json`,
Position timeline, role transcripts, and submission manifests into the private job
result directory before environment teardown. Its custody manifest records direct
versus recovered provenance, file hashes, a tree digest, and whether the copied
Corridor byte-matches the frozen digest. These artifacts may contain task solutions;
they are private evidence and require a separate redaction decision before release.

## Extraction record

The implementation was selected after comparing three sources:

1. Charting Loop already had canonical JSON, strict input handling, Corridor tree
   freezing, and runtime-evidence semantics in `benchmark_agents/contract.py` and
   `tools/corridor_runtime.py`. Those local semantics are the primary implementation
   source.
2. The CL-030/031/032 production-planning Corridor demonstrated the reusable shape of
   a documented CLI, dry-run/replay path, self-tests, and a runner-verifiable manifest.
   Its ERP/MES/WMS planner, constraints, facts, and decisions are not copied.
3. The local `batched-eval-parity` Corridor independently demonstrated the same CLI,
   isolated-run, report, guide, fixture, and manifest mechanics. Its evaluator model,
   metamorphic cases, failure findings, and source paths are not copied.

Aming Claw was also inspected as a mature implementation derived from the method. Its
stable contract hashing, snapshot manifests, trace records, and replay discipline
support the same generic design. Direct module reuse was rejected: those modules are
coupled to Aming Claw's private database, actor sessions, route authority, gates, and
service topology. The public kit has no import-time or runtime dependency on Aming
Claw and does not present that implementation as the method's required architecture.

## Freezing and integration

The Rule-compilation release sets `KIT_VERSION` to `0.7.0`. `KIT_VERSION` identifies
the API, while the exact Git commit plus
`python3 -m corridor_kit manifest corridor_kit` tree digest identifies the bytes.
A source-tree manifest excludes interpreter-created `__pycache__`, `.pyc`, and `.pyo`
files under a declared, digest-bound policy. The runner removes those derived caches
before freezing and then uses the same manifest implementation for freeze, verification,
and private custody, so every retained task-authored byte has one identity at every intake.
A benchmark harness should verify those two identities, upload the package read-only,
and tell the assigned role where it is. Changing any kit byte creates a new kit revision; do not
learn domain rules from one benchmark and silently add them to the shared revision.

The Harbor adapter uploads the frozen kit before the task clock starts, exposes only
these documented commands, and records its version and tree digest in trial metadata.
In the integrated profile, Worker compiles task-specific RuleCandidates in the shared
graph; Worker and QA read the same AuthoritySnapshot, graph, and frozen submissions.
Fresh Worker and QA prompts also
receive the exact frozen Method v8 bytes, version, and digest: the official task remains
Rule authority and the Method remains procedural self-diagnosis guidance. A partial or
uncompiled Corridor stays advisory; it cannot abort Worker, QA, or external grading,
and incompleteness alone is `not_assessed`, not a business `blocked` result. Every reminder reports
`advisory_only=true`, `authorizes_mutation=false`, and `blocking_gate=false`.
