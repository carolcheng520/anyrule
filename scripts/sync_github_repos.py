#!/usr/bin/env python3
"""Compatibility entrypoint for the canonical anywhere-ops repository sync."""

from __future__ import annotations

import os
import sys
from pathlib import Path


TARGET = Path(__file__).resolve().parents[2] / "anywhere-ops" / "scripts" / "maintenance" / "sync_repositories.py"


def main() -> int:
    if not TARGET.is_file():
        print(f"Canonical sync entrypoint is missing: {TARGET}", file=sys.stderr)
        return 1
    os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
