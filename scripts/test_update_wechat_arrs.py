#!/usr/bin/env python3
"""Checks for update_wechat_arrs.py."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import update_wechat_arrs as updater  # noqa: E402


REVISION_A = "a" * 40
REVISION_B = "b" * 40


def surge_source(lines: list[str], *, overrides: dict[str, int] | None = None) -> str:
    counts: Counter[str] = Counter(line.split(",", 1)[0] for line in lines)
    declared = {rule_type: counts[rule_type] for rule_type in updater.KNOWN_SOURCE_TYPES}
    declared.update(overrides or {})
    headers = [f"# {rule_type}: {declared[rule_type]}" for rule_type in sorted(declared)]
    headers.append(f"# TOTAL: {sum(declared.values())}")
    return "\n".join([*headers, *lines, ""])


def supplemental_source() -> str:
    return "\n".join(
        [
            "2, btrace.qq.com",
            "1, 240E:95C:3003:14::/60",
            "1, 240E:F7:A070:403::/60",
            "",
        ]
    )


class UpdateWeChatArrsTest(unittest.TestCase):
    def test_parse_rules_converts_only_reviewed_types_and_skips_explicit_types(self) -> None:
        rules, skipped = updater.parse_rules(
            surge_source(
                [
                    "DOMAIN,apd-pcdnwxlogin.teg.tencent-cloud.net",
                    "DOMAIN-SUFFIX,weixin.qq.com",
                    "DOMAIN-KEYWORD,101.226.129.",
                    "IP-CIDR,111.30.160.5/20,no-resolve",
                    "IP-CIDR6,240e:ff:f100::1/44,no-resolve",
                    "IP-ASN,132203,no-resolve",
                    "USER-AGENT,WeChat*",
                ]
            )
        )
        self.assertEqual(
            rules,
            [
                ("2", "apd-pcdnwxlogin.teg.tencent-cloud.net"),
                ("2", "weixin.qq.com"),
                ("0", "111.30.160.0/20"),
                ("1", "240e:ff:f100::/44"),
            ],
        )
        self.assertEqual(skipped, Counter({"DOMAIN-KEYWORD": 1, "IP-ASN": 1, "USER-AGENT": 1}))

    def test_parse_rules_rejects_unreviewed_semantic_widening(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            updater.parse_rules(surge_source(["DOMAIN,new-exact.example"]))
        self.assertIn("unreviewed exact DOMAIN", str(raised.exception))

    def test_parse_rules_rejects_unknown_type_flag_and_count_drift(self) -> None:
        cases = [
            (surge_source(["PROCESS-NAME,WeChat"]), "Unknown source rule type"),
            (surge_source(["IP-CIDR,192.0.2.0/24,unexpected"]), "Unknown source flag"),
            (surge_source(["DOMAIN-SUFFIX,weixin.qq.com"], overrides={"DOMAIN-SUFFIX": 2}), "Source count mismatch"),
        ]
        for source, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(SystemExit) as raised:
                    updater.parse_rules(source)
                self.assertIn(expected, str(raised.exception))

    def test_parse_rules_rejects_non_ip_domain_keyword(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            updater.parse_rules(surge_source(["DOMAIN-KEYWORD,wechat"]))
        self.assertIn("Refusing to drop non-IP-prefix", str(raised.exception))

    def test_build_rules_keeps_reviewed_supplemental_rules(self) -> None:
        source_rules = [
            ("2", "apd-pcdnwxlogin.teg.tencent-cloud.net"),
            ("2", "dldir1.qq.com"),
            ("1", "240e:95c:2003:20::/60"),
            ("1", "240e:f7:a070:100::/60"),
        ]
        rules = updater.build_rules(source_rules)
        for supplemental, _ in updater.SUPPLEMENTAL_RULES:
            self.assertIn(supplemental, rules)

    def test_validate_supplemental_rules_uses_cidr_semantics_and_fails_closed(self) -> None:
        updater.validate_supplemental_rules(supplemental_source())
        with self.assertRaises(SystemExit) as raised:
            updater.validate_supplemental_rules("2, btrace.qq.com\n")
        self.assertIn("Supplemental WeChat rule(s) are missing", str(raised.exception))

    def test_cli_is_local_only_and_records_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "WeChat.list"
            supplemental = root / "WeChat.arrs"
            output = root / "output.arrs"
            source_text = surge_source(["DOMAIN-SUFFIX,weixin.qq.com"])
            supplemental_text = supplemental_source()
            source.write_text(source_text, encoding="utf-8")
            supplemental.write_text(supplemental_text, encoding="utf-8")

            self.assertEqual(
                updater.main(
                    [
                        "--source", str(source),
                        "--source-revision", REVISION_A,
                        "--supplemental-source", str(supplemental),
                        "--supplemental-revision", REVISION_B,
                        "--output", str(output),
                    ]
                ),
                0,
            )
            rendered = output.read_text(encoding="utf-8")
            self.assertIn(f"# SOURCE: {updater.PRIMARY_SOURCE}@{REVISION_A}", rendered)
            self.assertIn(f"# SOURCE-SHA256: {hashlib.sha256(source.read_bytes()).hexdigest()}", rendered)
            self.assertIn(f"# SUPPLEMENTAL-SOURCE: {updater.SUPPLEMENTAL_SOURCE}@{REVISION_B}", rendered)
            self.assertIn("# SKIPPED: none", rendered)

            before = output.stat().st_mtime_ns
            updater.main(
                [
                    "--source", str(source),
                    "--source-revision", REVISION_A,
                    "--supplemental-source", str(supplemental),
                    "--supplemental-revision", REVISION_B,
                    "--output", str(output),
                ]
            )
            self.assertEqual(output.stat().st_mtime_ns, before)

        with self.assertRaises(SystemExit):
            updater.parse_args(
                [
                    "--source", "https://example.invalid/WeChat.list",
                    "--source-revision", REVISION_A,
                    "--supplemental-source", "https://example.invalid/WeChat.arrs",
                    "--supplemental-revision", REVISION_B,
                ]
            )

    def test_unreviewed_rule_removal_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wechat.arrs"
            path.write_text("2, existing.example\n", encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                updater.validate_no_unreviewed_removals(path, [("2", "other.example")], False)
            self.assertIn("Refusing unreviewed WeChat rule removal", str(raised.exception))
            updater.validate_no_unreviewed_removals(path, [("2", "other.example")], True)

    def test_wechat_direct_reject_and_mitm_files_keep_portfolio_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        direct = set(updater.parse_output_rules((root / "rules" / "wechat.arrs").read_text(encoding="utf-8")))
        rejects = set(updater.parse_output_rules((root / "rules" / "wechat-ads.arrs").read_text(encoding="utf-8")))
        mitm = (root / "mitm" / "WeChatAds.amrs").read_text(encoding="utf-8")
        self.assertIn(("2", "wxs.qq.com"), direct)
        self.assertTrue(rejects)
        self.assertTrue(all(value.endswith(".wxs.qq.com") for rule_type, value in rejects if rule_type == "2"))
        self.assertIn("hostname = mp.weixin.qq.com", mitm)
        self.assertIn("advertisement_num", __import__("base64").b64decode(
            "eyJhZHZlcnRpc2VtZW50X251bSI6MCwiYWR2ZXJ0aXNlbWVudF9pbmZvIjpbXX0="
        ).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
