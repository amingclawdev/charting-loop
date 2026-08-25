# Corridor Kit v5 four-stage local Demo

This deterministic engineering Demo exercises the exact implementation boundary that
failed in CL-151, without using a model, Harbor, a hidden verifier, network access, or
paid compute. It is not a benchmark result and makes no task-performance or causal
claim.

Run it from the repository root:

```bash
python3 demos/corridor-kit-v5-four-stage/run_demo.py
```

The command exits nonzero unless all four stages finish:

1. **Worker compile** — the real v5 assembler accepts the canonical source-witness
   schema and rejects the observed CL-151 aliases (`witness_id`, `witness_class`, and
   `expected_outcome`).
2. **Compile QA** — the real Graph API freezes the candidate and a QA pass establishes
   digest-bound RuleClosure.
3. **Worker implementation** — execution-test probes are frozen before mutation, QA
   reviews them, and the Worker output is frozen, changed, then restored byte-for-byte.
4. **Result QA** — a Fact receipt, final Position, selected Direction, read-only return
   contract, and Graph doctor produce `acceptance_assessed_complete` with no incomplete
   reasons.

The Demo uses a synthetic one-Rule public instruction. It tests protocol wiring and
schema agreement only; it does not assess whether a model can compile or solve a real
task.
