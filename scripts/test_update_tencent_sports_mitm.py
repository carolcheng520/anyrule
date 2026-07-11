#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import update_tencent_sports_mitm as updater  # noqa: E402


class TencentSportsUpdaterTest(unittest.TestCase):
    def test_generator_reproduces_current_rule(self) -> None:
        target = updater.repo_root() / updater.TARGET_RELATIVE
        candidate = updater.generate_candidate(target)
        self.assertEqual(candidate, target.read_text(encoding="utf-8"))
        updater.validate_amrs(candidate)

    def test_unreviewed_upstream_fixture_is_rejected_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for name in updater.REVIEWED_UPSTREAM_SHA256:
                (root / name).write_text("drifted fixture\n", encoding="utf-8")
            with self.assertRaises(updater.UpdateError) as raised:
                updater.require_supported_upstream(root)
        self.assertIn("unreviewed upstream", str(raised.exception))

    def test_invalid_base64_and_rule_count_are_rejected(self) -> None:
        candidate = updater.build_amrs("2026-07-11")
        broken = candidate.replace("# RULES: 10", "# RULES: 11", 1)
        with self.assertRaises(updater.UpdateError):
            updater.validate_amrs(broken)


if __name__ == "__main__":
    unittest.main()
