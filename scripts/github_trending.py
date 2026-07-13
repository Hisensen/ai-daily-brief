#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 趋势榜（github.com/trending）抓取器 — 输出 build_report.py 的 section JSON。

独立可跑，也可被 aihot_daily.py import 复用：
  python3 github_trending.py                  # 日榜，stdout 输出 section JSON
  python3 github_trending.py --since weekly   # 周榜
  python3 github_trending.py --limit 15

无官方 API，解析 trending 页 HTML（article.Box-row 结构，多年稳定）。
失败返回 None / 空输出，调用方应容错跳过（简报照常出，不因 GitHub 挂了失败）。
"""
import sys, re, json, html, argparse, subprocess

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# 与 aihot_report.py 一致的灰产黑名单
BLACK = re.compile(r'(锁头|外挂|aimbot|aim.?assist|cheat|anti-?cheat|破解|私服|vpngate|翻墙|刷量)', re.I)

SINCE_LABEL = {"daily": "GitHub 今日趋势榜", "weekly": "GitHub 本周趋势榜", "monthly": "GitHub 本月趋势榜"}
STARS_WORD = {"daily": "今日", "weekly": "本周", "monthly": "本月"}


def _text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def fetch_trending(since="daily", limit=12, lang=""):
    """返回 build_report section dict，失败返回 None。"""
    url = f"https://github.com/trending/{lang}?since={since}" if lang else f"https://github.com/trending?since={since}"
    try:
        page = subprocess.run(
            ["curl", "-sf", "--max-time", "30", "-H", f"User-Agent: {UA}", url],
            capture_output=True, text=True, timeout=40).stdout
    except Exception:
        return None
    if not page:
        return None

    items = []
    for block in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S):
        m = re.search(r'<h2[^>]*>.*?href="/([^/"]+/[^/"]+)"', block, re.S)
        if not m:
            continue
        name = m.group(1)
        dm = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.S)
        desc = _text(dm.group(1)) if dm else ""
        if BLACK.search(name) or BLACK.search(desc):
            continue
        lm = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        language = lm.group(1).strip() if lm else "—"
        sm = re.search(r'href="/%s/stargazers"[^>]*>(.*?)</a>' % re.escape(name), block, re.S)
        total = _text(sm.group(1)) if sm else ""
        tm = re.search(r'([\d,]+)\s+stars\s+(?:today|this\s+week|this\s+month)', block)
        gained = tm.group(1) if tm else ""

        extra = f"⭐{total} · {language}"
        if gained:
            extra += f" · {STARS_WORD.get(since, '')}+{gained}"
        items.append({
            "title": name,
            "source": "GitHub Trending",
            "time": "",
            "summary": desc[:120],
            "url": f"https://github.com/{name}",
            "extra": extra,
        })
        if len(items) >= limit:
            break

    if not items:
        return None
    return {"label": SINCE_LABEL.get(since, "GitHub 趋势榜"), "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--lang", default="", help="限定语言，如 python")
    args = ap.parse_args()
    sec = fetch_trending(args.since, args.limit, args.lang)
    if not sec:
        print("[github-trending] 抓取失败或无结果", file=sys.stderr)
        sys.exit(1)
    json.dump(sec, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
