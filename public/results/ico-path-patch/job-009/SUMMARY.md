# `ico-path-patch` job 009 — public engineering result

## Result

- Official evaluator: **19/19 checks**, reward `1.0`.
- Runtime: 5,194 seconds wall time; 5,107.230 seconds of agent execution under
  the then-current 5,400-second task deadline.
- Condition: `openai/gpt-5.6-sol`, maximum reasoning effort, Method v8, Corridor
  SDK v0.4.0, Agent v0.9.0, and a Modal task environment.
- Harness outcome: one completed trial, zero automatic retries, and zero trial
  exceptions.

This is an official task pass. It is **not a complete Method-conformance pass**:
the frozen Corridor reported incomplete definition closure and unresolved
construction readiness. QA consumed the same frozen Corridor and its runtime
Guide, but its internally contradictory assessment normalized to
`not_assessed`; it found no concrete defect and caused no repair.

## Observable execution facts

The frozen Corridor contained 11 files and 119,516 bytes and had digest
`sha256:b8b8f2853ffc9cb30372af08dcd6ef1a652235243d822b9998f9bff2aa08ce7d`.
Worker created six complete submission snapshots. Snapshot 6 was restored for
grading with tree digest
`sha256:458931fa489a7207663b311fdaf44a6a9ecc628b58b9ad798c6055bd3c6c4e7a`.

The original task container had already been destroyed when custody was
collected. The Corridor was recovered from the archived Builder rollout and
reproduced the expected frozen digest exactly. This is recovered byte-identical
custody, not a direct container download.

## Adaptation and claim boundary

This run followed earlier attempts on the same task. In particular, job 008
received an official 15/19 result with four failing verifier checks. General
Method and SDK work then strengthened acceptance-boundary representation before
job 009 ran. No task-specific solution bytes were placed in the reusable SDK,
but the development sequence was informed by same-task verifier feedback.
Consequently, evaluator-feedback-informed adaptation is an alternative
explanation for the improvement and must not be hidden.

Job 007 is classified separately as **project-caused harness-integrity
invalid**: an undeclared Python bytecode file changed a frozen tree. Jobs 002–004
were launcher/runtime infrastructure failures before meaningful task work. Job
008 remains a valid 15/19 method failure; job 009 does not rewrite it.

This release is a descriptive Corridor-assisted engineering result. It is not
an independent reproduction, a matched Treatment/Control experiment, a causal
estimate, multi-task efficacy evidence, a world-first claim, a leaderboard
maximum, or an accepted Harbor submission.

## Custody boundary

`MANIFEST.json` publishes hashes and byte sizes for the private audit, runner
result, recovered Corridor manifest, role transcripts, evaluator receipt, final
Worker snapshot, original binary, patch generator, and patched binary. Those raw
bytes remain sealed because they contain an active benchmark task, solution
material, hidden-verifier detail, private paths, or authentication-bearing logs.
The public branch contains only this summary and digest commitments.
