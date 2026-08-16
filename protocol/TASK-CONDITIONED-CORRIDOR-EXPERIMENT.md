# Task-conditioned Corridor experiment

This is prospective runner/evaluator guidance. It does not reinterpret any previously
frozen STUDY or RUN, add rules to the method paper, or constrain the builder's
implementation.

## Intended comparison

This design measures the result of a task-conditioned Corridor service being consumed
during a benchmark task. It is distinct from an availability study, where the service
is present but discovery and use are optional.

Freeze the comparison and its analysis plan before any builder or task session starts.
The official benchmark task is the only task requirement. Candidate schemas,
qualification chains, warranties, and governance receipts are not admission or scoring
requirements for this experiment unless a later frozen STUDY explicitly makes one of
them part of the intervention.

Freeze a runner-facing `TASK-CONSTRAINTS.json` according to
[`TASK-CONSTRAINT-DATUM.md`](TASK-CONSTRAINT-DATUM.md). The datum records the study
boundary and is not added to the builder or task-agent prompt. Only inputs named by its
builder-visible manifest are exposed to the builder.

## Build the treatment service

1. Freeze the exact public task instruction, public task environment, benchmark and
   evaluator identities, model/runtime configuration, resource limits, seed policy,
   and retry policy. Do not inspect or expose hidden tests, verifier bodies, reference
   solutions, prior results, or private evaluator data.
2. Start a fresh builder session. Give it the frozen Paper 2 representation, the
   public task and environment, and this neutral objective: build a Corridor branch
   service that can help a later agent complete the task.
3. Do not prescribe an API, schema, language, file layout, database, retrieval method,
   prompt, or implementation strategy. The builder may create code and persistent
   state as it judges useful. Record the exact inputs it saw.
4. Have the builder create and commit its own branch. Freeze the full commit, Git tree,
   service startup material, and content identities before either task arm begins.
   A branch name is only a locator.

The builder is not a task arm. Record its elapsed time, model usage, retries, and
resource cost separately as construction cost.

## Run the matched pair

Use fresh, independent task sessions and pristine environments. Treatment and control
must share the frozen official task bytes, model, tools, image, resource limits, retry
policy, evaluator, and seed assignment.

- Treatment receives access to the frozen builder-authored branch service and one
  minimal, frozen instruction to consume that service while solving the official task.
  The instruction identifies access; it must not add solution hints or restate Paper 2.
- Control receives the official task only and has no access to the branch service.

The treatment must attempt service consumption. Whether the service starts, is called,
returns useful data, changes persistent state, or is ignored is measured evidence—not
an admission, qualification, warranty, pre-score, or repair gate. Run the official
evaluator for both arms even when treatment consumption fails. Do not repair, tune,
replace, or re-prompt the service or either task agent after the pair is frozen.

Disable public-internet egress from both task environments. Allow the same
benchmark-declared internal services in both arms; treatment alone may reach the
frozen Corridor service. Route model control-plane traffic through a runner-held proxy
whose exact endpoint allowlist is frozen in the RUN pair and absent from prompts. Pull
images and dependencies before dispatch, and record allow/deny metadata without
credentials or request/response payloads.

## Audit only after scoring

Apply the frozen evaluator before experiment-specific audit. Preserve, when present:

- the official score and evaluator receipt;
- exact builder, treatment, control, scored, and result commits and Git trees;
- observable agent, runner, tool, and service logs or timelines;
- service invocation/request receipts sufficient to distinguish attempted, successful,
  failed, and absent consumption;
- the pre-score container/root-filesystem identity and a content-addressed inventory of
  persistent files;
- database files, transaction or query logs, dumps, and named-volume identities; and
- construction cost separately from treatment/control task-execution cost.

Do not publish credentials, hidden reasoning, unrelated account history, hidden
benchmark material, or private/unlicensed data. Keep each scored tree immutable. Add
logs, scores, database snapshots, and audit reports only in a descendant result commit
or a separate result branch, with provenance back to the scored commit.

Report service non-use or failure rather than deleting the run. A single matched pair
is descriptive evidence, not a causal or general performance claim.
