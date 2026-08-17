# Corridor kit

`corridor_kit` is a small, task-neutral reference implementation for the mechanical
part of U → C. It lets a fresh Builder start from known-good evidence plumbing rather
than rebuilding JSON parsing, hashing, manifests, scratch isolation, and command
capture on every task.

The kit has three deliberately separate execution surfaces: frozen task-specific
`WORK_ITEMS.json`, frozen selected `CAPABILITIES.json`, and a runner-owned hash-linked
Position timeline outside the Corridor. Current-row Guide and reminder views are
deterministic projections over those surfaces; they do not create authority.

It is not a Corridor for any particular task. It contains no Rule or Fact supplied by
a benchmark, no domain validator, no candidate answer, no evaluator fixture, and no
authority to mutate a target. It also creates no mandatory workflow, approval, or
pre-mutation Gate. Every command is an advisory tool that a Builder, Worker, or QA may
choose to run.

## Reuse boundary

The frozen reusable layer is deliberately small:

- strict `charting-loop/task-acceptance-ledger/v1` parsing and validation;
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
- an honest starter whose acceptance, work, and capability surfaces begin uncompiled.

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

## Commands

From the repository root:

```sh
python3 -m corridor_kit init /tmp/charting-loop/corridor
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
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json \
  --timeline /tmp/charting-loop-position/POSITION.jsonl
python3 -m corridor_kit runtime reminders \
  --work /tmp/charting-loop/corridor/WORK_ITEMS.json \
  --capabilities /tmp/charting-loop/corridor/CAPABILITIES.json \
  --timeline /tmp/charting-loop-position/POSITION.jsonl
```

Draft validation exists only so the initial scaffold can state its incompleteness
honestly. Before runner-owned freezing, run `validate` without `--allow-draft`; a final
ledger needs at least one atomic acceptance item, complete source coverage, and a
replayable entrypoint before it may report construction readiness `ready`.

The runner, not the Builder, freezes the resulting task-specific Corridor. Worker and
QA then receive the same frozen bytes and digest. Both independently re-read public
task sources; QA audits Corridor evidence instead of assuming the Corridor proves
itself.

The bundled `corridor_kit.domain.binary` pack contains no benchmark identifier,
opcode recipe, fixed offset, verifier knowledge, or candidate patch. Its descriptor
digest identifies the declared contract, while the SDK tree digest binds its
implementation bytes. Timeline row states remain RAW observations: they do not prove
done-when conditions, authorize mutation, or suppress the external evaluator.

`capture` invokes an argv with `shell=False`; metacharacters are data rather than an
implicit shell program. It records argv and the working directory, so callers must not
put credentials, subscription tokens, or other secrets in command arguments. Public
release still requires the repository's normal result sanitization.

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
