#!/usr/bin/env python3
"""Generate the maintained Anywhere WeChat routing rule set from local inputs."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import os
import re
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "rules" / "wechat.arrs"
RAW_LINK = "https://raw.githubusercontent.com/carolcheng520/anyrule/main/rules/wechat.arrs"
PRIMARY_SOURCE = "blackmatrix7/ios_rule_script:rule/Surge/WeChat/WeChat.list"
SUPPLEMENTAL_SOURCE = "chikacya/anywhere-rules:rules/common/WeChat.arrs"
Rule = tuple[str, str]

IPV4_PREFIX_RE = re.compile(r"^(?:\d{1,3}\.){2,3}$")
FULL_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SUPPORTED_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "IP-CIDR", "IP-CIDR6"}
SKIPPED_TYPES = {"DOMAIN-KEYWORD", "IP-ASN", "USER-AGENT"}
KNOWN_SOURCE_TYPES = SUPPORTED_TYPES | SKIPPED_TYPES
APPROVED_EXACT_DOMAINS = {
    "apd-pcdnwxlogin.teg.tencent-cloud.net",
    "dldir1.qq.com",
    "slife.xy-asia.com",
    "soup.v.qq.com",
    "vweixinf.tc.qq.com",
    "weixin110.qq.com",
    "wup.imtt.qq.com",
}
SUPPLEMENTAL_RULES: list[tuple[Rule, Rule]] = [
    (("2", "btrace.qq.com"), ("2", "apd-pcdnwxlogin.teg.tencent-cloud.net")),
    (("1", "240e:95c:3003:10::/60"), ("1", "240e:95c:2003:20::/60")),
    (("1", "240e:f7:a070:400::/60"), ("1", "240e:f7:a070:100::/60")),
]


def local_path(value: str) -> Path:
    if value.startswith(("http://", "https://")):
        raise argparse.ArgumentTypeError("remote URLs are not supported; use a local file path")
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"input file not found: {path}")
    return path


def full_revision(value: str) -> str:
    normalized = value.strip().lower()
    if not FULL_REVISION_RE.fullmatch(normalized):
        raise argparse.ArgumentTypeError("revision must be a full 40-character Git SHA")
    return normalized


def read_source(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Input is not UTF-8: {path} ({exc})") from exc
    return text, hashlib.sha256(data).hexdigest()


def is_ipv4_prefix_keyword(value: str) -> bool:
    if not IPV4_PREFIX_RE.fullmatch(value):
        return False
    octets = [part for part in value.split(".") if part]
    return all(0 <= int(octet) <= 255 for octet in octets)


def convert_rule(rule_type: str, value: str) -> Rule:
    normalized = value.strip().lower().rstrip(".")
    if not normalized:
        raise ValueError("empty value")
    if rule_type == "DOMAIN":
        if normalized not in APPROVED_EXACT_DOMAINS:
            raise ValueError(f"unreviewed exact DOMAIN would be widened to a suffix: {normalized}")
        return ("2", normalized)
    if rule_type == "DOMAIN-SUFFIX":
        return ("2", normalized)
    if rule_type == "IP-CIDR":
        return ("0", str(ipaddress.IPv4Network(normalized, strict=False)))
    if rule_type == "IP-CIDR6":
        return ("1", str(ipaddress.IPv6Network(normalized, strict=False)))
    raise ValueError(f"unsupported conversion type: {rule_type}")


def dedupe_preserving_order(rules: list[Rule]) -> list[Rule]:
    output: list[Rule] = []
    seen: set[Rule] = set()
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            output.append(rule)
    return output


def declared_source_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"# ([A-Z0-9-]+): (\d+)", line.strip())
        if match and (match.group(1) in KNOWN_SOURCE_TYPES or match.group(1) == "TOTAL"):
            key, value = match.groups()
            if key in counts:
                raise SystemExit(f"Duplicate source count header: {key}")
            counts[key] = int(value)
    missing = sorted((KNOWN_SOURCE_TYPES | {"TOTAL"}) - counts.keys())
    if missing:
        raise SystemExit("Missing source count header(s): " + ", ".join(missing))
    return counts


def parse_rules(text: str) -> tuple[list[Rule], Counter[str]]:
    declared = declared_source_counts(text)
    observed: Counter[str] = Counter()
    rules: list[Rule] = []
    skipped: Counter[str] = Counter()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise SystemExit(f"Malformed source rule at line {line_number}: {raw_line}")
        rule_type, value = parts[:2]
        rule_type = rule_type.upper()
        if rule_type not in KNOWN_SOURCE_TYPES:
            raise SystemExit(f"Unknown source rule type at line {line_number}: {rule_type}")
        flags = parts[2:]
        if flags and any(flag != "no-resolve" for flag in flags):
            raise SystemExit(f"Unknown source flag at line {line_number}: {', '.join(flags)}")
        observed[rule_type] += 1

        if rule_type == "DOMAIN-KEYWORD":
            if not is_ipv4_prefix_keyword(value):
                raise SystemExit(
                    f"Refusing to drop non-IP-prefix DOMAIN-KEYWORD at line {line_number}: {value}"
                )
            skipped[rule_type] += 1
            continue
        if rule_type in SKIPPED_TYPES:
            skipped[rule_type] += 1
            continue
        try:
            rules.append(convert_rule(rule_type, value))
        except ValueError as exc:
            raise SystemExit(f"Invalid {rule_type} at line {line_number}: {value} ({exc})") from exc

    observed_total = sum(observed.values())
    mismatches = [
        f"{key}: declared={declared[key]} observed={observed[key]}"
        for key in sorted(KNOWN_SOURCE_TYPES)
        if declared[key] != observed[key]
    ]
    if declared["TOTAL"] != observed_total:
        mismatches.append(f"TOTAL: declared={declared['TOTAL']} observed={observed_total}")
    if mismatches:
        raise SystemExit("Source count mismatch:\n" + "\n".join(mismatches))
    return dedupe_preserving_order(rules), skipped


def convert_anywhere_rule(rule_type: str, value: str, line_number: int, label: str) -> Rule | None:
    normalized_type = rule_type.strip()
    normalized_value = value.strip().lower()
    if not normalized_value:
        return None
    if normalized_type == "0":
        try:
            return ("0", str(ipaddress.IPv4Network(normalized_value, strict=False)))
        except ValueError as exc:
            raise SystemExit(f"{label}:{line_number}: invalid IPv4 CIDR {value} ({exc})") from exc
    if normalized_type == "1":
        try:
            return ("1", str(ipaddress.IPv6Network(normalized_value, strict=False)))
        except ValueError as exc:
            raise SystemExit(f"{label}:{line_number}: invalid IPv6 CIDR {value} ({exc})") from exc
    if normalized_type in {"2", "3"}:
        return (normalized_type, normalized_value.rstrip("."))
    return None


def parse_anywhere_rules(text: str, label: str) -> list[Rule]:
    rules: list[Rule] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "//")) or "=" in line:
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) != 2:
            raise SystemExit(f"{label}:{line_number}: malformed Anywhere rule")
        converted = convert_anywhere_rule(parts[0], parts[1], line_number, label)
        if converted is None:
            raise SystemExit(f"{label}:{line_number}: unsupported Anywhere rule type {parts[0]}")
        rules.append(converted)
    return dedupe_preserving_order(rules)


def validate_supplemental_rules(text: str) -> None:
    source_rules = set(parse_anywhere_rules(text, SUPPLEMENTAL_SOURCE))
    missing = [
        f"{rule_type}, {value}"
        for (rule_type, value), _ in SUPPLEMENTAL_RULES
        if (rule_type, value) not in source_rules
    ]
    if missing:
        raise SystemExit(
            "Supplemental WeChat rule(s) are missing from the supplemental source:\n"
            + "\n".join(missing)
        )


def build_rules(source_rules: list[Rule]) -> list[Rule]:
    rules = dedupe_preserving_order(source_rules)
    for supplemental, anchor in SUPPLEMENTAL_RULES:
        if supplemental in rules:
            continue
        try:
            anchor_index = rules.index(anchor)
        except ValueError:
            rules.append(supplemental)
        else:
            rules.insert(anchor_index + 1, supplemental)
    return rules


def parse_output_rules(text: str) -> list[Rule]:
    rules: list[Rule] = []
    for line in text.splitlines():
        if re.fullmatch(r"[0-2], .+", line.strip()):
            rule_type, value = line.split(",", 1)
            rules.append((rule_type.strip(), value.strip()))
    return rules


def output_last_updated(path: Path, rules: list[Rule]) -> str:
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if parse_output_rules(text) == rules:
            for line in text.splitlines():
                if line.startswith("# LAST-UPDATED: "):
                    return line.removeprefix("# LAST-UPDATED: ").strip()
    return date.today().isoformat()


def render_rules(
    rules: list[Rule],
    last_updated: str,
    *,
    source_revision: str,
    source_sha256: str,
    supplemental_revision: str,
    supplemental_sha256: str,
    skipped: Counter[str],
) -> str:
    body = "\n".join(f"{rule_type}, {value}" for rule_type, value in rules)
    skipped_text = ", ".join(f"{key}={value}" for key, value in sorted(skipped.items()))
    return (
        "# PURPOSE: Direct routing rules for WeChat core domains and IP ranges.\n"
        f"# LINK: {RAW_LINK}\n"
        f"# LAST-UPDATED: {last_updated}\n"
        "# SUGGESTED-ACTION: DIRECT\n"
        f"# RULES: {len(rules)}\n"
        f"# SOURCE: {PRIMARY_SOURCE}@{source_revision}\n"
        f"# SOURCE-SHA256: {source_sha256}\n"
        f"# SUPPLEMENTAL-SOURCE: {SUPPLEMENTAL_SOURCE}@{supplemental_revision}\n"
        f"# SUPPLEMENTAL-SOURCE-SHA256: {supplemental_sha256}\n"
        "# GENERATED-BY: scripts/update_wechat_arrs.py\n"
        f"# SKIPPED: {skipped_text or 'none'}\n"
        "\n"
        "name = WeChat\n"
        f"{body}\n"
    )


def validate_no_unreviewed_removals(path: Path, rules: list[Rule], allow_removals: bool) -> None:
    if allow_removals or not path.exists():
        return
    removed = [rule for rule in parse_output_rules(path.read_text(encoding="utf-8")) if rule not in rules]
    if removed:
        details = "\n".join(f"{rule_type}, {value}" for rule_type, value in removed)
        raise SystemExit("Refusing unreviewed WeChat rule removal(s):\n" + details)


def write_output(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=local_path)
    parser.add_argument("--source-revision", required=True, type=full_revision)
    parser.add_argument("--supplemental-source", required=True, type=local_path)
    parser.add_argument("--supplemental-revision", required=True, type=full_revision)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--allow-rule-removals", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_text, source_sha256 = read_source(args.source)
    supplemental_text, supplemental_sha256 = read_source(args.supplemental_source)
    source_rules, skipped = parse_rules(source_text)
    validate_supplemental_rules(supplemental_text)
    rules = build_rules(source_rules)
    validate_no_unreviewed_removals(args.output, rules, args.allow_rule_removals)
    rendered = render_rules(
        rules,
        output_last_updated(args.output, rules),
        source_revision=args.source_revision,
        source_sha256=source_sha256,
        supplemental_revision=args.supplemental_revision,
        supplemental_sha256=supplemental_sha256,
        skipped=skipped,
    )
    changed = write_output(args.output, rendered)
    type_counts = Counter(rule_type for rule_type, _ in rules)
    print(f"{'wrote' if changed else 'unchanged'} {args.output}")
    print(f"rules={len(rules)} type0={type_counts['0']} type1={type_counts['1']} type2={type_counts['2']}")
    print("skipped=" + ", ".join(f"{key}:{value}" for key, value in sorted(skipped.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
