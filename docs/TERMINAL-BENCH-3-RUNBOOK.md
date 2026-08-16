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
not persist the credential in ATIF or task artifacts.

Confirm the immutable dataset identity before a paid run:

```bash
harbor version show terminal-bench/terminal-bench@3.0.0 --json
```

Expected content hash:
`sha256:a32a61879ea94eb9dc16fa1fbeb398759f0c07ca633d9d1f6aec760207036da3`.
The package contains 74 tasks; 4 require GPU access, so the full run uses Modal.

## 2. Local no-model validation

Run these from the Charting Loop repository root:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

python3 -m unittest tests.test_full_method_agent -v
python3 -m unittest discover -s tests -v

HARBOR_PY="$HOME/.local/share/uv/tools/harbor/bin/python"
"$HARBOR_PY" -c \
  'from benchmark_agents.harbor_agent import ChartingLoopFullMethodAgent; print(ChartingLoopFullMethodAgent.import_path())'

harbor run --print-config \
  -d terminal-bench/terminal-bench@3.0.0 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  --ae CODEX_FORCE_AUTH_JSON=1 \
  --n-tasks 1 \
  -n 1
```

`--print-config` resolves configuration and exits. It does not start a task or call
the model. Confirm that the printed agent path, model, `reasoning_effort`, auth-json
flag, Modal environment, and dataset ref are exact.

## 3. One paid smoke task

Do not start with all 74 tasks. First run one task privately and inspect its role
logs, freeze identity, QA decision, grading result, cost, and ATIF:

```bash
export CHARTING_LOOP_ROOT="$PWD"
export PYTHONPATH="$CHARTING_LOOP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

harbor run \
  --job-name charting-loop-tb3-smoke-001 \
  -d terminal-bench/terminal-bench@3.0.0 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  --ae CODEX_FORCE_AUTH_JSON=1 \
  --n-tasks 1 \
  -n 1 \
  --upload --private
```

The default task time limit is part of the initial leaderboard condition. Do not
silently raise `--agent-timeout-multiplier`; if a larger end-to-end budget is needed,
declare and label it as a separate condition.

Acceptance checks for the smoke task:

- `agent/phases/builder`, `agent/phases/worker`, and `agent/phases/qa` exist.
- `agent/trajectory.json` is ATIF-v1.7 and embeds three unique role trajectories.
- orchestration metadata contains one `corridor_digest` and both Worker and QA logs
  refer to that same digest/path.
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

harbor run \
  --job-name charting-loop-tb3-3.0.0-full-001 \
  -d terminal-bench/terminal-bench@3.0.0 \
  -e modal \
  -a benchmark_agents.harbor_agent:ChartingLoopFullMethodAgent \
  -m openai/gpt-5.6-sol \
  --ak reasoning_effort=max \
  --ae CODEX_FORCE_AUTH_JSON=1 \
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
