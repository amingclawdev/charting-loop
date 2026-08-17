# Terminal-Bench 3.0 full-method runbook

This runbook launches the performance probe defined in
`protocol/TASK-CONDITIONED-CORRIDOR-BENCHMARK-V4.md`. It does not run a treatment /
control experiment. Every task dynamically builds its own Corridor; Worker and
independent QA both read that exact frozen Corridor.

## 1. Preconditions

Use Harbor 0.21.0 or newer with Modal support, a working Docker installation for
local checks, an authenticated Modal workspace, and a Codex login on the launch
host. Never paste subscription, Harbor, Modal, or Codex tokens into a command,
configuration committed to Git, task prompt, or result artifact.

This run is bound to `charting-loop-method-v7` at
`c68813cea1aa1d1eeaafde69a3f35f71ffab6d0d`, METHOD digest
`sha256:35590e6a3adddcfc5e210a52045c473d286fdbf256db8c47f951a754d7477fb6`,
and SCOPE-DATUM digest
`sha256:8e5daca8d7e880521b37fdf1ac63b0e7a919d4bab2446d4aca7e135689f11c35`.
Agent v0.8.1 resolves this identity and rejects changed catalog or method bytes before
any paid model call.

The agent computes the local `corridor_kit` source-tree digest, uploads that exact SDK
read-only before Builder, verifies the remote digest, and records it in trial metadata.
The SDK supplies task-neutral work rows, capability registry, Position timeline,
advisory reminders, immutable Worker/QA submission custody, and a generic read-only
binary pack. It contains no task-specific patch, offset, verifier fact, or stored
answer.

```bash
uv tool install --upgrade 'harbor[modal]'
harbor --version
docker ps
modal profile current
codex login status
```

Harbor and Modal authentication are interactive host setup, not benchmark context.
`CODEX_FORCE_AUTH_JSON=1` asks the installed Harbor Codex adapter to upload the
host's existing `~/.codex/auth.json` into an ephemeral secret path. The adapter does
not persist the credential in ATIF or task artifacts. Export this switch in the host
environment. Do **not** pass it through Harbor's `--ae`: extra-agent environment
values are also registered as redaction patterns, so the literal value `1` would
cause every `1` in captured logs and JSON to be replaced and corrupt the custody
record.

Confirm the immutable dataset identity before a paid run:

```bash
harbor version show terminal-bench/terminal-bench@3.0.0 --json
```

Expected content hash:
`sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
The package contains 74 tasks; 4 require GPU access, so the full run uses Modal.

## 2. Local no-model validation and mandatory doctor

Run these from the Charting Loop repository root:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_FORCE_AUTH_JSON=1

python3 -m unittest tests.test_full_method_agent -v
python3 -m unittest tests.test_corridor_kit -v
python3 -m unittest discover -s tests -v

python3 -m corridor_kit manifest corridor_kit

python3 tools/corridor_registry.py validate-method \
  --method-index method-paper/VERSIONS.json

HARBOR_PY="$HOME/.local/share/uv/tools/harbor/bin/python"
"$HARBOR_PY" -c \
  'from benchmark_agents.harbor_agent import ChartingLoopFullMethodAgent; print(ChartingLoopFullMethodAgent.import_path())'

export CHARTING_LOOP_MODAL_SPEND_LIMIT_USD='<the current cap shown in the Modal dashboard>'

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-ico-path-patch-009 \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 \
  --trusted-cyber-access-confirmed \
  --json
```

The spend limit is an operator attestation: copy the configured billing-cycle cap,
not the amount already spent and not an invented larger number. Modal exposes current
cycle charges to the CLI but does not expose that dashboard cap. The trusted-access
flag similarly records that the operator completed Codex Trusted Cyber Access; the
Codex CLI exposes login state but not that verification state.

The doctor is fail-closed and non-paid. It only performs account/configuration reads,
Harbor `--print-config`, local byte and output checks, and a Docker Linux self-test of
the actual CL-057 timeout cleanup. It does **not** start a Harbor trial, Modal task
environment, or model call. Its Linux self-test also imports a read-only frozen
adapter as root under the exact phase environment and proves that neither
`__pycache__` nor `.pyc` bytes appear and that the frozen tree remains byte-identical.
It verifies all of the following before returning `ready: true`:

- clean committed Git and frozen method/agent identities;
- Harbor 0.21+, the exact Terminal-Bench 3.0.0 content hash, login, and a claimed
  GitHub username required by Harbor upload;
- readable Modal billing plus sufficient headroom under the operator-declared cap;
- Codex login, `~/.codex/auth.json`, `CODEX_FORCE_AUTH_JSON=1`, and the explicit
  Trusted Cyber Access attestation;
- exactly the canonical task filter `terminal-bench/ico-path-patch`, one task, one
  concurrent trial, Modal, Agent v0.8.1,
  `gpt-5.6-sol` at max effort, zero automatic retries, and private upload;
- the cached task's x86-64 binary, which requires the Modal amd64 environment rather
  than a local arm64 execution substitute;
- a previously unused job name and writable output parent; and
- cleanup of a cancellation-resistant phase child with no process left behind; and
- binding the installed NVM-local Codex CLI to a stable path and invoking
  `codex --version` from a fresh Linux phase shell; and
- suppression of descendant Python bytecode writes while a frozen Corridor adapter
  is imported by a root-owned phase, without weakening the freeze digest check.

Exit 0 means the declared condition is ready. Exit 2 means at least one check failed;
follow the per-check repair instruction and rerun the doctor. Exit 3 is a doctor
internal error. A prior failed job is never resumed or overwritten: use the next
unused job name, keep `--max-retries 0`, and retain the failed artifact as evidence.

## 3. One paid smoke task

Do not start with all 74 tasks. First run one task privately and inspect its role
logs, freeze identity, QA decision, grading result, cost, and ATIF:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_FORCE_AUTH_JSON=1

harbor run \
  --job-name charting-loop-tb3-ico-path-patch-009 \
  -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 \
  -i terminal-bench/ico-path-patch \
  --n-tasks 1 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  -n 1 \
  --max-retries 0 \
  --upload --private
```

Run this paid command only when the immediately preceding doctor report for the same
job name says `ready: true`. The doctor does not authorize changing any flag between
preflight and launch. If a condition changes, rerun the doctor.

Job `charting-loop-tb3-ico-path-patch-002` is permanently retained as
launcher-invalid: its short `-i ico-path-patch` filter matched no dataset member, so
Harbor created no Job and started no Modal or model work. Never reuse or overwrite
that identity.

Job `charting-loop-tb3-ico-path-patch-003` is permanently retained as
runtime-invalid. Modal ran the official verifier, but Builder, Worker, and QA each
reported `codex: not found`; the frozen Corridor was only the harness fallback and
QA was `not_assessed`. Its official 0.0 is infrastructure evidence, not method
performance. The unmodified local custody tree is
`/private/tmp/charting-loop-tb3-results/charting-loop-tb3-ico-path-patch-003` on the
launch host. Its private Harbor upload also failed because the Hub write endpoint
rejected the profile username even though the read-side doctor probe found one;
that publication-identity discrepancy is separate from scoring and must be resolved
before claiming an uploaded result. Never reuse or overwrite `003`; the next paid
identity was `004`.

Job `charting-loop-tb3-ico-path-patch-004` is permanently retained as
runtime-invalid. Harbor installed Codex successfully under the default agent user's
runtime home, but Agent v0.5.1 then looked only under `/root/.nvm`; its fail-closed
setup probe stopped before Builder, Worker, QA, verifier, or any paid model call.
The unmodified local custody tree is
`/private/tmp/charting-loop-tb3-results/charting-loop-tb3-ico-path-patch-004` on the
launch host. Never reuse or overwrite `004`; the next paid identity was `005`.

Job `charting-loop-tb3-ico-path-patch-005` is permanently retained as a valid
end-to-end method-v4 observation with official reward `0.0`. Builder completed in
about 1115 seconds and produced a 27-item acceptance ledger, but definition closure
and construction readiness remained unresolved. Worker exhausted its 900-second phase
and QA exhausted its 450-second phase. This is method-performance evidence, not an
account, launcher, or infrastructure invalidation. It motivated the generic work-row,
capability, and reminder design but supplied no task bytes, offsets, opcodes, verifier
material, transcript content, or repair to method v5 or the frozen SDK. Never reuse or
overwrite `005`; the next paid identity is `006`.

Job `charting-loop-tb3-ico-path-patch-006` is permanently retained as a valid
end-to-end method-v5 observation with official reward `0.0`. The fixed per-phase
allocation stopped Worker before a complete official deliverable was placed under
submission custody; downstream QA time could not recover that lost state. This is a
method/runner performance failure, not an account or infrastructure invalidation. It
motivated the task-neutral v6 rule of one total deadline plus monotonic Worker
snapshots; no task answer, patch byte, offset, verifier fact, or transcript content
was imported into v6. Never reuse or overwrite `006`; the next paid identity is
`007`.

Job `charting-loop-tb3-ico-path-patch-007` is permanently retained as
runtime-invalid. Builder completed and froze a complete acceptance ledger, and
Worker froze a complete candidate snapshot under submission custody. Before QA or
the official verifier ran, however, the root-owned role process imported the frozen
Python task adapter and created `__pycache__/task_adapter.cpython-312.pyc`. The strict
manifest and Corridor digest verification correctly stopped the run on that
unplanned byte. Consequently `verifier_result` is null: this is runtime evidence,
not an official score or method-performance result. Agent v0.8.1 exports
`PYTHONDONTWRITEBYTECODE=1` for every phase, while retaining the same strict freeze
verification; it does not delete, allowlist, or normalize post-freeze bytes. The
private Harbor upload also encountered the previously observed profile-username
write discrepancy, which is separate from execution validity. Never reuse or
overwrite `007`; the next paid identity is `008`.

Job `charting-loop-tb3-ico-path-patch-008` is permanently retained as a valid
end-to-end method-v7 failure with official reward `0.0`: 15 of 19 verifier checks
passed, one completed trial raised no exception, and Harbor performed no retry.
Builder, Worker, and QA all completed under one total deadline in about 24m55s,
32m25s, and 19m15s respectively. Both Worker and QA read the same frozen Corridor;
the latest complete Worker submission was graded even though QA's contradictory
closure made its effective outcome `not_assessed`. The remaining failure was an
internal acceptance-boundary completeness miss while `task_ready` remained false,
not a launcher, account, timeout, or verifier failure.

The official maintainers had reported a best grader result of 10/19 under the original
90-minute condition in
[`harbor-framework/terminal-bench#1453`](https://github.com/harbor-framework/terminal-bench/issues/1453).
They later changed all task limits to eight hours. Consequently 15/19 is useful
same-condition diagnostic context, but it is still reward 0.0, not a current
eight-hour leaderboard maximum, accepted submission, or rank. The private Harbor
upload failed on profile identity after scoring; this is separate from task validity.
Raw role logs, binaries, patch bytes, and exact failure witnesses remain sealed.
Never reuse or overwrite `008`; the next paid identity is `009`.

The default task time limit is part of the initial leaderboard condition. Do not
silently raise `--agent-timeout-multiplier`; if a larger end-to-end budget is needed,
declare and label it as a separate condition.

The task's advertised time limit is the only execution budget. Builder, Worker, QA,
repair, and closure do not receive independent hard allocations. A bounded
finalization reserve remains inside the total deadline solely to stop the current
process, verify custody, restore the latest complete Worker snapshot, and return to
Harbor.

Acceptance checks for the smoke task:

- `agent/phases/builder`, `agent/phases/worker`, and `agent/phases/qa` exist.
- `agent/trajectory.json` is ATIF-v1.7 and embeds three unique role trajectories.
- orchestration metadata contains one `corridor_digest` and both Worker and QA logs
  refer to that same digest/path.
- `FREEZE.json` reports `acceptance_ledger.status=complete`, a non-empty exact
  acceptance-ID set, and no ledger errors before treating internal QA pass as valid.
- `WORK_ITEMS.json` covers the exact acceptance-ID set, has no dependency cycle or
  dangling capability ID, and gives every row scope and replayable done-when evidence.
- `CAPABILITIES.json` identifies selected mechanics by version, digest, contracts,
  applicability, and side effects; it contains no task answer or fixed patch.
- metadata records the locally and remotely verified SDK tree digest, Position
  timeline path, current-row projection, capability IDs, reminder count, and any
  non-gating timeline evidence loss.
- Worker and QA logs both query the same frozen work/capability paths and runner-owned
  timeline; each treats reminders as advisory rather than mutation or grading Gates.
- orchestration metadata records one absolute task deadline and remaining time at
  every role handoff, and contains no independent per-phase budget allocation.
- Worker freezes its first complete, scorable official task state and every later
  verified improvement as immutable, digest-bound versions; QA freezes assessments in
  a separate cooperative role namespace. Role labels are provenance, not credentials
  or permission Gates, and this condition makes no hostile-role isolation claim.
- before grading, the runner verifies the exact latest role/sequence/snapshot/tree
  binding, prevalidates every restore target and staging write, and performs per-file
  atomic replacement. It does not claim whole-set atomicity; a commit-phase partial
  prefix is a reported restore failure. If no Worker snapshot exists, metadata says so
  explicitly and does not invent one.
- QA emits exactly one result for every expected acceptance ID, independently checks
  the original public task sources, and reports no unmapped or unresolved item before
  pass.
- the Corridor tree and `FREEZE.json` have no write bits after construction.
- `qa_decision.repair_required` is true only for a schema-valid fail with a witness.
- a repair, if present, resumed the saved Worker session; closure resumed saved QA.
- grading ran even when QA reported fail, blocked, invalid output, or not assessed.
- no raw credential value appears in downloaded logs or uploaded artifacts.

Inspect locally with:

```bash
harbor view jobs
```

Keep the Harbor upload private until these checks pass.

## 4. Full 74-task run

Choose concurrency that fits the authenticated Modal workspace. Sixteen is a
starting point, not a scientific constant:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_FORCE_AUTH_JSON=1

harbor run \
  --job-name charting-loop-tb3-3.0.0-full-002 \
  -d terminal-bench/terminal-bench@3.0.0 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  -n 16 \
  --upload --private
```

Do not add a control arm to this job. The public Terminal-Bench leaderboard is the
performance comparison surface. A causal treatment/control comparison remains a
separate, cheaper, task-level study with equal budgets and frozen conditions.

## 5. Review before sharing

Record the job id, Harbor version, dataset content hash, agent commit, model identity,
reasoning effort, Modal environment, concurrency, wall time, SDK version/tree digest,
work-row and capability validation counts, reminder/timeline evidence, aggregate
cost/tokens, all task rewards, construction-fallback count, QA outcome counts, repair
count, and any infrastructure errors or retries.

Then make the upload public or submit it to the leaderboard only under the current
Terminal-Bench/Harbor publication instructions. Do not call this a causal estimate.
The strongest accurate sentence is:

> This is the end-to-end score of a dynamically constructed, frozen-Corridor agent
> whose Worker and independent QA both used the same task-conditioned Corridor,
> frozen work rows and capabilities, and advisory runtime timeline.

For causality, select a task prospectively and run a matched no-Corridor comparison.
For method attribution, add a null Builder that gets the same task and “build a
reusable aid first” objective but not the Charting Loop method.
