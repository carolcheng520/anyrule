#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate_rule_repository as validator  # noqa: E402


class RuleRepositoryValidationTest(unittest.TestCase):
    def test_current_repository_is_valid(self) -> None:
        self.assertGreater(len(validator.validate_repository()), 0)

    def test_duplicate_and_count_mismatch_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "rules").mkdir()
            (root / "mitm").mkdir()
            path = root / "rules" / "fixture.arrs"
            path.write_text(
                "# PURPOSE: Fixture.\n"
                "# LINK: https://raw.githubusercontent.com/carolcheng520/anyrule/main/rules/fixture.arrs\n"
                "# LAST-UPDATED: 2026-07-11\n"
                "# SUGGESTED-ACTION: DIRECT\n"
                "# RULES: 2\n\n"
                "name = Fixture\n"
                "2, example.com\n"
                "2, example.com\n",
                encoding="utf-8",
            )
            old_root = validator.ROOT
            validator.ROOT = root
            try:
                with self.assertRaises(validator.ValidationError):
                    validator.validate_file(path)
            finally:
                validator.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
