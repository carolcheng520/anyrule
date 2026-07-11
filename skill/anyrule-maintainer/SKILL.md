---
name: anyrule-maintainer
description: "Compatibility entrypoint for the canonical AnyRule four-repository maintenance skill now owned and installed from the sibling anywhere-ops repository."
---

# AnyRule Maintainer Compatibility Entry

The canonical skill, installer, repository inventory, and orchestration now live
in the sibling private `anywhere-ops` repository. This directory is retained for
one migration cycle and contains no maintenance policy.

Install the canonical skill from `anywhere-ops`:

```bash
cd ../anywhere-ops
python3 skill/install_anyrule_maintainer.py --replace
```

Existing direct invocations continue to delegate to the canonical control
plane:

```bash
python3 skill/anyrule-maintainer/scripts/run_anyrule_maintenance.py --check-only
```

The delegated workflow never resets, cleans, rebases, stashes, or force-pushes
the managed `anyrule` and `anywhere-ops` repositories.
