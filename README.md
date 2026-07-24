# AnyRule

Personal MITM and companion REJECT rule sets for Anywhere, together with the
offline generator and validators that keep generated rules reproducible.

## Repository layout

- `rules/`: reviewed companion REJECT rule sets.
- `mitm/`: MITM rules. `TencentSportsAdBlock.amrs` is generator-owned; other
  files are reviewed and maintained manually.
- `scripts/`: the Tencent Sports generator, offline tests, and repository
  validation.

Do not hand-edit generator-owned output. Update its source inputs or generator,
run the tests, then regenerate the file. The generator accepts only a local
upstream checkout plus its full revision; network access, reviewed source
hashes, commits, and publication belong to the sibling `anywhere-ops` control
plane.

## Local verification

```bash
PYTHONPYCACHEPREFIX=/private/tmp/anyrule-pycache \
  python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/validate_rule_repository.py
PYTHONPYCACHEPREFIX=/private/tmp/anyrule-pycache \
  python3 -m py_compile scripts/*.py
git diff --check
```

The periodic maintainer updates only `mitm/TencentSportsAdBlock.amrs`.
Repository synchronization, reviewed upstream hashes, and publication are
separate `anywhere-ops` operations. The maintainer does not stash, clean,
rebase, force-push, or automatically reset owned repositories.
