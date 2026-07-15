#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI HOT 资讯 → 精美 HTML / PDF 报告生成器。

分工：agent 负责拉数据 / 分组 / 把时间转人话 / 富化（star 等），
本脚本只负责把"结构化条目 JSON"排版成一份杂志感的页面，每条带可点击链接。

输入：从 stdin 读一个 JSON（结构见下），或用 --in 指定文件。
输出：--out 以 .html 结尾 → 直接写自包含 HTML 并用默认浏览器打开（无 Chrome 依赖）；
      否则走 Chrome headless 出 PDF（默认 ~/Desktop/aihot-report-<date>.pdf）。

输入 JSON 结构：
{
  "title":    "AI HOT 日报",                 # 大标题
  "subtitle": "2026-05-31 · 昨天与今天精选",  # 副标题（人话级元信息）
  "intro":    "可选：一段导语/今日要点",        # 可空
  "sections": [
    {
      "label": "模型发布/更新",
      "items": [
        {
          "title":   "谷歌 Nano Banana Pro 正式发布",
          "source":  "Google AI for Developers",
          "time":    "今天凌晨",          # 已转成人话的时间，可空
          "summary": "两款图像模型已可经 Gemini API 投产…",
          "url":     "https://x.com/...",
          "extra":   "⭐588 · C++"        # 可选徽标（star/语言等），可空
        }
      ]
    }
  ]
}

用法：
  cat report.json | python3 build_report.py --out ~/Desktop/ai.pdf
  python3 build_report.py --in report.json            # 默认输出到桌面并打开
  ... --no-open                                        # 不自动打开
"""
import sys, os, json, html, subprocess, tempfile, datetime, argparse

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 版块固定配色（与 AI HOT 五版块对齐；未知 label 用默认灰蓝）
SECTION_COLORS = {
    "模型发布/更新": "#6d28d9",
    "产品发布/更新": "#2563eb",
    "行业动态":     "#0891b2",
    "论文研究":     "#16a34a",
    "技巧与观点":   "#ea580c",
    "🎨 AIGC × 电商 × 自媒体变现雷达": "#db2777",
    "快讯":         "#64748b",
    "GitHub 本周开源热榜": "#24292f",
    "GitHub 今日趋势榜": "#24292f",
    "GitHub 本周趋势榜": "#24292f",
    "GitHub 本月趋势榜": "#24292f",
    "GitHub 趋势榜":     "#24292f",
}
DEFAULT_COLOR = "#475569"

CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 20mm 16mm;
  @bottom-center { content: counter(page) " / " counter(pages); }
}
* { box-sizing: border-box; }
body {
  font-family: "PingFang SC", "Microsoft YaHei", "Hiragino Sans GB", sans-serif;
  color: #1e293b; line-height: 1.7; margin: 0;
  -webkit-font-smoothing: antialiased;
}
.cover {
  border-bottom: 4px solid #0f172a; padding-bottom: 18px; margin-bottom: 28px;
}
.cover .brand {
  font-size: 12px; letter-spacing: 3px; color: #64748b;
  text-transform: uppercase; font-weight: 700;
}
.cover h1 {
  font-size: 34px; margin: 8px 0 6px; color: #0f172a; font-weight: 800;
  letter-spacing: -0.5px;
}
.cover .subtitle { font-size: 15px; color: #475569; font-weight: 500; }
.intro {
  background: #f8fafc; border-left: 4px solid #0f172a; border-radius: 0 8px 8px 0;
  padding: 12px 16px; margin-bottom: 28px; font-size: 14px; color: #334155;
}
.section { margin-bottom: 26px; break-inside: avoid-page; }
.section-head {
  display: flex; align-items: center; gap: 10px; margin-bottom: 14px;
}
.section-head .bar { width: 6px; height: 22px; border-radius: 3px; }
.section-head h2 {
  font-size: 19px; margin: 0; font-weight: 800; color: #0f172a;
}
.section-head .count { font-size: 12px; color: #94a3b8; font-weight: 600; }
.item {
  padding: 12px 0 14px; border-bottom: 1px solid #e2e8f0; break-inside: avoid;
}
.item:last-child { border-bottom: none; }
.item .line1 { display: flex; align-items: baseline; gap: 8px; }
.item .num {
  font-size: 13px; font-weight: 800; color: #cbd5e1; min-width: 26px;
}
.item .title {
  font-size: 15.5px; font-weight: 700; color: #0f172a; text-decoration: none;
  line-height: 1.45;
}
.item .title:hover { text-decoration: underline; }
.item .meta {
  margin: 3px 0 0 34px; font-size: 12px; color: #64748b;
}
.item .meta .src { color: #475569; font-weight: 600; }
.item .meta .badge {
  display: inline-block; margin-left: 8px; padding: 1px 7px; border-radius: 10px;
  background: #fef3c7; color: #92400e; font-weight: 700; font-size: 11px;
}
.item .summary {
  margin: 6px 0 0 34px; font-size: 13px; color: #334155; line-height: 1.65;
}
.item .src-link {
  margin: 6px 0 0 34px; font-size: 12px;
}
.item .src-link a { color: #2563eb; text-decoration: none; font-weight: 600; }
.item .src-link a:hover { text-decoration: underline; }
.radar-note {
  margin: 0 0 12px; font-size: 12.5px; color: #9d174d; line-height: 1.6;
  background: #fdf2f8; border-radius: 8px; padding: 8px 12px;
}
.radar { display: flex; flex-direction: column; gap: 2px; }
.radar-item { padding: 7px 0; border-bottom: 1px dashed #f6d4e4; break-inside: avoid; }
.radar-item:last-child { border-bottom: none; }
.radar-item .radar-link {
  font-size: 14.5px; font-weight: 700; color: #be185d; text-decoration: none; line-height: 1.5;
}
.radar-item .radar-link:hover { text-decoration: underline; }
.radar-item .radar-meta { font-size: 12px; color: #9d5877; margin-left: 8px; }
.footer {
  margin-top: 30px; padding-top: 14px; border-top: 1px solid #e2e8f0;
  font-size: 11px; color: #94a3b8; text-align: center;
}
@media screen {
  body { max-width: 860px; margin: 0 auto; padding: 36px 28px 48px; background: #fff; }
}
"""

def esc(s):
    return html.escape(str(s)) if s is not None else ""

def render_item(it, num):
    title = esc(it.get("title", "无标题"))
    url   = it.get("url", "")
    src   = esc(it.get("source", ""))
    time  = esc(it.get("time", ""))
    summ  = esc(it.get("summary", ""))
    extra = esc(it.get("extra", ""))

    title_html = f'<a class="title" href="{esc(url)}">{title}</a>' if url else f'<span class="title">{title}</span>'
    badge = f'<span class="badge">{extra}</span>' if extra else ""
    meta_bits = []
    if src:  meta_bits.append(f'<span class="src">{src}</span>')
    if time: meta_bits.append(time)
    meta = (" · ".join(meta_bits)) + badge if meta_bits or badge else ""

    parts = [f'<div class="item">']
    parts.append(f'<div class="line1"><span class="num">{num:02d}</span>{title_html}</div>')
    if meta: parts.append(f'<div class="meta">{meta}</div>')
    if summ: parts.append(f'<div class="summary">{summ}</div>')
    if url:  parts.append(f'<div class="src-link"><a href="{esc(url)}">查看原文 →</a></div>')
    parts.append('</div>')
    return "\n".join(parts)

def render_radar_item(it):
    """变现雷达用的紧凑条目：标题(链接) + 来源 · 时间，不含摘要。
    完整摘要在下方各版块，这里只是一层「搞钱视角」的跳转索引，避免重复大段内容。
    刻意不用 class="title" / class="summary"，以免被发布器的条数校验重复计入。"""
    title = esc(it.get("title", "无标题"))
    url   = it.get("url", "")
    meta  = " · ".join(x for x in [esc(it.get("source", "")), esc(it.get("time", ""))] if x)
    link  = (f'<a class="radar-link" href="{esc(url)}">{title}</a>' if url
             else f'<span class="radar-link">{title}</span>')
    meta_html = f'<span class="radar-meta">{meta}</span>' if meta else ""
    return f'<div class="radar-item">{link}{meta_html}</div>'

def render_html(data):
    title    = esc(data.get("title", "AI HOT 报告"))
    subtitle = esc(data.get("subtitle", ""))
    intro    = esc(data.get("intro", ""))
    sections = data.get("sections", [])

    body = [f'<div class="cover"><div class="brand">AI HOT · aihot.virxact.com</div>'
            f'<h1>{title}</h1><div class="subtitle">{subtitle}</div></div>']
    if intro:
        body.append(f'<div class="intro">{intro}</div>')

    num = 0
    for sec in sections:
        label = sec.get("label", "")
        items = sec.get("items", [])
        if not items:
            continue
        color = SECTION_COLORS.get(label, DEFAULT_COLOR)
        body.append('<div class="section">')
        body.append(f'<div class="section-head"><span class="bar" style="background:{color}"></span>'
                    f'<h2>{esc(label)}</h2><span class="count">{len(items)} 条</span></div>')
        if sec.get("compact"):
            # 紧凑索引版块（如变现雷达）：不参与全局编号，条目是下方各版块的跳转镜头
            if sec.get("note"):
                body.append(f'<div class="radar-note">{esc(sec["note"])}</div>')
            body.append('<div class="radar">')
            for it in items:
                body.append(render_radar_item(it))
            body.append('</div>')
        else:
            for it in items:
                num += 1
                body.append(render_item(it, num))
        body.append('</div>')

    today = datetime.date.today().isoformat()
    body.append(f'<div class="footer">本报告由 aihot skill 自动生成 · 数据来自 aihot.virxact.com · {today} · 共 {num} 条</div>')

    return f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{"".join(body)}</body></html>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", default=None)
    ap.add_argument("--out", dest="outfile", default=None)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    raw = open(args.infile, encoding="utf-8").read() if args.infile else sys.stdin.read()
    data = json.loads(raw)

    out = args.outfile
    if not out:
        out = os.path.expanduser(f"~/Desktop/aihot-report-{datetime.date.today().isoformat()}.pdf")
    out = os.path.expanduser(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    html_str = render_html(data)

    # HTML 直出模式：--out 以 .html 结尾时不走 Chrome，直接落盘并用默认浏览器打开
    if out.lower().endswith(".html"):
        with open(out, "w", encoding="utf-8") as f:
            f.write(html_str)
        print(out)
        if not args.no_open:
            subprocess.run(["open", out], check=False)
        return

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        html_path = f.name
        f.write(html_str)

    if not os.path.exists(CHROME):
        print(f"ERROR: 未找到 Chrome: {CHROME}", file=sys.stderr)
        sys.exit(1)

    subprocess.run([
        CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={out}", f"file://{html_path}"
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.unlink(html_path)

    print(out)  # 把生成路径打到 stdout，方便 agent 拿到
    if not args.no_open:
        subprocess.run(["open", out], check=False)

if __name__ == "__main__":
    main()
