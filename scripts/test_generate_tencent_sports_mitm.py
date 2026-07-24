#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_tencent_sports_mitm as generator  # noqa: E402


SOURCE_REVISION = "aad85d3669ababee8d64cd6e245b6d0546250bd0"
SOURCE_HASHES = {
    "TencentSportsAdBlock.sgmodule": "4987d3d24b0947366e950cbfe06b5d4aecd61b6c6bd258d9fe8a354c0615da75",
    "TencentSportsAdBlock.js": "07ce795cb38bbfc77d771c1eefbb70577d49e44d44c071e27b09dd05bad62427",
    "TencentSportsFloatBlock.js": "e62e26451ab1f2107d054ab9b311fcdbd13edb3ddedadcec6ef130b3cf9c291f",
}


class TencentSportsUpdaterTest(unittest.TestCase):
    def test_generator_reproduces_current_rule(self) -> None:
        target = generator.repo_root() / generator.TARGET_RELATIVE
        candidate = generator.generate_candidate(
            target,
            SOURCE_REVISION,
            SOURCE_HASHES,
        )
        self.assertEqual(candidate, target.read_text(encoding="utf-8"))
        generator.validate_amrs(candidate)

    def test_missing_and_unsupported_upstream_fixture_is_rejected_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            with self.assertRaises(generator.UpdateError) as missing:
                generator.require_supported_upstream(root)
            self.assertIn("missing upstream", str(missing.exception))
            for name in generator.UPSTREAM_FILES:
                (root / name).write_text("unsupported fixture\n", encoding="utf-8")
            with self.assertRaises(generator.UpdateError) as unsupported:
                generator.require_supported_upstream(root)
            self.assertIn("hostname", str(unsupported.exception))

    def test_invalid_base64_and_rule_count_are_rejected(self) -> None:
        candidate = generator.build_amrs(
            "2026-07-11",
            SOURCE_REVISION,
            SOURCE_HASHES,
        )
        broken = candidate.replace("# RULES: 10", "# RULES: 11", 1)
        with self.assertRaises(generator.UpdateError):
            generator.validate_amrs(broken)

    def test_generator_has_no_git_or_publication_policy(self) -> None:
        source = Path(generator.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "git clone",
            "git push",
            "EXPECTED_ORIGIN",
            "REVIEWED_UPSTREAM_SHA256",
            "def publish(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
