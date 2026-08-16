# Optional evidence

This directory is a pointer boundary only. It may hold a local consent or reference
manifest in a future strict profile, but it must not contain raw authority exchanges,
user–AI logs, attachments, or study diagnostics. Public opaque attachment bodies belong
under `exogenous/runs/<run-id>/attachments/`; private bodies belong in ignored
`exogenous/local/`.

The directory is not part of the Candidate implementation tree or semantic identity,
and the draft validator does not read it. Absence means `not_assessed`. The draft v2
template has no strict optional-evidence profile, so its manifest validator rejects
every non-null `authority_evidence` value.
