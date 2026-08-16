# Frozen subject-diagnosis prompt v1

Assess exactly one frozen scenario trace. You may use only:

1. the named `trace/scenarios/Sn.json` bytes;
2. the knowledge treatment assigned to this run; and
3. this prompt.

Do not infer an adjudicated label from a filename, prior result, evaluator output, or
another scenario. Return one `subject-diagnosis` JSON record conforming to the corridor
assessment schema. Choose `drift`, `no-drift`, or `abstain`. Populate a factor
classification for a `drift` verdict only when the assigned knowledge treatment itself
defines applicable factor codes; this prompt does not define their meaning. A `drift`
without such a supported classification uses `not-classifiable` and an empty factor
list. A `no-drift` verdict uses `not-assessed` and an empty factor list. An `abstain`
verdict uses `not-classifiable` and an empty factor list. Cite the exact scenario evidence
digest and state the theory version actually visible to you, or `null` if none was
supplied.

Do not claim that your diagnosis is independently warranted or externally authorized.
