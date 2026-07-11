#!/usr/bin/env python3
"""Compatibility installer delegating to the canonical anywhere-ops skill."""

from __future__ import annotations

import os
import sys
from pathlib import Path


TARGET = Path(__file__).resolve().parents[2] / "anywhere-ops" / "skill" / "install_anyrule_maintainer.py"


if __name__ == "__main__":
    if not TARGET.is_file():
        print(f"Canonical installer is missing: {TARGET}", file=sys.stderr)
        raise SystemExit(1)
    os.chdir(TARGET.parents[2])
    os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])
