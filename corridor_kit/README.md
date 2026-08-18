# Corridor kit

`corridor_kit` is a small, task-neutral reference implementation for the mechanical
part of U → C. It lets a fresh Builder start from known-good evidence plumbing rather
than rebuilding JSON parsing, hashing, manifests, scratch isolation, and command
capture on every task.

The kit has four deliberately separate execution surfaces: frozen task-specific
`ACCEPTANCE.json`, frozen `WORK_ITEMS.json`, frozen selected `CAPABILITIES.json`, and
a runner-owned hash-linked Position timeline outside the Corridor. Position,
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
- append-only `charting-loop/position-event/v1` observations plus deterministic
  current-row, Guide, and reminder projections;
- canonical JSON, content hashes, and deterministic source-tree manifests;
- labeled inventories of the public task world;
- atomic JSON/report writes;
- isolated, shell-free argv execution with replayable stdout and stderr;
- generic read-only ELF inventory, changed-range comparison, and replay binding; and
- a digest-bound, solution-free Method capsule plus honest acceptance, evidence,
  source-map, replay, work, and capability surfaces that begin uncompiled.

Each Builder must still compile the current task's acceptance items, Rule/Fact map,
coupled constraints, work rows, capability selections, domain checks, fixtures, and task adapter. Those bytes belong to
the task-specific Corridor and must never be copied from an earlier benchmark task.

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
  --expected-method-digest sha256:METHOD_DIGEST
python3 -m corridor_kit validate \
  /tmp/charting-loop/corridor/ACCEPTANCE.json --allow-draft
python3 -m corridor_kit validate-capabilities \
  /tmp/charting-loop/corridor/CAPABILITIES.json --allow-draft
python3 -m corridor_kit validate-work \
  /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --acceptance /tmp/charting-loop/corridor/ACCEPTANCE.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json --allow-draft
python3 -m corridor_kit survey \
  --root specification=/app/public/SPEC.md \
  --root source=/app/public/src \
  --output /tmp/charting-loop/builder-scratch/world.json
python3 -m corridor_kit capture \
  --output /tmp/charting-loop/builder-scratch/runs/baseline \
  --cwd /app -- python3 -m public_package.tests
```

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
frozen work digest and visible timeline prefix. It then projects `Direction` from
that PositionRef, the transitive frozen Rule closure selected by the current row,
and the applicable frozen capabilities. `Entrance` and `Guide` are derived from that
Direction rather than acting as independent authority. Worker and QA therefore see
the same position-relative acceptance boundary.

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

`KIT_VERSION` identifies the API, while the exact Git commit plus
`python3 -m corridor_kit manifest corridor_kit` tree digest identifies the bytes.
A source-tree manifest excludes interpreter-created `__pycache__`, `.pyc`, and `.pyo`
files under a declared, digest-bound policy; the runner's later task-Corridor freeze
remains stricter and closes over every retained task artifact.
A benchmark harness should verify those two identities, upload the package read-only,
and tell Builder where it is. Changing any kit byte creates a new kit revision; do not
learn domain rules from one benchmark and silently add them to the shared revision.

The Harbor adapter uploads the frozen kit before Builder starts, exposes only these
documented commands, and records its version and tree digest in trial metadata. The
Builder compiles task-specific rows and adapters; Worker and QA query the same frozen
rows, capability identities, and runner timeline. Every reminder reports
`advisory_only=true`, `authorizes_mutation=false`, and `blocking_gate=false`.
