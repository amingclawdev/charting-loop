# Implementation

Builder-writable Candidate bytes go here, except `GUIDE-CONTRACT.md`: that file is a
runner-owned, read-only control declaration materialized before dispatch. While
`candidate_state=open`, the tree and semantic-closure digests remain null. Freezing
records the entire implementation-tree digest, including the contract, and the
Candidate semantic-closure digest. Editing any frozen semantic byte requires a new
Candidate revision.
