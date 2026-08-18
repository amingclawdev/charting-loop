---
name: Corridor replication report
about: Report any outcome from a fresh matched Corridor pilot
title: "[replication] <task or domain>"
labels: ""
assignees: ""
---

Use this template for a completed, null, negative, blocked, timeout, invalid, or
unscored pilot. This is the Charting Loop project's research intake. It is **not** a
Harbor upload, official benchmark submission, accepted result, or leaderboard entry.

Before submitting:

- [ ] The task was fresh and unseen by the builder and task roles, or I mark the report
      as same-task/adaptive rather than independent replication.
- [ ] Treatment Worker and Treatment QA used the same exact frozen Corridor.
- [ ] Control Worker and Control QA had no Corridor access.
- [ ] I included every attempt and did not discard an unfavorable outcome.
- [ ] I did not paste credentials, tokens, private paths, raw sessions, private
      reasoning, complete trajectories, hidden evaluator material, databases,
      writeback SQL, detailed logs, or a solution-bearing service.

## Report classification

- Distinct task name and release:
- Report class: independent fresh-task pilot / same-task repetition / adaptive
  engineering run / other
- Overall status: completed / null / negative / blocked / timeout / invalid / unscored
- Date and report author:

## Exact frozen identities

- Task and evaluator commit/digest:
- Starter repository commit:
- Method version, source commit, Method digest, and Scope Datum digest:
- Corridor commit/tree/digest:
- Model, effort, agent/runtime, container/image, and dependency identities:
- Total arm-time constraint, compute limits, network policy, and QA instruction digest:
- Preregistration or frozen analysis-plan locator/digest:

## Intended arm difference

State how you verified that both Treatment roles could use the exact frozen Corridor,
both Control roles could not, and all other declared conditions were matched.

## All attempts

| Attempt | Arm | Worker status/score | QA status | Final official score | Wall time | Model/API cost | Compute cost | Counted? Why? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | Treatment / Control |  |  |  |  |  |  |  |

## Builder and Corridor construction

- Builder inputs and exclusions:
- Construction wall time, model/API cost, and compute cost:
- Freeze identity and time:
- Reusable base modules versus task-specific modules:

## Observable mechanism and QA evidence

- Evidence that Treatment Worker consumed the Corridor:
- Evidence that Treatment QA consumed the same Corridor:
- Evidence that Control roles had no Corridor access:
- QA finding, witness, decision, and any bounded rework:
- What changed—or did not change—after QA:

## Contamination, network, and custody

- Prior exposure to this task or verifier feedback:
- Network access and external sources used:
- Hidden-test or evaluator exposure:
- Sealed artifacts retained, custodial locator, and content digests:
- Redactions and why they were necessary:

## Result and limits

- Smallest evidence-supported conclusion:
- Alternative explanations or validity threats:
- What this report does **not** establish:
- Optional official benchmark/Harbor URL and acceptance status (if independently
  obtained; do not infer it from this issue):
