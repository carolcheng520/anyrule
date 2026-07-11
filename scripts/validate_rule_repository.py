#!/usr/bin/env python3
"""Validate tracked AnyRule routing and MITM files without network access."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import ipaddress
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_HEADERS = ("PURPOSE", "LINK", "LAST-UPDATED", "SUGGESTED-ACTION", "RULES")
HEADER_RE = re.compile(r"^# ([A-Z-]+):\s*(.*)$")
RULE_RE = re.compile(r"^([0-4]),\s*(.+)$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def headers(lines: list[str], path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        match = HEADER_RE.match(line)
        if match:
            key, value = match.groups()
            if key in values:
                raise ValidationError(f"{path}: duplicate {key} header")
            values[key] = value.strip()
    required = set(COMMON_HEADERS)
    if path.suffix == ".amrs":
        required.add("COMPANION-FILES")
    missing = sorted(required - values.keys())
    if missing:
        raise ValidationError(f"{path}: missing header(s): {', '.join(missing)}")
    try:
        dt.date.fromisoformat(values["LAST-UPDATED"])
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid LAST-UPDATED date") from exc
    expected_link = f"https://raw.githubusercontent.com/carolcheng520/anyrule/main/{path.as_posix()}"
    if values["LINK"] != expected_link:
        raise ValidationError(f"{path}: LINK must be {expected_link}")
    return values


def validate_arrs(path: Path, lines: list[str]) -> int:
    seen: set[tuple[int, str]] = set()
    count = 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("name ="):
            continue
        match = RULE_RE.match(stripped)
        if not match:
            raise ValidationError(f"{path}:{number}: invalid rule line")
        rule_type = int(match.group(1))
        value = match.group(2).strip()
        if rule_type not in (0, 1, 2, 3):
            raise ValidationError(f"{path}:{number}: unsupported routing rule type {rule_type}")
        if rule_type in (0, 1):
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValidationError(f"{path}:{number}: invalid CIDR {value}") from exc
            expected_version = 4 if rule_type == 0 else 6
            if network.version != expected_version:
                raise ValidationError(f"{path}:{number}: rule type does not match CIDR version")
            value = str(network)
        elif rule_type == 2:
            value = value.lower().rstrip(".")
            if not DOMAIN_RE.fullmatch(value):
                raise ValidationError(f"{path}:{number}: invalid domain suffix {value}")
        elif not value:
            raise ValidationError(f"{path}:{number}: empty domain keyword")
        key = (rule_type, value)
        if key in seen:
            raise ValidationError(f"{path}:{number}: duplicate rule {rule_type}, {value}")
        seen.add(key)
        count += 1
    return count


def validate_amrs(path: Path, lines: list[str]) -> int:
    seen: set[tuple[str, str, str]] = set()
    count = 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("name =") or stripped.startswith("hostname ="):
            continue
        parts = stripped.split(", ", 3)
        if len(parts) != 4 or parts[0] not in {"0", "1", "2", "3", "4"} or not parts[1].isdigit():
            raise ValidationError(f"{path}:{number}: invalid MITM rule line")
        key = (parts[0], parts[1], parts[2])
        if key in seen:
            raise ValidationError(f"{path}:{number}: duplicate MITM match rule")
        seen.add(key)
        payload = parts[3]
        static_response = payload.startswith("4, ")
        encoded = payload[3:] if static_response else payload
        try:
            script = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValidationError(f"{path}:{number}: invalid base64 script") from exc
        if not static_response and "function process(" not in script:
            raise ValidationError(f"{path}:{number}: decoded rule has no process function")
        count += 1
    return count


def validate_file(path: Path) -> None:
    relative = path.relative_to(ROOT)
    lines = path.read_text(encoding="utf-8").splitlines()
    metadata = headers(lines, relative)
    actual = validate_arrs(relative, lines) if path.suffix == ".arrs" else validate_amrs(relative, lines)
    try:
        declared = int(metadata["RULES"])
    except ValueError as exc:
        raise ValidationError(f"{relative}: RULES must be an integer") from exc
    if declared != actual:
        raise ValidationError(f"{relative}: RULES declares {declared}, found {actual}")


def validate_repository(root: Path = ROOT) -> list[Path]:
    paths = sorted((root / "rules").glob("*.arrs")) + sorted((root / "mitm").glob("*.amrs"))
    if not paths:
        raise ValidationError("no rule files found")
    for path in paths:
        validate_file(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        paths = validate_repository()
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {len(paths)} rule files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
