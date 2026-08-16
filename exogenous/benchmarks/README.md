# Benchmarks

Legacy v1/v2 benchmark releases store one `TASKSET.json` at
`benchmarks/<benchmark-id>/<release>/`. Versioned v3 variants live at
`benchmarks/<benchmark-id>/<release>/tasksets/<taskset-id>/TASKSET.json`, allowing one
upstream release to retain multiple immutable constraint profiles without rewriting a
historical TaskSet. Every version pins the exact task bytes or immutable external
reference, environment, evaluator, license, and ordered task-list digest.
