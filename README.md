# AnyRule

Personal routing and MITM rule sets for Anywhere, together with the offline
generators and validators that keep generated rules reproducible.

## Repository layout

- `rules/`: routing rule sets. Files such as `direct-app.arrs` are maintained
  manually; `geosite-cn-direct-delta.arrs`, `geoip-cn-ipv6.arrs`, and
  `wechat.arrs` are generator-owned.
- `mitm/`: MITM rules. `TencentSportsAdBlock.amrs` is generator-owned; other
  files are reviewed and maintained manually.
- `scripts/`: generators, offline tests, and repository validation.
- `skill/`: a temporary compatibility copy of the AnyRule maintainer skill.
  The canonical four-repository control plane is moving to the sibling private
  `anywhere-ops` repository.

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

The periodic four-repository maintenance workflow is intentionally strict: it
does not stash, clean, rebase, force-push, or automatically reset managed
repositories.
