# Theory version catalog

`VERSIONS.json` is the machine-readable catalog of theory artifacts that a corridor or
experiment may cite. A version identity includes the source commit and the exact bytes
of a named representation; a label such as `v5` is descriptive, not sufficient.

The current catalog uses `charting-loop/theory-index/v2`. It identifies the exact
[Zenodo v1 record](https://doi.org/10.5281/zenodo.21844624) and deposited PDF as the
single `published-primary` theory source. Later internal drafting bytes may be recorded
as `consulted-drafting`, but cannot replace that public primary or silently acquire its
publication status. The concept DOI is discovery metadata only; exact references use
the version DOI and byte digest.

The validator still reads `charting-loop/theory-index/v1` catalogs under their legacy
semantics. A legacy catalog remains usable by the legacy method-provenance join, but it
does not retroactively assert the publication roles introduced by v2.

The current source repository has no configured remote URL. Public identity is therefore
established by the Zenodo record plus the exact deposited bytes, while the local Git
commit provides a reproducible source resolver. The default validator checks catalog
structure and reference equality without inventing a remote. When a trusted source
checkout is available, the same program can also resolve the commit, read every
representation directly from Git, and recompute its blob ID and byte-level SHA-256:

```sh
python3 tools/corridor_registry.py validate-theory
python3 tools/corridor_registry.py validate-theory --source-root ../drift-gym
```

The catalog says `repository_url: null`; CI cannot perform the Git-resolving form until
the source is vendored or a trusted checkout is made available. This does not weaken the
public DOI identity, but CI must report local source resolution separately from public
publication provenance.
