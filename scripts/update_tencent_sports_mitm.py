#!/usr/bin/env python3
"""Update and publish the Tencent Sports MITM rule from upstream Surge files."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


UPSTREAM_URL = "https://github.com/Hey-sayiwanna/TencentSports-Surge.git"
EXPECTED_ORIGIN = "git@github.com:carolcheng520/anyrule.git"
MAIN_BRANCH = "main"
TARGET_RELATIVE = Path("mitm/TencentSportsAdBlock.amrs")

HOSTNAMES = [
    "app.sports.qq.com",
    "config.ab.qq.com",
    "shequ.sports.qq.com",
    "film.video.qq.com",
    "sports.qq.com",
    "matchweb.sports.qq.com",
]

EXPECTED_UPSTREAM_PATTERNS = [
    r"^https:\/\/(?:app\.sports\.qq\.com\/(?:feeds\/list|m\/matchAfter\/stats|match\/adBanner)\?|shequ\.sports\.qq\.com\/topic\/detail\?|film\.video\.qq\.com\/x\/sports-vip-channel\/(?:\?.*)?$)",
    r"^https:\/\/(?:app\.sports\.qq\.com\/(?:trpc\.sports_resource\.cgi\.ResourceCGI\/MatchWidgets|vaccess\/trpc\.sports_resource\.cgi\.ResourceCGI\/ColumnWidget|vaccess\/trpc\.sportsbasic\.column\.Column\/GetColumn)|sports\.qq\.com\/sapp\/h5msg\.htm|matchweb\.sports\.qq\.com\/trpc\.dorae\.coin\.Coin\/CoinLayer)(?:\?.*)?$",
]

REVIEWED_UPSTREAM_SHA256 = {
    "TencentSportsAdBlock.sgmodule": "4987d3d24b0947366e950cbfe06b5d4aecd61b6c6bd258d9fe8a354c0615da75",
    "TencentSportsAdBlock.js": "07ce795cb38bbfc77d771c1eefbb70577d49e44d44c071e27b09dd05bad62427",
    "TencentSportsFloatBlock.js": "e62e26451ab1f2107d054ab9b311fcdbd13edb3ddedadcec6ef130b3cf9c291f",
}

REPRESENTATIVE_URLS = [
    "https://app.sports.qq.com/feeds/list?x=1",
    "https://app.sports.qq.com/m/matchAfter/stats?x=1",
    "https://app.sports.qq.com/match/adBanner?x=1",
    "https://shequ.sports.qq.com/topic/detail?id=1",
    "https://app.sports.qq.com/trpc.sports_resource.cgi.ResourceCGI/MatchWidgets?x=1",
    "https://app.sports.qq.com/vaccess/trpc.sports_resource.cgi.ResourceCGI/ColumnWidget?x=1",
    "https://app.sports.qq.com/vaccess/trpc.sportsbasic.column.Column/GetColumn?x=1",
    "https://sports.qq.com/sapp/h5msg.htm?x=1",
    "https://matchweb.sports.qq.com/trpc.dorae.coin.Coin/CoinLayer?x=1",
    "https://film.video.qq.com/x/sports-vip-channel/?x=1",
]


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Rule:
    phase: str
    order: int
    pattern: str
    script: str

    def line(self) -> str:
        encoded = base64.b64encode(self.script.encode("utf-8")).decode("ascii")
        return f"{self.phase}, {self.order}, {self.pattern}, {encoded}"


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise UpdateError(f"{' '.join(args)} failed: {output or result.returncode}")
    return result


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def git_output(repo: Path, args: list[str]) -> str:
    return run(["git", *args], cwd=repo).stdout.strip()


def require_publishable_repo(repo: Path, *, require_clean: bool) -> None:
    top_level = Path(git_output(repo, ["rev-parse", "--show-toplevel"])).resolve()
    if top_level != repo.resolve():
        raise UpdateError(f"expected repo root {repo}, found {top_level}")

    branch = git_output(repo, ["branch", "--show-current"])
    if branch != MAIN_BRANCH:
        raise UpdateError(f"expected branch {MAIN_BRANCH}, found {branch or 'detached HEAD'}")

    origin = git_output(repo, ["remote", "get-url", "origin"])
    if origin != EXPECTED_ORIGIN:
        raise UpdateError(f"expected origin {EXPECTED_ORIGIN}, found {origin}")

    if require_clean:
        status = git_output(repo, ["status", "--porcelain"])
        if status:
            raise UpdateError(f"worktree is not clean:\n{status}")

    run(["git", "fetch", "origin", MAIN_BRANCH], cwd=repo, capture=False)
    ahead_behind = git_output(repo, ["rev-list", "--left-right", "--count", f"HEAD...origin/{MAIN_BRANCH}"])
    if ahead_behind != "0\t0":
        raise UpdateError(f"local branch must match origin/{MAIN_BRANCH}, got {ahead_behind}")


def clone_upstream() -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
    temp = tempfile.TemporaryDirectory(prefix="tencent-sports-surge-")
    upstream = Path(temp.name) / "TencentSports-Surge"
    run(["git", "clone", "--depth", "1", UPSTREAM_URL, str(upstream)], cwd=Path(temp.name), capture=False)
    sha = git_output(upstream, ["rev-parse", "HEAD"])
    return temp, upstream, sha


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_supported_upstream(upstream: Path) -> None:
    for filename, expected_hash in REVIEWED_UPSTREAM_SHA256.items():
        actual_hash = file_sha256(upstream / filename)
        if actual_hash != expected_hash:
            raise UpdateError(
                f"unreviewed upstream {filename} content: expected {expected_hash}, got {actual_hash}; "
                "review upstream changes and update this converter before publishing"
            )

    sgmodule = (upstream / "TencentSportsAdBlock.sgmodule").read_text(encoding="utf-8")
    ad_js = (upstream / "TencentSportsAdBlock.js").read_text(encoding="utf-8")
    float_js = (upstream / "TencentSportsFloatBlock.js").read_text(encoding="utf-8")

    for hostname in HOSTNAMES:
        if hostname not in sgmodule:
            raise UpdateError(f"upstream sgmodule no longer contains hostname {hostname}")

    for pattern in EXPECTED_UPSTREAM_PATTERNS:
        if pattern not in sgmodule:
            raise UpdateError(f"unsupported upstream script pattern change: {pattern}")

    required_tokens = {
        "TencentSportsAdBlock.js": [
            "isHomeVipPromotion",
            "removeVipPopup",
            'ad\\.sports',
            'gdt\\.qq\\.com',
            "sports-vip-channel",
        ],
        "TencentSportsFloatBlock.js": [
            "CoinLayer",
            "closeH5MessagePopup",
            "forceNotice",
            "newRecommend",
            "GetColumn",
        ],
    }
    for token in required_tokens["TencentSportsAdBlock.js"]:
        if token not in ad_js:
            raise UpdateError(f"unsupported upstream TencentSportsAdBlock.js change, missing {token!r}")
    for token in required_tokens["TencentSportsFloatBlock.js"]:
        if token not in float_js:
            raise UpdateError(f"unsupported upstream TencentSportsFloatBlock.js change, missing {token!r}")


def map_local_script() -> str:
    return """function process(ctx) {
  Anywhere.respond({
    status: 200,
    headers: [["Content-Type", "application/proto"]],
    body: ""
  });
}
"""


def feed_script() -> str:
    return """function process(ctx) {
  try {
    const body = JSON.parse(Anywhere.codec.utf8.decode(ctx.body));
    const data = body && body.data;
    let removedCount = 0;
    let changed = false;

    function isAdItem(item) {
      if (!item || typeof item !== "object") return false;

      const report =
        typeof item.report === "string"
          ? item.report
          : JSON.stringify(item.report || {});

      const info = item.info || {};
      const infoReport =
        typeof info.report === "string"
          ? info.report
          : JSON.stringify(info.report || {});

      const jumpData = info.jumpData || {};
      const param = jumpData.param || {};
      const jumpUrl = param.url || param.iosUrl || "";

      return (
        item.id === "ad" ||
        item.type === 613 ||
        item.reason === "\u5f3a\u63d2" ||
        /"rec_type":"613"/.test(report) ||
        /"is_force_insert":"1"/.test(report) ||
        /"module":"internalbanner"/.test(report) ||
        /"sub_ei":"banner"/.test(report) ||
        /ad\\.sports|gdt|advert|internalbanner/i.test(report) ||
        /ad\\.sports|gdt|advert|internalbanner/i.test(infoReport) ||
        /waimai\\.meituan\\.com|gdt\\.qq\\.com/i.test(jumpUrl)
      );
    }

    function isHomeVipPromotion(item) {
      if (!item || typeof item !== "object") return false;

      const info = item.info || {};
      const vipPromotion = info.vipPromotion || {};
      const adReport = vipPromotion.adReport || {};
      const taskReport = vipPromotion.taskReport || {};
      const buttonJumpData = vipPromotion.buttonJumpData || {};
      const buttonParam = buttonJumpData.param || {};
      const jumpData = vipPromotion.jumpData || {};
      const jumpParam = jumpData.param || {};
      const ptag = adReport.ptag || taskReport.ptag || buttonParam.url || jumpParam.url || "";

      return (
        item.id === "type1149" ||
        /ad\\.sports\\.homepage\\.banner/i.test(ptag) ||
        (
          vipPromotion.title === "\u65b0\u7528\u6237\u9996\u5f00\u7279\u60e0" &&
          vipPromotion.button === "\u7acb\u5373\u5f00\u901a"
        )
      );
    }

    if (data && Array.isArray(data.list)) {
      data.list = data.list.filter((item) => {
        if (isAdItem(item)) {
          removedCount += 1;
          changed = true;
          return false;
        }
        return true;
      });
    }

    if (data && Object.prototype.hasOwnProperty.call(data, "adList")) {
      data.adList = "";
      changed = true;
    }

    if (data && Array.isArray(data.topItem)) {
      data.topItem = data.topItem.filter((item) => {
        if (isHomeVipPromotion(item)) {
          removedCount += 1;
          changed = true;
          return false;
        }
        return true;
      });
    }

    if (data && Array.isArray(data.stats)) {
      data.stats = data.stats.filter((item) => {
        const ad = item && item.ad;
        const isMatchBannerAd =
          item &&
          (
            item.text === "\u5e7f\u544a" ||
            String(item.type) === "41" ||
            typeof (ad && ad.adListPB) === "string" ||
            Boolean(ad && ad.adListPB)
          );

        if (isMatchBannerAd) {
          removedCount += 1;
          changed = true;
          return false;
        }
        return true;
      });
    }

    if (data && Object.prototype.hasOwnProperty.call(data, "iconAd")) {
      data.iconAd = {};
      changed = true;
    }

    if (data && Object.prototype.hasOwnProperty.call(data, "topWidget")) {
      data.topWidget = {};
      changed = true;
    }

    if (!changed) return;
    if (removedCount > 0) {
      Anywhere.log.info("Tencent Sports feed removed " + removedCount + " ad module(s).");
    }
    ctx.body = Anywhere.codec.utf8.encode(JSON.stringify(body));
  } catch (e) {
    Anywhere.log.warning("Tencent Sports feed ad block failed: " + e);
  }
}
"""


def article_script() -> str:
    return """function process(ctx) {
  try {
    const body = JSON.parse(Anywhere.codec.utf8.decode(ctx.body));
    const data = body && body.data;
    let changed = false;

    if (data && typeof data.adListPB === "string" && data.adListPB.length > 0) {
      data.adListPB = "";
      changed = true;
    }

    if (data && Array.isArray(data.adList) && data.adList.length > 0) {
      data.adList = [];
      changed = true;
    }

    if (data && Array.isArray(data.adInfos) && data.adInfos.length > 0) {
      data.adInfos = [];
      changed = true;
    }

    if (!changed) return;
    ctx.body = Anywhere.codec.utf8.encode(JSON.stringify(body));
  } catch (e) {
    Anywhere.log.warning("Tencent Sports article ad block failed: " + e);
  }
}
"""


def match_widgets_script() -> str:
    return """function process(ctx) {
  try {
    const body = JSON.parse(Anywhere.codec.utf8.decode(ctx.body));
    const data = body && body.data;

    if (!data || !Array.isArray(data.bannerList)) return;
    data.bannerList = [];
    ctx.body = Anywhere.codec.utf8.encode(JSON.stringify(body));
  } catch (e) {
    Anywhere.log.warning("Tencent Sports match widgets ad block failed: " + e);
  }
}
"""


def column_widget_script() -> str:
    return """function process(ctx) {
  try {
    const body = JSON.parse(Anywhere.codec.utf8.decode(ctx.body));
    const data = body && body.data;
    const jumpData = data && data.jumpData;
    const param = jumpData && jumpData.param;
    const title = (param && param.title) || "";
    const url = (param && param.url) || "";

    if (!data || !(data.img || title || url)) return;
    body.data = null;
    ctx.body = Anywhere.codec.utf8.encode(JSON.stringify(body));
  } catch (e) {
    Anywhere.log.warning("Tencent Sports column widget block failed: " + e);
  }
}
"""


def get_column_script() -> str:
    return """function process(ctx) {
  try {
    const body = JSON.parse(Anywhere.codec.utf8.decode(ctx.body));
    const data = body && body.data;
    let changed = false;
    let removedCount = 0;

    if (data && Array.isArray(data.forceNotice) && data.forceNotice.length > 0) {
      const popupIds = data.forceNotice
        .map((item) => String((item && item.id) || ""))
        .filter(Boolean);

      removedCount += data.forceNotice.length;
      data.forceNotice = [];
      changed = true;

      if (Array.isArray(data.newRecommend) && popupIds.length > 0) {
        const beforeCount = data.newRecommend.length;
        data.newRecommend = data.newRecommend.filter(
          (item) => !popupIds.includes(String((item && item.id) || ""))
        );
        removedCount += beforeCount - data.newRecommend.length;
      }
    }

    if (!changed) return;
    if (removedCount > 0) {
      Anywhere.log.info("Tencent Sports column removed " + removedCount + " popup item(s).");
    }
    ctx.body = Anywhere.codec.utf8.encode(JSON.stringify(body));
  } catch (e) {
    Anywhere.log.warning("Tencent Sports column popup block failed: " + e);
  }
}
"""


def h5_script() -> str:
    return """function process(ctx) {
  ctx.body = Anywhere.codec.utf8.encode(`<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title></title>
</head>
<body>
<script>
(function () {
  function closeNativePage() {
    try {
      var frame = document.createElement("iframe");
      frame.style.cssText =
        "display:none;width:0;height:0;border:0;position:fixed;left:0;top:0;";
      frame.src = "http://sports.qq.com/jsBridge/close?";
      document.documentElement.appendChild(frame);
    } catch (error) {}

    setTimeout(function () {
      try {
        history.back();
      } catch (error) {}
    }, 150);
  }

  closeNativePage();
}());
</script>
</body>
</html>`);
}
"""


def coin_script() -> str:
    return """function process(ctx) {
  ctx.body = Anywhere.codec.utf8.encode(JSON.stringify({
    code: 0,
    data: null,
    traceID: ""
  }));
}
"""


def vip_popup_script() -> str:
    return """function process(ctx) {
  try {
    let body = Anywhere.codec.utf8.decode(ctx.body);
    const marker = '"moduleType":"module_popup_page"';
    const markerIndex = body.indexOf(marker);

    if (markerIndex === -1) return;

    function findMatchingBrace(text, start) {
      let depth = 0;
      let inString = false;
      let escaped = false;

      for (let i = start; i < text.length; i++) {
        const ch = text[i];

        if (inString) {
          if (escaped) {
            escaped = false;
          } else if (ch === "\\\\") {
            escaped = true;
          } else if (ch === '"') {
            inString = false;
          }
          continue;
        }

        if (ch === '"') {
          inString = true;
        } else if (ch === "{") {
          depth += 1;
        } else if (ch === "}") {
          depth -= 1;
          if (depth === 0) return i;
        }
      }

      return -1;
    }

    const objectStack = [];
    let inString = false;
    let escaped = false;

    for (let i = 0; i <= markerIndex; i++) {
      const ch = body[i];

      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (ch === "\\\\") {
          escaped = true;
        } else if (ch === '"') {
          inString = false;
        }
        continue;
      }

      if (ch === '"') {
        inString = true;
      } else if (ch === "{") {
        objectStack.push(i);
      } else if (ch === "}") {
        objectStack.pop();
      }
    }

    let moduleStart = -1;
    let moduleEnd = -1;

    for (let i = objectStack.length - 1; i >= 0; i--) {
      const start = objectStack[i];
      const end = findMatchingBrace(body, start);
      if (end === -1) continue;

      const moduleText = body.slice(start, end + 1);
      if (
        moduleText.includes(marker) &&
        moduleText.includes('"moduleId"') &&
        moduleText.includes('"itemDataLists"')
      ) {
        moduleStart = start;
        moduleEnd = end;
        break;
      }
    }

    if (moduleStart === -1 || moduleEnd === -1) return;

    let removeStart = moduleStart;
    let removeEnd = moduleEnd;
    let left = moduleStart - 1;
    while (left >= 0 && /\\s/.test(body[left])) left -= 1;

    if (body[left] === ",") {
      removeStart = left;
    } else {
      let right = moduleEnd + 1;
      while (right < body.length && /\\s/.test(body[right])) right += 1;
      if (body[right] === ",") removeEnd = right;
    }

    body = body.slice(0, removeStart) + body.slice(removeEnd + 1);
    ctx.body = Anywhere.codec.utf8.encode(body);
  } catch (e) {
    Anywhere.log.warning("Tencent Sports VIP popup block failed: " + e);
  }
}
"""


def rules() -> list[Rule]:
    return [
        Rule("0", 100, r"^https://config\.ab\.qq\.com/tab/GetTabRemoteConfig.*", map_local_script()),
        Rule("0", 100, r"^https://config\.ab\.qq\.com/tab/GetTabToggle.*", map_local_script()),
        Rule("1", 100, r"^https://app\.sports\.qq\.com/(?:feeds/list|m/matchAfter/stats|match/adBanner)\?", feed_script()),
        Rule("1", 100, r"^https://shequ\.sports\.qq\.com/topic/detail\?", article_script()),
        Rule("1", 100, r"^https://app\.sports\.qq\.com/trpc\.sports_resource\.cgi\.ResourceCGI/MatchWidgets(?:\?.*)?$", match_widgets_script()),
        Rule("1", 100, r"^https://app\.sports\.qq\.com/vaccess/trpc\.sports_resource\.cgi\.ResourceCGI/ColumnWidget(?:\?.*)?$", column_widget_script()),
        Rule("1", 100, r"^https://app\.sports\.qq\.com/vaccess/trpc\.sportsbasic\.column\.Column/GetColumn(?:\?.*)?$", get_column_script()),
        Rule("1", 100, r"^https://sports\.qq\.com/sapp/h5msg\.htm(?:\?.*)?$", h5_script()),
        Rule("1", 100, r"^https://matchweb\.sports\.qq\.com/trpc\.dorae\.coin\.Coin/CoinLayer(?:\?.*)?$", coin_script()),
        Rule("1", 100, r"^https://film\.video\.qq\.com/x/sports-vip-channel/(?:\?.*)?$", vip_popup_script()),
    ]


def existing_last_updated(target: Path) -> str:
    if not target.exists():
        return dt.date.today().isoformat()
    match = re.search(r"^# LAST-UPDATED: (\d{4}-\d{2}-\d{2})$", target.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else dt.date.today().isoformat()


def build_amrs(last_updated: str) -> str:
    built_rules = rules()
    lines = [
        "# PURPOSE: MITM rules to block Tencent Sports splash, feed, article, widget, VIP popup, task popup, H5 popup, and PageCard ads.",
        "# LINK: https://raw.githubusercontent.com/carolcheng520/anyrule/main/mitm/TencentSportsAdBlock.amrs",
        "# SOURCE: https://raw.githubusercontent.com/Hey-sayiwanna/TencentSports-Surge/main/TencentSportsAdBlock.sgmodule",
        f"# LAST-UPDATED: {last_updated}",
        "# SUGGESTED-ACTION: Enable MITM",
        f"# RULES: {len(built_rules)}",
        "# COMPANION-FILES: Standalone. Upstream recommends broad ad-platform and HTTPDNS REJECT modules for pre-roll video ads; they are omitted here because their scope is not Tencent Sports-specific.",
        "",
        "name = Tencent Sports Ad Block",
        f"hostname = {', '.join(HOSTNAMES)}",
        "",
    ]
    lines.extend(rule.line() for rule in built_rules)
    return "\n".join(lines) + "\n"


def decode_rules(amrs_text: str) -> list[tuple[str, str]]:
    decoded: list[tuple[str, str]] = []
    for line in amrs_text.splitlines():
        if not line.startswith(("0,", "1,")):
            continue
        parts = line.split(", ")
        if len(parts) < 4:
            raise UpdateError(f"invalid rule line: {line[:80]}")
        script = base64.b64decode(", ".join(parts[3:])).decode("utf-8")
        decoded.append((parts[2], script))
    return decoded


def validate_amrs(amrs_text: str) -> None:
    rule_lines = [line for line in amrs_text.splitlines() if line.startswith(("0,", "1,"))]
    header_match = re.search(r"^# RULES: (\d+)$", amrs_text, re.MULTILINE)
    if not header_match:
        raise UpdateError("missing RULES header")
    if int(header_match.group(1)) != len(rule_lines):
        raise UpdateError(f"RULES mismatch: header={header_match.group(1)} actual={len(rule_lines)}")

    decoded = decode_rules(amrs_text)
    for pattern, script in decoded:
        if "ad.sports" in script and "ad\\.sports" not in script:
            raise UpdateError(f"loose ad.sports regex in {pattern}")
        if "gdt.qq.com" in script and "gdt\\.qq\\.com" not in script:
            raise UpdateError(f"loose gdt.qq.com regex in {pattern}")

    response_patterns = [pattern for line in rule_lines if line.startswith("1,") for pattern in [line.split(", ")[2]]]
    for url in REPRESENTATIVE_URLS:
        matches = [pattern for pattern in response_patterns if re.search(pattern, url)]
        if len(matches) != 1:
            raise UpdateError(f"{url} matched {len(matches)} response rules")


NODE_VALIDATOR = r"""
const fs = require("fs");
const vm = require("vm");
const amrs = fs.readFileSync(process.env.AMRS_FILE, "utf8");
const upstreamDir = process.env.UPSTREAM_DIR;
const upstreamAd = fs.readFileSync(`${upstreamDir}/TencentSportsAdBlock.js`, "utf8");
const upstreamFloat = fs.readFileSync(`${upstreamDir}/TencentSportsFloatBlock.js`, "utf8");
const allRules = amrs.split(/\n/)
  .filter((line) => /^[01],/.test(line))
  .map((line) => {
    const parts = line.split(/, /);
    return {
      phase: parts[0],
      pattern: parts[2],
      script: Buffer.from(parts.slice(3).join(", "), "base64").toString("utf8")
    };
  });
for (const rule of allRules) {
  new vm.Script(rule.script);
}
const rules = allRules.filter((rule) => rule.phase === "1");

function local(url, body) {
  const matched = rules.filter((rule) => new RegExp(rule.pattern).test(url));
  if (matched.length !== 1) throw new Error(`local match count ${matched.length} for ${url}`);
  const ctx = { body: typeof body === "string" ? body : JSON.stringify(body) };
  const sandbox = {
    Anywhere: {
      codec: { utf8: { decode: String, encode: String } },
      log: { info(){}, warning(){} }
    }
  };
  vm.runInNewContext(matched[0].script, sandbox);
  sandbox.process(ctx);
  return ctx.body;
}

function upstream(script, url, body) {
  let result;
  const sandbox = {
    $request: { url },
    $response: { body: typeof body === "string" ? body : JSON.stringify(body) },
    $done: (value) => { result = value || {}; },
    console: { log(){} }
  };
  vm.runInNewContext(script, sandbox);
  return Object.prototype.hasOwnProperty.call(result || {}, "body")
    ? result.body
    : (typeof body === "string" ? body : JSON.stringify(body));
}

function canon(value) {
  try { return JSON.stringify(JSON.parse(value)); } catch { return value; }
}

function same(name, left, right) {
  if (canon(left) !== canon(right)) {
    throw new Error(`${name} differs from upstream`);
  }
}

const cases = [
  ["feed topItem", upstreamAd, "https://app.sports.qq.com/feeds/list?x=1", {
    data: {
      list: [{ id: "ad" }, { id: "keep" }],
      topItem: [
        { id: "type1149", info: { vipPromotion: { title: "\u65b0\u7528\u6237\u9996\u5f00\u7279\u60e0", button: "\u7acb\u5373\u5f00\u901a" } } },
        { id: "hot_my_schedule" }
      ],
      stats: [{ text: "\u5e7f\u544a" }, { text: "\u6bd4\u5206" }],
      adList: "x",
      iconAd: { a: 1 },
      topWidget: { b: 1 }
    }
  }],
  ["feed no-op", upstreamAd, "https://app.sports.qq.com/feeds/list?x=1", {
    data: {
      list: [{ id: "keep" }],
      topItem: [{ id: "hot_my_schedule" }],
      stats: [{ text: "\u6bd4\u5206" }]
    }
  }],
  ["article", upstreamAd, "https://shequ.sports.qq.com/topic/detail?id=1", { data: { adListPB: "x", adList: [1], adInfos: [2], keep: true } }],
  ["vip html", upstreamAd, "https://film.video.qq.com/x/sports-vip-channel/?x=1", "{\"modules\":[{\"moduleId\":\"a\",\"itemDataLists\":[],\"moduleType\":\"module_popup_page\"},{\"moduleId\":\"keep\"}]}"],
  ["match widgets", upstreamFloat, "https://app.sports.qq.com/trpc.sports_resource.cgi.ResourceCGI/MatchWidgets?x=1", { data: { bannerList: [1, 2], keep: true } }],
  ["column widget", upstreamFloat, "https://app.sports.qq.com/vaccess/trpc.sports_resource.cgi.ResourceCGI/ColumnWidget?x=1", { data: { img: "x", jumpData: { param: { title: "a", url: "b" } } } }],
  ["get column", upstreamFloat, "https://app.sports.qq.com/vaccess/trpc.sportsbasic.column.Column/GetColumn?x=1", { data: { forceNotice: [{ id: 100 }, { id: 200 }], newRecommend: [{ id: 100 }, { id: 300 }], keep: true } }],
  ["get column no-op", upstreamFloat, "https://app.sports.qq.com/vaccess/trpc.sportsbasic.column.Column/GetColumn?x=1", { data: { newRecommend: [{ id: 300 }], keep: true } }],
  ["coin", upstreamFloat, "https://matchweb.sports.qq.com/trpc.dorae.coin.Coin/CoinLayer?x=1", { data: { visible: true } }],
  ["h5", upstreamFloat, "https://sports.qq.com/sapp/h5msg.htm?x=1", "<html>ad</html>"]
];

for (const [name, script, url, payload] of cases) {
  same(name, local(url, payload), upstream(script, url, payload));
}
"""


def validate_against_upstream(amrs_text: str, upstream: Path) -> None:
    if not shutil.which("node"):
        raise UpdateError("node is required for upstream behavior validation")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".amrs", delete=False) as temp:
        temp.write(amrs_text)
        temp_path = Path(temp.name)
    try:
        env = os.environ.copy()
        env["AMRS_FILE"] = str(temp_path)
        env["UPSTREAM_DIR"] = str(upstream)
        run(["node", "-e", NODE_VALIDATOR], cwd=repo_root(), env=env)
    finally:
        temp_path.unlink(missing_ok=True)


def generate_candidate(target: Path) -> str:
    preserved_date = existing_last_updated(target)
    candidate = build_amrs(preserved_date)
    if target.exists() and candidate == target.read_text(encoding="utf-8"):
        return candidate
    return build_amrs(dt.date.today().isoformat())


def update_target(target: Path, candidate: str, *, check_only: bool) -> bool:
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    if candidate == old:
        print(f"{target}: already up to date")
        return False
    if check_only:
        print(f"{target}: would update")
        return True
    target.write_text(candidate, encoding="utf-8")
    print(f"{target}: updated")
    return True


def publish(repo: Path, message: str, *, push: bool) -> None:
    changed = git_output(repo, ["status", "--porcelain"])
    if changed != f" M {TARGET_RELATIVE}":
        raise UpdateError(f"unexpected worktree changes before commit:\n{changed}")
    run(["git", "diff", "--check"], cwd=repo, capture=False)
    run(["git", "add", str(TARGET_RELATIVE)], cwd=repo, capture=False)
    staged = git_output(repo, ["diff", "--cached", "--name-only"])
    if staged != str(TARGET_RELATIVE):
        raise UpdateError(f"unexpected staged files:\n{staged}")
    unstaged = git_output(repo, ["diff", "--name-only"])
    if unstaged:
        raise UpdateError(f"unexpected unstaged files after staging target:\n{unstaged}")
    run(["git", "commit", "-m", message], cwd=repo, capture=False)
    if push:
        run(["git", "push", "origin", MAIN_BRANCH], cwd=repo, capture=False)
        run(["git", "fetch", "origin", MAIN_BRANCH], cwd=repo, capture=False)
        ahead_behind = git_output(repo, ["rev-list", "--left-right", "--count", f"HEAD...origin/{MAIN_BRANCH}"])
        if ahead_behind != "0\t0":
            raise UpdateError(f"post-push parity failed: {ahead_behind}")
        head = git_output(repo, ["rev-parse", "HEAD"])
        remote = run(["git", "ls-remote", "--heads", "origin", MAIN_BRANCH], cwd=repo).stdout.split()[0]
        if head != remote:
            raise UpdateError(f"live GitHub main mismatch: HEAD={head} remote={remote}")
        print(f"pushed {head}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="validate and report whether the rule would change")
    parser.add_argument("--no-commit", action="store_true", help="write the rule update but leave commit and push to the caller")
    parser.add_argument("--no-push", action="store_true", help="commit locally but do not push")
    parser.add_argument(
        "--commit-message",
        default="Update Tencent Sports MITM rules",
        help="commit message used when the rule changes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_only and args.no_commit:
        print("error: --check-only and --no-commit cannot be used together", file=sys.stderr)
        return 1

    repo = repo_root()
    target = repo / TARGET_RELATIVE

    try:
        require_publishable_repo(repo, require_clean=not args.check_only)
        temp, upstream, upstream_sha = clone_upstream()
        with temp:
            require_supported_upstream(upstream)
            candidate = generate_candidate(target)
            validate_amrs(candidate)
            validate_against_upstream(candidate, upstream)
            changed = update_target(target, candidate, check_only=args.check_only)
            print(f"upstream main: {upstream_sha}")
            if args.check_only or args.no_commit or not changed:
                return 0
            publish(repo, args.commit_message, push=not args.no_push)
        return 0
    except UpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
