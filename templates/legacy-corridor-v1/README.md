# Corridor artifact skeleton

Copy this directory as a clean, runner-owned experiment envelope. Do not give the whole
directory to the builder. Replace every template identity, materialize only the closed
`INPUTS.json.builder_view` plus an empty writable `corridor/` in a separate no-`.git`
builder workspace, let the runner populate the interaction log, and update all SHA-256
values at candidate freeze.

From the repository root, materialize the builder workspace with:

```bash
python3 tools/corridor_registry.py prepare-builder templates/corridor PATH/TO/NEW-WORKSPACE
```

Canonical files:

```text
CORRIDOR.json
inputs/INPUTS.json         exact builder-visible input inventory
corridor/                 implementation
authority/
  AUTHORITY.json          actors, scopes, capture declaration
  DESIGN.md               common authority-study design
  CONDITION.md            frozen assigned authority-input protocol
  interactions.jsonl      complete visible build/authority exchange
  events.jsonl            explicit exogenous-authority acts
trace/                    runner-captured execution evidence
  FIRST-TRAVERSAL.json    structured first-attempt evidence when attempted
  scenarios/S1.json...   label-free pre-adjudication scenario observations
evaluation/               subject diagnoses, independent assessment, final result
```

This checked-in copy is marked `template: true`; it demonstrates the contract but cannot
be entered in the registry. Check its internal consistency with:

```bash
python3 tools/corridor_registry.py validate-corridor templates/corridor --allow-template
```
