---
name: Scenario report (15 minutes, no building required)
about: Run the six scenarios against a system you already have
title: "[scenarios] <your system in a few words>"
labels: scenario-report
---

You do not need to build a corridor or read the papers to file this. Run the six scenarios
in `reference-task/TASK.md` against a pinned version of whatever you already use to run
agents: a framework, scripts, or a CI pipeline. Report what happened. This is an
observational `external-system` report, not a controlled arm.

**Failures are the point.** A report where five of six fail is worth more than one where
all six pass, because it tells us where real systems actually break.

## Your setup
- What runs your agents:
- Exact version, commit, or release:
- Model(s):
- Runtime and web-access state:
- Was later user authority input allowed? bootstrap-only / interactive / unknown:
- Roughly how long it has been in use:
- Date:

## Results

| # | Scenario | Outcome | What actually happened |
|---|---|---|---|
| S1 | worker reports done, change never applied | pass / fail / blocked | |
| S2 | "what counts as finished" edited after dispatch | pass / fail / blocked | |
| S3 | two items modify the same file | pass / fail / blocked | |
| S4 | legitimate submission, no legal next step exists | pass / fail / blocked | |
| S5 | old acceptance, the check it relied on has since changed | pass / fail / blocked | |
| S6 | worker proposes a good change to the acceptance rules | pass / fail / blocked | |

## Anything that surprised you
