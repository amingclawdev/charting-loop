# Public release checklist

Use this checklist for each exact ref. A prior successful run does not cover a new
commit, branch, task, or visibility decision.

## 1. Freeze identity and scope

- [ ] Record the full typed identity, valid branch locator, full commit, exact commit
      tree, committed manifest path, and recomputed manifest digest.
- [ ] Confirm the release was recreated from a clean custody base rather than merged
      from internal experiment history.
- [ ] List every intended public path and classify every omitted path as embargoed or
      restricted.
- [ ] For benchmark material, record upstream repository, exact commit, license, task
      status, oracle publication status, and the maintainer-clearance disposition:
      `required`, `not-required` with a written rationale, or `pending`. Written
      maintainer clearance is mandatory before publishing solution-bearing or exact
      service/evaluator content. When a release contains only Apache-2.0 public task
      instructions plus non-reconstructive summaries and records authoritative license
      evidence, `not-required` is permitted; a courtesy maintainer notice is recommended
      but non-blocking. A local TaskSet declaration alone is not redistribution
      permission.
- [ ] Confirm the method/study/result version named by the summary is the version that
      actually produced the evidence. Do not transfer an old result to a new method.

## 2. Check contamination and claims

- [ ] Record the evaluated model/version, knowledge cutoff, and network/search policy.
- [ ] Keep same-task executable solution code embargoed while the task remains active,
      unless the benchmark maintainer has approved publication in writing.
- [ ] Review summaries, DB audits, commands, and verifier excerpts for reconstructable
      answer content; a digest label alone does not make content safe.
- [ ] State whether the evidence is descriptive, engineering, method-transfer, or an
      explicitly designed causal result. Do not infer benchmark-wide efficacy from a
      pilot or an incomplete pair.

## 3. Machine checks

Stage the exact candidate, inspect the staged names, and run the checker with an exact
allowlist. Before the release commit, `--allow-dirty` permits inspection of the staged
candidate; it is not sufficient for final readiness.

```sh
git diff --cached --name-status
python3 tools/public_release.py validate-registry --base-ref <public-base-commit>
python3 tools/public_release.py check \
  --ref HEAD \
  --allow-ref HEAD \
  --base-ref <public-base-commit> \
  --allow-dirty
```

After committing, repeat without `--allow-dirty` and name the immutable full commit in
both positions if desired:

```sh
release_commit="$(git rev-parse HEAD)"
python3 tools/public_release.py check \
  --ref "$release_commit" \
  --allow-ref "$release_commit" \
  --base-ref <public-base-commit>
python3 -m unittest discover -s tests -v
```

For the first curated public commit, create a no-parent commit from the allowlisted tree
instead of pushing internal ancestry, then validate the exact root with `--genesis` and
`--base-ref "$release_commit"`. Genesis is accepted only when the registry is empty and
the candidate commit has no parent. A base ref that lacks the registry otherwise fails;
there is no implicit first-run exception.

The internal integration `main` is custody evidence, not the first public candidate.
Its scan is expected to remain `INVALID` when a deleted `.DS_Store` is reachable through
history. Preserve that result: do not relax the scanner, rewrite internal history, or
allowlist the blob away. Publication readiness is decided only from a separately
curated, exact no-parent public root:

```sh
release_commit="$(git rev-parse <public-root-ref>)"
test "$(git rev-list --parents -n 1 "$release_commit" | wc -w | tr -d ' ')" = "1"
python3 tools/public_release.py check \
  --ref "$release_commit" \
  --allow-ref "$release_commit" \
  --base-ref "$release_commit" \
  --genesis
```

The checker scans the exact Git index, the selected ref tree, and every named blob
reachable from that ref. It rejects nested Git/submodules, bundles and packs, archives,
databases and SQL, raw sessions/logs/trajectories, solution-shaped paths, hidden
evaluator material, host-local paths, credential-shaped values, hidden-reasoning
structures, oversized blobs, and unclassified/binary blobs. `.gitignore` is only a
convenience layer and never substitutes for this scan.

## 4. Human review and authorization

- [ ] A reviewer independent of the artifact builder freshly checks the exact no-parent
      public-root commit and the sealed/public classification. Internal passes and
      earlier reviews do not cover this root.
- [ ] Preserve historical bypasses, waivers, and failed close attempts as their original
      evidence. Do not replay or upgrade them into a `PASS` for the public root.
- [ ] License, `THIRD_PARTY_NOTICES.md`, citation metadata, and security reporting text
      cover the actual bytes.
- [ ] Published summaries include failed, blocked, invalid, timeout, and unscored
      attempts rather than presenting a selected success subset.
- [ ] All sealed artifacts have content digests, sizes, provenance, custody location,
      and an explicit release trigger; their bytes are absent from every pushed ref.
- [ ] The repository owner explicitly authorizes the exact remote and refs. Validation
      does not authorize a push.
- [ ] The immutable public-root scan has zero warnings. A known deleted `.DS_Store` in
      internal ancestry may explain why an internal integration ref is not publishable;
      it is never an exception for the curated public root.

If any item fails, stop the publication. Preserve the failed check as local audit
material, correct the candidate in a new commit, and rerun the entire checklist.
