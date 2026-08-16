# Service-plan Corridor E2E demo

This is a non-normative synthetic lifecycle fixture plus a sanitized observation of one
small Corridor/task-only Docker pair. The default run uses Python's standard library
and requires no model, network, Docker, API key, or ChatGPT subscription.

```sh
python3 demos/service-plan-corridor-e2e/run_demo.py --check
```

The command regenerates the evidence bundle in memory, validates all joins, and compares
it with `expected/RUNTIME-EVIDENCE.json`. To inspect a fresh canonical bundle without
changing the repository:

```sh
python3 demos/service-plan-corridor-e2e/run_demo.py --output /tmp/runtime-evidence.json
```

## What the deterministic fixture exercises

The fixed task compiles an admitted service inventory into a canonical plan. `W0` and
`W1` use the same project/run/generation, public repository, base, admission Rule, and
projector; the runner-owned `core-ready` event extends the contiguous RAW ledger prefix.
Its timeline presence alone does not make it a Fact; the W1 admission root binds the
new admitted projection.

For each revision, Position resolves the `service-plan-builder` role definition to an
admitted `RoleDefinition` Rule and its holder binding to an admitted
`ActorRoleAssignment` Fact with explicit authority source and liveness. The
AuthorityWarranty binds those assignment-governing surfaces, not the stage Direction
Rule; the EvidentialWarranty separately binds the assignment to the
certificate-covered Direction evidence.

The synthetic treatment sequence is:

1. diagnose U because no live warranty exists, freeze projection `r0@W0`, run a
   side-effect-free canary that consumes the Guide result, record `pc-r0`, and assess
   live EvidentialWarranty `ew-r0-live-w0` plus AuthorityWarranty `aw-r0-live-w0`;
2. consume the fixture's projected `C0` state through one bounded stage-1 Entrance;
3. append the single `core-ready` event, obtaining `W1` on the same base world;
4. append lapsed EvidentialWarranty `ew-r0-lapsed-w1` and return
   `typed-refusal: stale_world_ref` before another mutation;
5. preserve all r0 records, re-enter U, freeze r1, and obtain new traversal,
   certificate, live EvidentialWarranty, and live AuthorityWarranty at W1; and
6. consume the fixture's projected `C1` state through one bounded stage-2 Entrance and
   run the common evaluator.

The default task-only and Corridor records receive the exact same stage instruction
bytes, fixtures, checkpoint, and public evaluator output. They are deterministic parity
projections, not two independent agent executions. Both have the same `TASK_PASS`.
Only the treatment projection receives `CORRIDOR_E2E_PASS`; that score does not
contribute to task success.
The schemas and joins are described in
[`protocol/RUNTIME-EVIDENCE-SCHEMA.md`](../../protocol/RUNTIME-EVIDENCE-SCHEMA.md).

## Observed Docker/Codex pair

[`examples/PAIR-RESULT.json`](examples/PAIR-RESULT.json) is a digest-bound sanitized,
runner-reported record of one real serial Docker pair using the exact public seed
commit. It reports that both valid arms passed the same evaluator and produced identical
final plan bytes, and that the treatment exhibited Entrance → checkpoint → stale
refusal → re-entry → Entrance. The first treatment attempt is retained as an excluded
infrastructure failure. Raw evidence is intentionally not published here, so this file
is not promoted into a PathCertificate or independent verification receipt.

That observation is not a performance golden or a benchmark. It used one fixed order,
different prompt bytes, a repaired command wrapper, different cache histories, a public
evaluator, and an isolation downgrade required by the nested sandbox. It tests a tiny
Corridor system package with task-only knowledge; it does not estimate the effect of the
method paper.

## Optional model/Docker lane

The repository deliberately does not run a subscription-backed agent in CI. A manual
rerun must start from fresh named volumes, pin the public seed commit, model, CLI and
image identities, keep the evaluator network-free and credential-free, and write raw
artifacts only below the ignored `exogenous/local/` boundary. Never copy a personal
Codex home, host workspace, Docker socket, Git/SSH credentials, or raw authentication
material into this demo tree or an image layer.

Codex permission profiles and legacy sandbox settings do not compose; a manual runner
must choose one permission model and mechanically preflight its file/network boundary.
See the official [permission profiles](https://learn.chatgpt.com/docs/permissions),
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), and
[CI authentication boundary](https://learn.chatgpt.com/docs/auth/ci-cd-auth).

## Manual instrumented-acceptance assembly

`run_acceptance_pair.py` is a local assembler for artifacts that an operator has already
produced in fresh, non-scripted AI-agent sessions. It is not an agent launcher: it has no
model or network client and never creates, repairs, retries, or labels a session on the
operator's behalf. Run it only after placing raw evidence, one independently issued
session-receipt file per attempt, usage receipts, a fixed measurement plan, and an
independently produced replay receipt beneath a private evidence root, and after
materializing the complete validated STUDY/RUN registry beneath
a separate exogenous root.

```sh
python3 demos/service-plan-corridor-e2e/run_acceptance_pair.py \
  --manual \
  --input /private/acceptance/ACCEPTANCE-INPUT.json \
  --evidence-root /private/acceptance/evidence \
  --exogenous-root /private/acceptance/exogenous \
  --method-index /path/to/frozen/method-paper/VERSIONS.json \
  --output /private/acceptance/records/pilot-r1.json
```

The input has schema `charting-loop/acceptance-input/v1` and closed top-level fields:
`acceptance_id`, runner identity/session/invocation, `manual_confirmation`, measurement
plan path, every attempt, pair selections, and replay-receipt path. Every attempt records
its arm, externally assigned session and invocation ids, actual session-receipt path,
mandatory validated RUN binding, Candidate/common-condition digests, outcome, repair
ancestry, usage receipt, and a non-empty inventory of raw evidence. Control Candidate is
null. Failed, excluded, and repaired attempts remain in that list; pairs refer to the
exact attempt ids selected for comparison. A correction is a new attempt and, when
applicable, a new immutable RUN, never a rewrite.

Every path below the evidence or exogenous root is a normalized safe-relative POSIX
path. Absolute paths, `..`, symlinks, missing files, duplicate ids, self-declared
`validation_ok` fields, and pre-existing output paths are rejected. The assembler:

1. runs the full method-catalog and exogenous-registry validators rather than reading a
   generated index or trusting an eligibility flag from the input;
2. reads actual safe regular files; raw evidence, RUN, STUDY, catalog, session receipts,
   and replay receipts use file-byte digests, while parsed measurement plans and usage
   receipts use canonical-JSON digests;
3. derives package costs and clean-pair joins from those inputs;
4. derives an out-of-band source-validation projection from successful catalog, STUDY,
   and direct RUN validator facts, including a canonical digest of each complete RUN
   binding, then binds the source projection's canonical digest into the record;
5. requires a replay receipt from a verifier whose identity, session, and invocation
   differ from the assembler, agent sessions, and RUN runners and whose payload/outcome
   digests close the exact canonical package;
6. passes the assembled record, source-validation projection, and evidence root to the
   runtime validator; and
7. creates a new canonical record atomically only after validation succeeds.

Both `--manual` and `manual_confirmation: true` are required. This is a deliberate
operator stop, not proof that sessions were fresh, independent, or even model-issued.
Distinct strings in the manifest prevent accidental reuse within selected pairs, but do
not authenticate those strings. The public runner requires an actual, distinct
`charting-loop/ai-session-receipt/v1` file for every attempt, including failed and
repaired attempts. Each receipt binds the exact attempt/session/invocation/agent fields;
its issuer values must differ from assembler, agent-session, and RUN-runner values. This
corroborates the declared provenance but is not a signature or proof of freshness. The
independently executed replay verifier must bind that provenance plus the complete
canonical acceptance payload, not merely echo the
manifest's ids.

A selected pair is clean only when builder and treatment are distinct sessions bound to
the same treatment RUN, control is bound to a different task-only RUN, and no session,
attempt, or RUN anywhere in their retained repair lineages is reused by another pair.
All three selected outcomes are `passed`; treatment is
`corridor/method-paper`, control is `task-only/task-only`; treatment/control bind the
same STUDY, task, trial, seed, closed runtime/evaluator conditions, and an explicit
WorldRef comparison projection that excludes only the distinct RUN id (and is neither a
WorldRef nor WorldSpan); and all
Candidate and common-condition joins agree. The builder and treatment share the
treatment RUN but remain separate attempts with separate session receipts and evidence.

Cost reporting uses the complete selected lineages. `corridor_e2e` adds builder and
treatment construction, guided execution, re-entry/revalidation, and retry usage,
including superseded failed attempts. `control_task` reports the control lineage
separately. An incomplete lineage produces null totals plus explicit missing-stage ids,
never a partial total that looks complete. The `execution_only` and amortized values are non-additive secondary views;
they must not be presented as the total Corridor cost. Cached-input and reasoning-
output counts are subsets of input/output, not extra tokens to add.

`instrumented_acceptance_pilot_ready` can become true only after at least two distinct
clean matched pairs and all trusted-input/replay gates pass. It is still a bounded
instrumented pilot claim. `formal_comparison_ready`, `benchmark_result`,
`causal_claim_allowed`, and `adoption_claim_allowed` remain false, and authority remains
`not_assessed`.

## Claim boundary

The checked-in default run establishes only that its declared synthetic records and
joins are deterministic and replayable. Fixture issuer labels do not establish
independent verification, a real live Warranty, or method-level C. The Docker record is
only a sanitized runner-reported observation. Neither establishes lower drift
probability, superiority
over the control, causal effect, long-horizon generalization, hidden-evaluator security,
real-world authority, universal correctness, or method-paper effectiveness. Authority
is explicitly `not_assessed`.
