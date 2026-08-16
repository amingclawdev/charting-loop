# v2 Candidate builder boundary

The builder may change only the declared Candidate implementation surface and explicit
builder-owned declarations. `implementation/GUIDE-CONTRACT.md` is a runner-owned,
read-only carve-out even though it is physically inside that subtree. Preserve that
contract plus the runner-frozen Rule/Fact inputs, Guide result, Position, Direction,
WorldRef, method reference, unique allowed-action set, canonical action-set digest, and
exact declared action-transition Rule. Preserve the pinned facade/interface identity
and operation, argument digest, lookup-scope identity/digest, and cardinality.

- Do not create, edit, infer, or backfill runner/evaluator traversal receipts.
- Do not self-issue a PathCertificate, EvidentialWarranty, or AuthorityWarranty.
- Do not reconstruct optional authority evidence or user–AI logs. If absent, their
  status is `not_assessed` or `unknown`, never approved.
- Invoke only the declared interface operation with the exact digested bounded arguments
  and closed single-result lookup scope.
- Do not navigate outside the bounded Entrance or choose sources through grep, search,
  RAG, repository browsing, or another agent-side discovery step.
- Completion reports implementation or a blocker only. Building and freezing a
  Candidate do not certify it or place any scope in C.
