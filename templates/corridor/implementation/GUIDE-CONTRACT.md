# Guide contract

Guide is the deterministic control-plane function:

`Evaluate(Rules, admitted Facts, Position, EvidentialWarranty, AuthorityWarranty) -> Entrance | typed refusal`

Guide evaluates the warranty requirements declared by the assignment and governing
Rule but never mints either warranty. Actor–Role Assignment consumption requires both
warranties to be `live`; `lapsed`, `unknown`, or `not_assessed` yields a stable typed
stale, unauthorized, unknown, or not-assessed refusal. Open Candidate registration is
not gated by those consume-time states.

The same exact inputs and WorldRef must return the same single result. An Entrance pins
the declared facade ID/version/digest, nested interface ID/version/digest/operation,
canonical digest of `argument_mode` plus `opaque_key`, and lookup-scope
ID/version/digest at cardinality one. Its unique allowed-action strings are canonically
digested and exactly joined to one declared action-transition Rule carrying that same
digest. Its WorldRef binds project, run, generation, strict HTTPS repository and
immutable base, environment, raw-ledger prefix, admission receipt/rules, projector
algorithm, and derived state. The runtime owns closed
lookup and source selection; the agent does not. A large file plus open-ended grep,
search, repository browsing, or RAG instruction is semantic pull and is not a
consumable Entrance.

This runner-owned, read-only file declares a control contract and is frozen before the
builder receives an Entrance. Its location inside `implementation/` is physical only;
it is explicitly excluded from the builder-writable surface. Structural validation
checks declarations only: it does not dereference facade/interface/scope pins, prove
invocation, or prove deterministic runtime selection. Keyword screening is auxiliary.
A future real-Candidate profile must bind a GuideReceipt and consume-time verification
to the frozen implementation tree.

The builder may read the materialized Entrance and pinned MethodRef/knowledge inputs,
then modify builder-owned bytes under `implementation/`. The builder must not change
this contract, the task, WorldRef, Direction, role definition or assignment, allowed
actions, canonical action-set digest, action-transition Rule, receipts, certificates,
warranties, or authority evidence. It cannot self-issue either warranty.

Return either a completed implementation or an explicit blocker. Completion is a claim
to be checked; it is not a certificate.
