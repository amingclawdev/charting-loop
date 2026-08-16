# Author provenance catalog

This directory records method-author provenance. It is not a participant log, an
authority ledger, a run registry, or empirical evidence.

- `SOURCES.json` pins source artifacts.
- `CLAIMS.json` classifies method claims and their falsification boundaries.
- `EVIDENCE-INDEX.json` joins claims to sources without copying task/run/score data.

Participant and evaluator data belong under `exogenous/`. Optional user–AI or authority
logs never become author provenance merely because they informed a later study.

`validate-method` parses all three JSON documents with strict JSON/schema checks,
requires unique claim/source identities, resolves every binding exactly once, and
rejects orphan claims. External source bytes remain pinned but unresolved unless a
separate exact-checkout resolver is supplied; the validator reports that status as a
fact rather than implying byte verification.
