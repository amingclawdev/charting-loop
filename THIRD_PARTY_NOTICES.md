# Third-party notices

Project-authored repository material is licensed under Apache License 2.0. The
following benchmark inputs retain their upstream provenance. A TaskSet license field is
not, by itself, proof that every upstream byte at the pinned commit may be redistributed.

## Terminal-Bench 3.0 production-planning input

- Upstream: `https://github.com/harbor-framework/terminal-bench`
- Pinned commit: `2b0442c3c583b710ca8da14c8e601b99f2f1f244`
- Local custody: `exogenous/benchmarks/terminal-bench/3.0/`
- Local TaskSet declaration: Apache-2.0
- The original pinned tree does not contain a root license file. Independent current
  upstream evidence was therefore checked at commit
  `d435a67e30ecb41f916716607c30c4646f208ee6`: its root `LICENSE` is Apache-2.0 with
  SHA-256 `sha256:c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`, and its
  `tasks/production-planning/instruction.md` has SHA-256
  `sha256:b4e85ed8bc8e9f5ea093ae6b144ea8b66c085a585d32bfef6917eef61022e702`, exactly
  matching the local vendored instruction.
- Evidence URLs:
  `https://github.com/harbor-framework/terminal-bench/blob/d435a67e30ecb41f916716607c30c4646f208ee6/LICENSE`
  and
  `https://github.com/harbor-framework/terminal-bench/blob/d435a67e30ecb41f916716607c30c4646f208ee6/tasks/production-planning/instruction.md`.

The local TaskSet records content digests and identifies which public task instruction
was vendored. It does not redistribute the task's solution, environment tree, or
evaluator tree.

## Terminal-Bench 2.1 cobol-modernization input

- Upstream: `https://github.com/harbor-framework/terminal-bench-2-1`
- Pinned commit: `7131e4375048a0e408a8fb404b5f499d726b695b`
- Local custody: `exogenous/benchmarks/terminal-bench/2.1/`
- Local TaskSet declaration: Apache-2.0
- Upstream license evidence: `LICENSE` at the pinned commit,
  `https://github.com/harbor-framework/terminal-bench-2-1/blob/7131e4375048a0e408a8fb404b5f499d726b695b/LICENSE`
- License blob SHA-256: `sha256:c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`

The benchmark names belong to their respective owners. Inclusion is for research
provenance and does not imply endorsement. Before adding or publishing another vendored
task, record its exact source commit and an authoritative license URL/blob digest. If
that evidence is absent, keep the bytes out of the public tree and publish only the
upstream reference and local content digest.
