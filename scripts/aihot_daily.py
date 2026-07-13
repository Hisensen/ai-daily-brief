#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI HOT 每日开机简报（无 LLM，纯脚本，供 LaunchAgent 无人值守调用）。

行为：
  - 时间窗自动 = 距离上次成功运行的时长（首次 / state 丢失默认 24h；上限 7 天 = API 硬上限）
  - 拉 mode=selected 精选 → 五版块分组 + 时间转人话 + GitHub star 富化
  - 复用 build_report.py 的 render_html 出 HTML 到桌面并自动打开
  - 成功后把本次运行时间写入 state 文件
  - 防抖：距上次成功运行 < 6 小时直接退出（避免重启一天弹多次）

手动调试：
  python3 aihot_daily.py --force          # 忽略防抖
  python3 aihot_daily.py --no-open        # 不自动打开
"""
import sys, os, re, json, subprocess, datetime, math, time, argparse, zoneinfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report import render_html
from github_trending import fetch_trending

STATE = os.path.expanduser(
    "~/Library/Application Support/AI每日简报/collector_last_run"
)
GH = "/usr/local/bin/gh"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 aihot-skill/0.2.0-daily")
CN = zoneinfo.ZoneInfo("Asia/Shanghai")

LABELS = {
    "ai-models": "模型发布/更新",
    "ai-products": "产品发布/更新",
    "industry": "行业动态",
    "paper": "论文研究",
    "tip": "技巧与观点",
}
ORDER = ["模型发布/更新", "产品发布/更新", "行业动态", "论文研究", "技巧与观点", "其他"]
GH_RE = re.compile(r"github\.com/([\w.-]+)/([\w.-]+)")
GH_SKIP_OWNERS = {"blog", "features", "orgs", "topics", "trending", "sponsors"}


def log(msg):
    print(f"[aihot-daily] {msg}", file=sys.stderr)


def read_last_run():
    try:
        return datetime.datetime.fromisoformat(open(STATE).read().strip())
    except Exception:
        return None


def write_last_run(dt):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        f.write(dt.isoformat())


def fetch(url, retries=5):
    """curl 带重试——开机瞬间可能还没网。"""
    for i in range(retries):
        try:
            out = subprocess.run(
                ["curl", "-sf", "--max-time", "30", "-H", f"User-Agent: {UA}", url],
                capture_output=True, text=True, timeout=40)
            if out.returncode == 0 and out.stdout:
                raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", out.stdout)
                return json.loads(raw, strict=False)
        except Exception as e:
            log(f"fetch attempt {i+1} error: {e}")
        time.sleep(20 * (i + 1))
    return None


def human_time(iso, today):
    if not iso:
        return ""
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CN)
    d, hm = dt.date(), dt.strftime("%H:%M")
    if d == today:
        return f"今天 {hm}"
    if d == today - datetime.timedelta(days=1):
        return f"昨天 {hm}"
    if d == today - datetime.timedelta(days=2):
        return f"前天 {hm}"
    return f"{d.month}/{d.day} {hm}"


def gh_repo(item):
    for field in (item.get("url") or "", item.get("summary") or ""):
        m = GH_RE.search(field)
        if m and m.group(1) not in GH_SKIP_OWNERS:
            return f"{m.group(1)}/{m.group(2).rstrip('.')}"
    return None


_gh_cache = {}
def gh_badge(repo):
    if repo in _gh_cache:
        return _gh_cache[repo]
    badge = None
    if os.path.exists(GH):
        try:
            out = subprocess.run(
                [GH, "api", f"repos/{repo}", "--jq", "{s:.stargazers_count,l:.language}"],
                capture_output=True, text=True, timeout=15)
            if out.returncode == 0:
                j = json.loads(out.stdout)
                badge = f"⭐{j['s']:,}" + (f" · {j['l']}" if j.get("l") else "")
        except Exception:
            pass
    _gh_cache[repo] = badge
    return badge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略 6 小时防抖")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    now = datetime.datetime.now(CN)
    today = now.date()
    last = read_last_run()

    if last and not args.force and (now - last) < datetime.timedelta(hours=6):
        log(f"上次运行 {last:%m-%d %H:%M}，距今不足 6 小时，跳过")
        return

    # 时间窗 = 距上次运行时长，clamp [24h, 7d]
    if last:
        delta = now - last
        capped = delta > datetime.timedelta(days=7)
        delta = max(datetime.timedelta(hours=24), min(delta, datetime.timedelta(days=7)))
    else:
        delta, capped = datetime.timedelta(hours=24), False
    days = max(1, math.ceil(delta.total_seconds() / 86400))
    since_utc = (now - delta).astimezone(datetime.timezone.utc)
    since = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    log(f"时间窗 {days} 天（since {since}）")

    base = "https://aihot.virxact.com/api/public/items"
    data = fetch(f"{base}?mode=selected&since={since}&take=100")
    if data is None:
        log("API 拉取失败（重试后仍不可达），本次放弃，不更新 state")
        sys.exit(1)
    items = list(data.get("items", []))
    cursor = data.get("nextCursor")
    while cursor:
        time.sleep(0.5)
        page = fetch(f"{base}?mode=selected&since={since}&take=100&cursor={cursor}")
        if page is None:
            log("分页拉取失败，本次放弃，不生成简报也不更新 state")
            sys.exit(1)
        items.extend(page.get("items", []))
        cursor = page.get("nextCursor")
    log(f"共 {len(items)} 条")

    sections = {}
    for it in items:
        label = LABELS.get(it.get("category"), "其他")
        entry = {
            "title": it.get("title") or it.get("title_en") or "无标题",
            "source": it.get("source", ""),
            "time": human_time(it.get("publishedAt"), today),
            "summary": it.get("summary") or "",
            "url": it.get("url", ""),
        }
        repo = gh_repo(it)
        if repo:
            b = gh_badge(repo)
            if b:
                entry["extra"] = b
        sections.setdefault(label, []).append(entry)

    # GitHub 趋势榜：窗口 1 天走日榜，更久走周榜；失败容错跳过
    trend_since = "daily" if days <= 1 else "weekly"
    trending = None
    try:
        trending = fetch_trending(since=trend_since, limit=12)
    except Exception as e:
        log(f"github trending 抓取异常: {e}")
    if trending:
        log(f"github trending {trend_since}: {len(trending['items'])} 个仓库")
    else:
        log("github trending 无结果，跳过该版块")

    window = "过去 24 小时" if days <= 1 else f"最近 {days} 天"
    note = "（最多回看 7 天）" if capped else ""
    counts = " · ".join(f"{lb} {len(sections[lb])}" for lb in ORDER if lb in sections)
    if trending:
        counts += f" · {trending['label']} {len(trending['items'])}"
    report = {
        "title": "AI HOT 每日简报",
        "subtitle": f"{today.isoformat()} · {window}精选{note} · 共 {len(items)} 条 · 按发布时间倒序",
        "intro": f"自上次查看以来的 AI 精选动态：{counts}。" if items else "这段时间没有新的精选条目。",
        "sections": [{"label": lb, "items": sections[lb]} for lb in ORDER if lb in sections]
                    + ([trending] if trending else []),
    }

    out = os.path.expanduser(f"~/Desktop/aihot-简报-{today.isoformat()}-{now:%H%M}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_html(report))
    write_last_run(now)
    log(f"已生成 {out}")
    print(out)
    if not args.no_open:
        subprocess.run(["open", out], check=False)


if __name__ == "__main__":
    main()
