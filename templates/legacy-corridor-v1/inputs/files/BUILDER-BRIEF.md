# Reference build brief v1

Build a governance mechanism for a small software-change pipeline so that a work item's
journey from proposal to closed is decidable by machine rather than by reading prose.

You are given an empty workspace and three simulated workers that will submit changes.
You may design any solution.

The solution must:

1. accept work items, each naming what should change and what would count as finished;
2. dispatch a work item to a worker;
3. accept or reject the worker's submission and expose the reason in a form another
   program can consume;
4. close a work item and later answer on what basis it was closed.

Deliver a running implementation plus instructions a third party can follow without
asking you anything. The runner will freeze and evaluate it separately.

Implementation details not stated above are deliberately unconstrained.
