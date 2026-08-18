# Public release branches

This protocol defines repository custody and publication layout. It does not add a
rule to the Corridor method, qualify an experiment, or change an existing result.
`method-paper/METHOD.md` remains the sole normative method source.

## Deterministic namespaces

Every public release record names one exact full commit and tree under one namespace:

| kind | branch template | default visibility | purpose |
|---|---|---|---|
| custody | `main` | `public-summary` | method, protocol, indexes, citation, licensing, and validation tools |
| Corridor artifact | `corridor/<dataset>/<release>/<taskset>/<task>/<construction>/<build>/<candidate>/<revision>` | `embargoed-solution-bearing` | one task-conditioned Corridor package; never a cross-task dumping branch |
| result | `results/<dataset>/<release>/<taskset>/<task>/<study>/<run>/<arm>/<result-release>` | `public-summary` | immutable, sanitized summaries and digests for one study result release |

Each placeholder is a lowercase slug containing letters, digits, dots, or hyphens.
Branch names are navigation aids, not identity authority. A non-custody release row has
a closed `identity` object covering benchmark dataset/release/taskset/task,
method/protocol/study, construction/build/candidate/revision, and
launch/attempt/run/arm/result-release. Fields not applicable to that artifact are null;
the fields required by its branch kind are concrete. The authoritative tuple is that
typed identity plus the recorded full commit, exact commit tree, committed manifest
path and digest, and immutable registry row.

No two rows may reuse a release id, branch locator, or full typed identity. A locator
must be a valid Git ref and its path projection must exactly match the corresponding
identity fields. A correction changes the relevant revision or result-release field,
uses a new ref and release row, and points `supersedes_release_id` at the earlier row.

The namespaces scale by adding a task or study segment. A new task does not alter an
older branch, and a new dataset version does not rewrite an earlier result branch.
Corrections are new commits and new registry rows with an explicit `supersedes` link.

## Four publication states

The default is `restricted-on-request`. Classification is per artifact, not per
repository:

1. **`public-summary`** includes method and protocol text, citations and notices,
   deterministic indexes, aggregate or per-attempt scores, timing/token summaries,
   typed QA outcomes, claim limitations, and content digests of sealed material.
2. **`embargoed-solution-bearing`** includes task-specific solution code, executable services,
   writeback SQL, decoded or final databases, detailed agent logs, and trajectories.
   It may be released only after task retirement or written benchmark-maintainer
   approval, and then only through a new audited release row.
3. **`restricted-on-request`** includes credentials, private data, hidden evaluator bytes,
   unrelated account history, and internal Git/runtime history. It is never copied to
   a public branch. Requestability describes custody, not a promise of disclosure.
4. **`public-after-retirement-or-maintainer-clearance`** is a transition state allowed
   only when the task is retired or written maintainer clearance is recorded in a new
   row. It never changes an older row in place.

`STUDY-RESULT`, `DB-AUDIT`, or `MANIFEST` is not automatically safe merely because it
is a summary-shaped file. Rows, queries, assertions, commands, or paths that reconstruct
a solution remain embargoed. A public summary must be reviewed for reconstruction and
benchmark-contamination risk.

## Reproducibility modes

**Method-transfer replication** is the public default: another team freezes an unseen
task and method identity, then uses its own builder to construct a fresh Corridor.
This tests whether the method transfers without publishing a reusable same-task answer.

**Exact-service replay** tests an existing executable package. For an active benchmark
task it remains embargoed or is shared with a maintainer or independent adjudicator
under controlled access. Exact replay and method transfer answer different questions
and must not be combined into one claim.

## Contamination and claim boundary

The official oracle's publication date, any additional implementation's first public
date, the evaluated model/version, its knowledge cutoff, and network/search policy are
separate facts. A model failure on an already-public oracle is useful negative evidence
against simple memorization; it is not proof that memorization was impossible.

Publishing a new task-specific solver does not retroactively invalidate a completed
run. It does make later open-internet runs on the same task potentially contaminated.
Release records therefore classify contamination and default to descriptive claims.
Causal, benchmark-wide, production, or generalization claims require a prospectively
frozen design and evidence beyond a release checklist.

## Curated release sequence

1. Start from the intended clean custody commit. Do not sanitize an internal branch by
   deleting files at its tip; deleted objects remain reachable history.
2. Recreate public commits from the allowlisted source material. Never merge or push an
   internal experiment history into a public namespace.
3. Build the result summary deterministically. Its outcome object explicitly counts
   pass, fail, blocked, invalid, timeout, and unscored attempts. Record every sealed
   artifact's digest, byte size, media type, license status, custody, and release
   trigger, plus provenance and source ref, without copying the sealed bytes. A
   public-after transition also records the applicable retirement or maintainer-
   clearance evidence ref.
4. Stage the exact candidate tree, run `tools/public_release.py check` with an explicit
   ref allowlist, then commit and repeat the check against the immutable commit.
5. Obtain independent content review and explicit owner authorization. Machine success
   is necessary but never permission to publish.
6. Append one immutable row to `exogenous/registry/PUBLIC-RELEASES.json`; never update an
   old row in place.

The current registry contains fourteen public-summary rows. Twelve are the immutable
v1/v2 Treatment and Control releases for CL-030, CL-031, and CL-032: six current arm
releases from three repetitions of one benchmark task, not six distinct-task results.
The remaining two are append-only versions of the separate Corridor-assisted
engineering release for `ico-path-patch` job 009. Its `public-v2` supersedes but does
not mutate `public-v1`, adding a minimized frozen snapshot of Harbor's public trial
table. The run has no matched Control and is not a causal-evidence arm.
Every row points to a sanitized result branch; controlled source bytes remain sealed
behind recorded digests.
