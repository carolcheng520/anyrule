#!/usr/bin/env python3
"""Install the repo-local AnyRule maintainer skill for Codex discovery."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SKILL_NAME = "anyrule-maintainer"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_github_repos as repository_inventory


MAIN_BRANCH = repository_inventory.MAIN_BRANCH
RepoSpec = repository_inventory.RepoSpec
repo_specs = repository_inventory.repo_specs
REQUIRED_INVENTORY_VERSION = 2


class InstallError(Exception):
    pass


def run_git(path: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or f"exit code {result.returncode}"
        raise InstallError(f"{path}: git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def anyrule_root() -> Path:
    return ROOT


def validate_repo(repo: RepoSpec) -> None:
    if not repo.path.is_dir():
        raise InstallError(
            f"{repo.name}: missing repository directory {repo.path}\n"
            f"Clone it beside anyrule with: git clone {repo.origin_url} {repo.path}"
        )

    top_level = Path(run_git(repo.path, ["rev-parse", "--show-toplevel"])).resolve()
    if top_level != repo.path.resolve():
        raise InstallError(f"{repo.name}: expected repo root {repo.path}, found {top_level}")

    branch = run_git(repo.path, ["branch", "--show-current"])
    if branch != MAIN_BRANCH:
        raise InstallError(f"{repo.name}: expected branch {MAIN_BRANCH}, found {branch or 'detached HEAD'}")

    origin_url = run_git(repo.path, ["remote", "get-url", "origin"])
    if origin_url != repo.origin_url:
        raise InstallError(f"{repo.name}: expected origin {repo.origin_url}, found {origin_url}")


def codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base / "skills"


def install_symlink(skill_dir: Path) -> Path:
    target = codex_skills_dir() / SKILL_NAME
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        current = target.resolve()
        if current == skill_dir.resolve():
            return target
        target.unlink()
    elif target.exists():
        raise InstallError(
            f"{target} already exists and is not a symlink; move it aside before installing"
        )

    target.symlink_to(skill_dir.resolve(), target_is_directory=True)
    return target


def main() -> int:
    root = anyrule_root()
    if Path.cwd().resolve() != root.resolve():
        print(f"Run this installer from the anyrule repository root: {root}", file=sys.stderr)
        return 1

    actual_version = getattr(repository_inventory, "REPOSITORY_INVENTORY_VERSION", 0)
    if actual_version != REQUIRED_INVENTORY_VERSION:
        print(
            f"Install failed: repository inventory version {actual_version} is incompatible with "
            f"installer version {REQUIRED_INVENTORY_VERSION}",
            file=sys.stderr,
        )
        return 1

    skill_dir = root / "skill" / SKILL_NAME
    if not (skill_dir / "SKILL.md").is_file():
        print(f"Missing skill directory: {skill_dir}", file=sys.stderr)
        return 1

    try:
        for repo in repo_specs(root):
            validate_repo(repo)
        link = install_symlink(skill_dir)
    except InstallError as exc:
        print(f"Install failed: {exc}", file=sys.stderr)
        return 1

    print(f"Installed {SKILL_NAME}: {link} -> {skill_dir.resolve()}")
    print("Open a new Codex session if the skill list was already loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
