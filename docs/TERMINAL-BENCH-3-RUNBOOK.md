# Terminal-Bench 3.0 runbook

## Current no-Builder, in-clock Graph Kernel study

The current prospective study is
`method-guided-graph-kernel-experiment-v1.2`, specified in
[`INTEGRATED-GRAPH-EXPERIMENT-PROTOCOL-V1.2.md`](INTEGRATED-GRAPH-EXPERIMENT-PROTOCOL-V1.2.md).
It does **not** run a task-specific Builder. Both arms receive the same task-neutral
`corridor_kit` v0.7.1 Graph Kernel and Graph Agent v1.1.0. The Method arm gives Worker
and QA the exact frozen `charting-loop-method-v8`; the neutral arm gives both roles a
frozen neutral instruction. The Kernel stores Rules, Rule authority and dependencies,
admitted Facts, whole-state Position checkpoints, and Direction proposals/snapshots.
It validates structure and provenance only: it does not choose Direction, establish
task truth or PASS, authorize mutation, repair output, or act as a Gate.

Rule-candidate custody in kit v0.7.1 uses a deterministic bounded envelope so large
compile reports can remain exact without raising the graph's 5 MiB safety limit. Compile
QA receives digest-bound, read-only IR and report views materialized beneath the immutable
candidate root. This changes storage and QA custody only; it does not change the frozen
Method, task authority, Gate policy, or scoring semantics.

Run two matched profiles on each of two same-task adaptive regression probes:

- `bun-sourcemap-leak` probes Rule authoring and Fact admission;
- `music-harmony` probes Position-to-Direction reprojection.

These tasks have already informed engineering, so the runs are mechanism regressions,
not fresh transfer samples, independent replications, or causal proof. The comparison
is Method-guided execution versus a neutral instruction conditional on byte-identical
Kernel infrastructure. There is one official task clock, no phase allocation, no
Builder, one trial per job, zero automatic retries, and private upload.

Inside that one clock, Worker freezes the first complete scorable revision; QA audits
the paired immutable Worker/graph revision before official verification. A replayable,
identity-bound QA witness may resume the same Worker session for repair and a newer
freeze, which the same QA session audits again. QA is advisory and never repairs,
blocks, or grants PASS. At deadline or a non-repair decision, the harness restores the
latest valid Worker freeze and returns it to Harbor; Harbor then runs the official
verifier. Invalid or missing QA cannot erase that freeze or prevent grading.

Before every paid job, run the non-paid doctor with the exact job name, task, arm,
committed HEAD, and current Modal cap. It must return `ready: true`:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CODEX_FORCE_AUTH_JSON=1
export CHARTING_LOOP_MODAL_SPEND_LIMIT_USD='<current dashboard cap>'
export CHARTING_LOOP_EXPERIMENT_HEAD="$(git rev-parse HEAD)"

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-bun-graph-v12-method-001 \
  --task bun-sourcemap-leak --study-arm method \
  --expected-head "$CHARTING_LOOP_EXPERIMENT_HEAD" \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 --trusted-cyber-access-confirmed --json

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-bun-graph-v12-neutral-001 \
  --task bun-sourcemap-leak --study-arm neutral \
  --expected-head "$CHARTING_LOOP_EXPERIMENT_HEAD" \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 --trusted-cyber-access-confirmed --json

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-music-graph-v12-method-001 \
  --task music-harmony --study-arm method \
  --expected-head "$CHARTING_LOOP_EXPERIMENT_HEAD" \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 --trusted-cyber-access-confirmed --json

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-music-graph-v12-neutral-001 \
  --task music-harmony --study-arm neutral \
  --expected-head "$CHARTING_LOOP_EXPERIMENT_HEAD" \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 --trusted-cyber-access-confirmed --json
```

After the matching doctor succeeds, launch the corresponding private jobs. Do not
change any flag between doctor and launch:

```bash
harbor run --job-name charting-loop-tb3-bun-graph-v12-method-001 -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 -i terminal-bench/bun-sourcemap-leak \
  --n-tasks 1 -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopGraphKernelMethodAgent \
  -m openai/gpt-5.6-sol --ak reasoning_effort=max -n 1 --max-retries 0 \
  --upload --private

harbor run --job-name charting-loop-tb3-bun-graph-v12-neutral-001 -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 -i terminal-bench/bun-sourcemap-leak \
  --n-tasks 1 -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopGraphKernelNeutralAgent \
  -m openai/gpt-5.6-sol --ak reasoning_effort=max -n 1 --max-retries 0 \
  --upload --private

harbor run --job-name charting-loop-tb3-music-graph-v12-method-001 -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 -i terminal-bench/music-harmony \
  --n-tasks 1 -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopGraphKernelMethodAgent \
  -m openai/gpt-5.6-sol --ak reasoning_effort=max -n 1 --max-retries 0 \
  --upload --private

harbor run --job-name charting-loop-tb3-music-graph-v12-neutral-001 -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 -i terminal-bench/music-harmony \
  --n-tasks 1 -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopGraphKernelNeutralAgent \
  -m openai/gpt-5.6-sol --ak reasoning_effort=max -n 1 --max-retries 0 \
  --upload --private
```

Preserve job output, Worker and QA role logs, Study profile, live graph JSONL, every
paired immutable graph revision, every Worker snapshot, every QA report and witnessed
repair disposition, ATIF, final restore identity, verifier output, and private custody.
Do not run an additional post-score repair or feed verifier feedback into the task.

Compare path structure as well as reward: Rule coverage/authority,
Fact-admission receipts, checkpoint count and completeness, Position-bound Direction
changes, invalid append attempts, Worker revision count, QA repair recommendations,
witness replay dispositions, and last-valid fallback.

## Historical Builder-first full-method runbook

This runbook launches the performance probe defined in
`protocol/TASK-CONDITIONED-CORRIDOR-BENCHMARK-V4.md`. It does not run a treatment /
control experiment. Every task dynamically builds its own Corridor; Worker and
independent QA both read that exact frozen Corridor.

## 1. Preconditions

Use Harbor 0.21.0 or newer with Modal support, a working Docker installation for
local checks, an authenticated Modal workspace, and a Codex login on the launch
host. Never paste subscription, Harbor, Modal, or Codex tokens into a command,
configuration committed to Git, task prompt, or result artifact.

This run is bound to `charting-loop-method-v8` at
`3c3813444a7d43d0a56837e9cb960be86ce26d06`, METHOD digest
`sha256:85b5a7a8700312ec1e35b80df6e224221d44a48904247a8d6d32cfe940459446`,
and SCOPE-DATUM digest
`sha256:bd70498b2f75e039d88c80ae0c5b0a11fba15d12517820c27e8bccb28da987af`.
Agent v0.9.0 resolves this identity and rejects changed catalog or method bytes before
any paid model call. The frozen reusable SDK condition is `corridor_kit` v0.5.0 plus
its per-run canonical source-tree digest.

The agent computes the local `corridor_kit` source-tree digest, uploads that exact SDK
read-only before Builder, verifies the remote digest, and records it in trial metadata.
The SDK supplies task-neutral authoring and witness records, work rows, capability registry, Position timeline,
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
  --task ico-path-patch \
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
- exactly the canonical `terminal-bench/<task>` filter derived from the explicit
  supported `--task` name, one task, one concurrent trial, Modal, Agent v0.9.0,
  `gpt-5.6-sol` at max effort, zero automatic retries, and private upload;
- the selected task's pinned cache digest and manifest; for `ico-path-patch`, also
  the cached x86-64 binary that rules out a local arm64 execution substitute;
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
job name **and task** says `ready: true`. The doctor does not authorize changing any
flag between preflight and launch. If a condition changes, rerun the doctor.

### Two sequential adaptive regressions for Kit 0.5

These two runs are mechanism probes on previously failed tasks, not a matched
experiment, transfer claim, or benchmark-wide result. Keep WIP at one and run them in
this order. Each Builder starts from the public task and the same frozen Method v8 +
Kit 0.5 condition; it may not reuse an earlier task Corridor. Worker and QA read the
same frozen Corridor. Use one official task clock, zero retries, no per-role budget,
and the latest valid Worker snapshot if the clock expires. Do not change Method,
SDK, prompts, or harness between the doctor and either trial.

First, `bun-sourcemap-leak` tests whether the task-neutral Authoring layer reduces
time to the first valid, task-ready freeze enough to leave time for Worker and QA.
Its official clock is 1,800 seconds.

```bash
python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-bun-sourcemap-leak-kit05-001 \
  --task bun-sourcemap-leak \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 \
  --trusted-cyber-access-confirmed \
  --json

harbor run \
  --job-name charting-loop-tb3-bun-sourcemap-leak-kit05-001 \
  -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 \
  -i terminal-bench/bun-sourcemap-leak \
  --n-tasks 1 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  -n 1 \
  --max-retries 0 \
  --upload --private
```

Second, `music-harmony` tests a different mechanism: a known key-signature change
must be admitted as a new Position checkpoint, after which the real Position-bound
Direction and Entrance are reprojected. A changed generic digest is insufficient.
The record must preserve the ordered Position reference, timeline head, Direction
digest, current work row, and Rule-closure identity around that transition.

```bash
python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-music-harmony-kit05-001 \
  --task music-harmony \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 \
  --trusted-cyber-access-confirmed \
  --json

harbor run \
  --job-name charting-loop-tb3-music-harmony-kit05-001 \
  -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 \
  -i terminal-bench/music-harmony \
  --n-tasks 1 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  -n 1 \
  --max-retries 0 \
  --upload --private
```

For both jobs, retain the Builder stage timeline, every freeze, Worker/QA role
records, final verifier output, and remaining task time at each handoff. A score
cannot substitute for the Authoring or Position/Direction mechanism evidence.

### Third distinct-task transfer probe: `session-window-debug`

This task was selected prospectively from the public Terminal-Bench 3.0 package at
commit `2b0442c3c583b710ca8da14c8e601b99f2f1f244`, before inspecting any solution or
verifier bytes. Its public metadata classifies it as Software / Systems, gives the
agent 7,200 seconds, estimates eight expert hours, and requires no GPU. Its public
instruction asks for a repair across coupled late-event, session-merge, watermark,
and garbage-collection rules while treating `DESIGN.md` as authoritative. That makes
it a useful cross-domain test of whether the task-neutral work-row, acceptance,
capability, and timeline SDK transfers beyond binary and production-planning tasks.
The source records are
[`task.toml`](https://github.com/harbor-framework/terminal-bench/blob/2b0442c3c583b710ca8da14c8e601b99f2f1f244/tasks/session-window-debug/task.toml)
and
[`instruction.md`](https://github.com/harbor-framework/terminal-bench/blob/2b0442c3c583b710ca8da14c8e601b99f2f1f244/tasks/session-window-debug/instruction.md).

The doctor pins cache digest
`638c00fd438a0289ba75f6bc536861831f4a8eab2b85064064038e1bcc91cfbb`
and constructs the full filter from the bare task name; a short or mismatched Harbor
filter fails closed. Run the non-paid preflight first:

```bash
python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-session-window-debug-001 \
  --task session-window-debug \
  --jobs-dir jobs \
  --modal-spend-limit-usd "$CHARTING_LOOP_MODAL_SPEND_LIMIT_USD" \
  --min-modal-headroom-usd 1.00 \
  --trusted-cyber-access-confirmed \
  --json
```

Only if that exact report is `ready: true`, launch one private, zero-retry trial:

```bash
harbor run \
  --job-name charting-loop-tb3-session-window-debug-001 \
  -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 \
  -i terminal-bench/session-window-debug \
  --n-tasks 1 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  -n 1 \
  --max-retries 0 \
  --upload --private
```

Do not add a task-specific SDK function, inspect solution/verifier/hidden-test bytes,
retry a failed observation, or overwrite this job identity. Builder, Worker, and QA
must share one frozen Corridor digest and the original 7,200-second total task
deadline. Preserve the role logs, freeze and custody manifests, verifier output,
timings, cost, and final classification for audit.

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
