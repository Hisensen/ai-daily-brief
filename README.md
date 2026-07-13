# AI 每日简报（Codex 自动发布版）

每天采集 [AI HOT](https://aihot.virxact.com/) 精选和 GitHub 趋势，用 Codex 整理成中文公网简报，并发布到 GitHub Pages。

- 公网地址：<https://hisensen.github.io/ai-daily-brief/>
- `index.html`：当前首页
- `archive/`：每期采集器生成的原版 HTML
- `AGENTS.md`：Codex 的排版、内容和存档规则；以后想调整日报效果，优先改这里
- `scripts/aihot_daily.py`：纯 Python 采集器，不调用 Claude 或其他模型
- `scripts/aihot_daily_publish.py`：Codex 渲染、严格验收、Git 提交与发布
- `config/com.aihot.daily.plist`：本机定时任务模板

## 自动流程

macOS LaunchAgent 在北京时间 04:00 运行，并在登录和 12:33 做补偿检查。发布器会：

1. 先检查今天是否已在远端发布，避免重复出刊。
2. 优先续发桌面上已有的 `04:00` 简报；没有待处理文件才重新采集。
3. 预取趋势项目 README，然后让 Codex 在无 Git、无 GitHub 网络权限的临时目录里只生成 `index.html`。
4. 校验日期、条数、全部摘要和来源链接、GitHub 项目与中文说明、搞钱参考和历史存档。
5. 在基于远端 `main` 的临时 worktree 中只提交 `index.html` 与当日 archive，再核对推送前后 SHA 和远端归档内容。

用户当前工作区中的修改、未跟踪文件和 `.DS_Store` 不会被提交或删除。任何一步失败都会返回非零退出码、保留源简报并写入状态文件。

## 常用操作

在本仓库目录运行：

```bash
# 立即执行今天的完整流程
python3 scripts/aihot_daily_publish.py

# 补发指定日期的已有文件，并保留桌面源文件
python3 scripts/aihot_daily_publish.py \
  --date 2026-07-13 \
  --brief "$HOME/Desktop/aihot-简报-2026-07-13-0400.html" \
  --keep-brief

# 执行并在成功后打开公网页面
python3 scripts/aihot_daily_publish.py --open

# 运行回归测试
python3 tests/test_aihot_daily_publish.py -v
```

查看运行状态：

```bash
cat "$HOME/Library/Application Support/AI每日简报/status.json"
tail -n 100 "$HOME/Library/Logs/aihot-daily.log"
tail -n 100 "$HOME/Library/Logs/aihot-daily-error.log"
launchctl print "gui/$(id -u)/com.aihot.daily" | rg 'state =|runs =|last exit code'
```

## 以后怎么改

- 改选题整理、搞钱参考或页面结构：编辑 `AGENTS.md`。
- 改采集窗口、分类或数据处理：编辑 `scripts/aihot_daily.py`。
- 改发布校验和 GitHub 流程：编辑 `scripts/aihot_daily_publish.py`，并同步补测试。
- 改执行时间：编辑 `config/com.aihot.daily.plist` 的 `StartCalendarInterval`，复制到 `~/Library/LaunchAgents/com.aihot.daily.plist` 后重新加载。

重新安装定时任务：

```bash
cp config/com.aihot.daily.plist "$HOME/Library/LaunchAgents/com.aihot.daily.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.aihot.daily.plist"
launchctl bootout "gui/$(id -u)/com.aihot.daily" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.aihot.daily.plist"
launchctl enable "gui/$(id -u)/com.aihot.daily"
```

## 依赖检查

```bash
$HOME/.local/bin/codex login status
/usr/local/bin/gh auth status
git --version
curl --version
```

Codex 使用 ChatGPT 登录；GitHub 使用 `gh`/Git 凭证。无人值守任务不再调用 `claude` 命令，也不读取 `~/.claude` 下的脚本或规则。
