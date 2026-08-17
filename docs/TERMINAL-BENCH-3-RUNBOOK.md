# Terminal-Bench 3.0 full-method runbook

This runbook launches the performance probe defined in
`protocol/TASK-CONDITIONED-CORRIDOR-BENCHMARK-V3.md`. It does not run a treatment /
control experiment. Every task dynamically builds its own Corridor; Worker and
independent QA both read that exact frozen Corridor.

## 1. Preconditions

Use Harbor 0.21.0 or newer with Modal support, a working Docker installation for
local checks, an authenticated Modal workspace, and a Codex login on the launch
host. Never paste subscription, Harbor, Modal, or Codex tokens into a command,
configuration committed to Git, task prompt, or result artifact.

This run is bound to `charting-loop-method-v4` at
`0d3ed5c357c906edcc697a83b3ce681c68cd353a`, METHOD digest
`sha256:d3a9da497c31f3bde46a31f37990236af51b9f677ae807d023582b27254c4ab0`,
and SCOPE-DATUM digest
`sha256:65c6a91120c15bec30278288a26ecc98bdf96cfb07fd490dc915408a78844327`.
Agent v0.5.0 resolves this identity and rejects changed catalog or method bytes before
any paid model call.

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
python3 -m unittest discover -s tests -v

python3 tools/corridor_registry.py validate-method \
  --method-index method-paper/VERSIONS.json

HARBOR_PY="$HOME/.local/share/uv/tools/harbor/bin/python"
"$HARBOR_PY" -c \
  'from benchmark_agents.harbor_agent import ChartingLoopFullMethodAgent; print(ChartingLoopFullMethodAgent.import_path())'

export CHARTING_LOOP_MODAL_SPEND_LIMIT_USD='<the current cap shown in the Modal dashboard>'

python3 tools/terminal_bench_doctor.py \
  --job-name charting-loop-tb3-ico-path-patch-002 \
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
environment, or model call. It verifies all of the following before returning
`ready: true`:

- clean committed Git and frozen method/agent identities;
- Harbor 0.21+, the exact Terminal-Bench 3.0.0 content hash, login, and a claimed
  GitHub username required by Harbor upload;
- readable Modal billing plus sufficient headroom under the operator-declared cap;
- Codex login, `~/.codex/auth.json`, `CODEX_FORCE_AUTH_JSON=1`, and the explicit
  Trusted Cyber Access attestation;
- exactly `ico-path-patch`, one task, one concurrent trial, Modal, Agent v0.5.0,
  `gpt-5.6-sol` at max effort, zero automatic retries, and private upload;
- the cached task's x86-64 binary, which requires the Modal amd64 environment rather
  than a local arm64 execution substitute;
- a previously unused job name and writable output parent; and
- cleanup of a cancellation-resistant phase child with no process left behind.

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
  --job-name charting-loop-tb3-ico-path-patch-002 \
  -o jobs \
  -d terminal-bench/terminal-bench@3.0.0 \
  -i ico-path-patch \
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

The default task time limit is part of the initial leaderboard condition. Do not
silently raise `--agent-timeout-multiplier`; if a larger end-to-end budget is needed,
declare and label it as a separate condition.

Acceptance checks for the smoke task:

- `agent/phases/builder`, `agent/phases/worker`, and `agent/phases/qa` exist.
- `agent/trajectory.json` is ATIF-v1.7 and embeds three unique role trajectories.
- orchestration metadata contains one `corridor_digest` and both Worker and QA logs
  refer to that same digest/path.
- `FREEZE.json` reports `acceptance_ledger.status=complete`, a non-empty exact
  acceptance-ID set, and no ledger errors before treating internal QA pass as valid.
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
  --job-name charting-loop-tb3-3.0.0-full-001 \
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
reasoning effort, Modal environment, concurrency, wall time, aggregate cost/tokens,
all task rewards, construction-fallback count, QA outcome counts, repair count, and
any infrastructure errors or retries.

Then make the upload public or submit it to the leaderboard only under the current
Terminal-Bench/Harbor publication instructions. Do not call this a causal estimate.
The strongest accurate sentence is:

> This is the end-to-end score of a dynamically constructed, frozen-Corridor agent
> whose Worker and independent QA both used the same task-conditioned Corridor.

For causality, select a task prospectively and run a matched no-Corridor comparison.
For method attribution, add a null Builder that gets the same task and “build a
reusable aid first” objective but not the Charting Loop method.
