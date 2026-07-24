#!/usr/bin/env python3
"""Deprecated compatibility entrypoint for the canonical anywhere-ops maintainer."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


UPSTREAM_URL = "https://github.com/Hey-sayiwanna/TencentSports-Surge.git"
REVIEWED_UPSTREAM_SHA256 = {
    "TencentSportsAdBlock.sgmodule": "4987d3d24b0947366e950cbfe06b5d4aecd61b6c6bd258d9fe8a354c0615da75",
    "TencentSportsAdBlock.js": "07ce795cb38bbfc77d771c1eefbb70577d49e44d44c071e27b09dd05bad62427",
    "TencentSportsFloatBlock.js": "e62e26451ab1f2107d054ab9b311fcdbd13edb3ddedadcec6ef130b3cf9c291f",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-commit", action="store_true")
    args = parser.parse_args()
    if not args.no_commit:
        parser.error("direct publication was retired; use the canonical anywhere-ops maintainer")

    print(
        "warning: compatibility path is deprecated; update anywhere-ops before the next run",
        file=sys.stderr,
    )
    with tempfile.TemporaryDirectory(prefix="tencent-sports-compat-") as tmpdir:
        source = Path(tmpdir) / "TencentSports-Surge"
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", UPSTREAM_URL, str(source)],
            check=False,
        )
        if clone.returncode:
            return clone.returncode
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        for filename, expected in REVIEWED_UPSTREAM_SHA256.items():
            actual = sha256(source / filename)
            if actual != expected:
                print(
                    f"error: unreviewed upstream {filename}: expected {expected}, got {actual}",
                    file=sys.stderr,
                )
                return 1
        generator = Path(__file__).with_name("generate_tencent_sports_mitm.py")
        return subprocess.run(
            [
                sys.executable,
                str(generator),
                "--source-dir",
                str(source),
                "--source-revision",
                revision,
            ],
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
