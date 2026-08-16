# Security and sensitive benchmark material

This repository is a research preview. Only the current default branch is maintained;
there is no support or response-time guarantee.

Do not open a public issue containing credentials, private data, hidden evaluator
material, an active benchmark solution, detailed agent logs, raw sessions, trajectories,
database contents, or host-local paths. When the repository is hosted on GitHub, use
the repository's private security-advisory form. If that channel is unavailable,
contact the repository owner through an established private channel and include only a
minimal description until a secure transfer method is agreed.

Useful reports identify the affected full commit, path or checker rule, impact, and a
minimal reproduction that contains no secret or restricted bytes. Remove credentials
from any pasted command output and rotate an exposed credential before reporting it.

The maintainers may remove public refs while reviewing a report. Removing a branch is
not proof that its objects were never fetched; credential rotation and benchmark
contamination assessment remain necessary. Do not attempt to validate a report by
accessing accounts, hidden tests, or systems beyond those you are authorized to use.

`tools/public_release.py` is a defense-in-depth release check, not a secret scanner with
complete coverage and not permission to publish. Human review and explicit release
authorization remain required.
