#!/usr/bin/env python3
"""Contract tests for retained MITM and companion REJECT assets."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER_RE = re.compile(r"^# ([A-Z-]+):\s*(.*)$", re.MULTILINE)
LOCAL_COMPANION_RE = re.compile(r"\b(?:mitm|rules)/[A-Za-z0-9._/-]+")
WECHAT_REJECT_SUFFIXES = {
    "wxa.wxs.qq.com",
    "wximg.wxs.qq.com",
    "wxsmw.wxs.qq.com",
    "wxsnsdy.wxs.qq.com",
    "wxsnsdythumb.wxs.qq.com",
}


def metadata(path: Path) -> dict[str, str]:
    return dict(HEADER_RE.findall(path.read_text(encoding="utf-8")))


def arrs_rules(path: Path) -> set[tuple[int, str]]:
    rules: set[tuple[int, str]] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("name ="):
            continue
        rule_type, value = (part.strip() for part in line.split(",", 1))
        rules.add((int(rule_type), value))
    return rules


class MitmRejectContractsTest(unittest.TestCase):
    def test_wechat_companion_and_reject_suffixes_are_exact(self) -> None:
        mitm = ROOT / "mitm" / "WeChatAds.amrs"
        companion = ROOT / "rules" / "wechat-ads.arrs"
        references = set(
            LOCAL_COMPANION_RE.findall(metadata(mitm)["COMPANION-FILES"])
        )
        self.assertEqual(references, {"rules/wechat-ads.arrs"})
        self.assertEqual(
            arrs_rules(companion),
            {(2, suffix) for suffix in WECHAT_REJECT_SUFFIXES},
        )

    def test_all_local_mitm_companions_exist(self) -> None:
        for path in sorted((ROOT / "mitm").glob("*.amrs")):
            with self.subTest(path=path.name):
                companion_header = metadata(path)["COMPANION-FILES"]
                for relative in LOCAL_COMPANION_RE.findall(companion_header):
                    self.assertTrue((ROOT / relative).is_file(), relative)

    def test_all_remaining_routing_rules_are_explicit_rejects(self) -> None:
        paths = sorted((ROOT / "rules").glob("*.arrs"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(metadata(path)["SUGGESTED-ACTION"], "REJECT")
                self.assertNotIn("# SUGGESTED-ACTION: DIRECT", text)


if __name__ == "__main__":
    unittest.main()
