# AI 每日简报(手机公网版)

aihot 每日简报的公网发布仓库,GitHub Pages 托管,手机/任何人可直接访问。

- **公网地址**:https://hisensen.github.io/ai-daily-brief/
- `index.html` — 简报站页面(报头日期 → 💰今日搞钱参考 → 今日精选 → GitHub 趋势 → 往期存档折叠)
- `archive/` — 每期 aihot 原版 HTML 备份,页面存档区直接链接到这里

## 每日更新流程(由 Claude 自动执行,规则在 ~/.claude/CLAUDE.md)

1. aihot 生成当日简报后,把原版 HTML 复制进 `archive/`
2. 重写 `index.html`:新一期上头条,旧的"今日"降级为存档区新的 `<details>` 条目(带原版链接)
3. 「💰 今日搞钱参考」每条必须附参考链接(新闻原文 / GitHub 仓库)
4. `git add -A && git commit && git push`,Pages 自动更新
5. 每月 1 号清理:删除超过 30 天的 archive 文件与页面存档条目
