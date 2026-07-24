# AnyRule

Personal MITM and companion REJECT rule sets for Anywhere, together with the
offline generator and validators that keep generated rules reproducible.

## Repository layout

- `rules/`: reviewed companion REJECT rule sets.
- `mitm/`: MITM rules. `TencentSportsAdBlock.amrs` is generator-owned; other
  files are reviewed and maintained manually.
- `scripts/`: the Tencent Sports generator, offline tests, and repository
  validation.
- `skill/`: a policy-free compatibility entrypoint for the canonical
  `anywhere-ops` control plane.

Do not hand-edit generator-owned output. Update its source inputs or generator,
run the tests, then regenerate the file.

## Local verification

```bash
PYTHONPYCACHEPREFIX=/private/tmp/anyrule-pycache \
  python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/validate_rule_repository.py
python3 scripts/sync_github_repos.py --self-test
PYTHONPYCACHEPREFIX=/private/tmp/anyrule-pycache \
  python3 -m py_compile scripts/*.py
git diff --check
```

The periodic maintainer updates only `mitm/TencentSportsAdBlock.amrs`.
Five-repository synchronization and formal-App diagnostics remain separate
`anywhere-ops` operations. The maintainer does not stash, clean, rebase,
force-push, or automatically reset owned repositories.
