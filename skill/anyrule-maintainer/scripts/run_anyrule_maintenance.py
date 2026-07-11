#!/usr/bin/env python3
"""Compatibility entrypoint delegating to the canonical anywhere-ops control plane."""

from __future__ import annotations

import os
import sys
from pathlib import Path


TARGET = Path(__file__).resolve().parents[4] / "anywhere-ops" / "scripts" / "maintenance" / "maintain_anyrule.py"


if __name__ == "__main__":
    if not TARGET.is_file():
        print(f"Canonical maintainer is missing: {TARGET}", file=sys.stderr)
        raise SystemExit(1)
    os.execv(sys.executable, [sys.executable, str(TARGET), *sys.argv[1:]])
