import importlib.util
import inspect
import base64
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "scripts" / "aihot_daily_publish.py"


class DailyPublisherTests(unittest.TestCase):
    def load_publisher(self):
        self.assertTrue(
            PUBLISHER.exists(),
            "Codex publisher script has not been implemented yet",
        )
        spec = importlib.util.spec_from_file_location("aihot_daily_publish", PUBLISHER)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_build_codex_command_is_unattended_and_has_no_claude_dependency(self):
        publisher = self.load_publisher()
        self.assertNotIn(
            "prompt",
            inspect.signature(publisher.build_codex_command).parameters,
            "prompt must be passed over stdin, not exposed in process arguments",
        )

        command = publisher.build_codex_command(
            codex_bin=Path("/opt/codex"),
            worktree=Path("/tmp/ai-daily-worktree"),
        )

        self.assertEqual(command[0], "/opt/codex")
        self.assertLess(command.index("--ask-for-approval"), command.index("exec"))
        self.assertIn("never", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("-s", command)
        self.assertIn("workspace-write", command)
        self.assertIn("-c", command)
        self.assertIn('approval_policy="never"', command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], "-")
        self.assertIn("-C", command)
        self.assertIn("/tmp/ai-daily-worktree", command)
        self.assertNotIn("claude", " ".join(command).lower())

    def test_published_snapshot_requires_today_and_today_archive(self):
        publisher = self.load_publisher()

        self.assertTrue(
            publisher.published_snapshot(
                "<h1>2026年7月13日</h1>",
                ["archive/aihot-简报-2026-07-13-1023.html"],
                today_cn="2026年7月13日",
                today_iso="2026-07-13",
            )
        )
        self.assertFalse(
            publisher.published_snapshot(
                "<h1>2026年7月13日</h1>",
                ["archive/aihot-简报-2026-07-12-0400.html"],
                today_cn="2026年7月13日",
                today_iso="2026-07-13",
            )
        )
        self.assertFalse(
            publisher.published_snapshot(
                "<h1>2026年7月12日</h1>",
                ["archive/aihot-简报-2026-07-13-1023.html"],
                today_cn="2026年7月13日",
                today_iso="2026-07-13",
            )
        )

    def test_unexpected_changes_rejects_files_outside_site_and_archive(self):
        publisher = self.load_publisher()

        self.assertEqual(
            publisher.unexpected_changes(
                ["index.html", "archive/aihot-简报-2026-07-13-1023.html"]
            ),
            [],
        )
        self.assertEqual(
            publisher.unexpected_changes(
                ["index.html", ".DS_Store", "scripts/aihot_daily_publish.py"]
            ),
            [".DS_Store", "scripts/aihot_daily_publish.py"],
        )

    def test_choose_scheduled_brief_prefers_the_0400_issue(self):
        publisher = self.load_publisher()
        self.assertTrue(
            hasattr(publisher, "choose_scheduled_brief"),
            "choose_scheduled_brief is missing",
        )
        with tempfile.TemporaryDirectory() as tmp:
            desktop = Path(tmp)
            scheduled = desktop / "aihot-简报-2026-07-13-0400.html"
            later_retry = desktop / "aihot-简报-2026-07-13-1023.html"
            wrong_day = desktop / "aihot-简报-2026-07-12-0400.html"
            for path in (scheduled, later_retry, wrong_day):
                path.write_text(path.name, encoding="utf-8")

            self.assertEqual(
                publisher.choose_scheduled_brief(desktop, "2026-07-13"),
                scheduled,
            )

    def test_run_process_preserves_failure_exit_code(self):
        publisher = self.load_publisher()

        result = publisher.run_process(
            [sys.executable, "-c", "raise SystemExit(7)"],
            cwd=ROOT,
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 7)

    def test_codex_ready_reflects_cli_login_preflight(self):
        publisher = self.load_publisher()
        self.assertTrue(hasattr(publisher, "codex_ready"), "codex_ready is missing")

        self.assertTrue(publisher.codex_ready(Path("/usr/bin/true"), ROOT))
        self.assertFalse(publisher.codex_ready(Path("/usr/bin/false"), ROOT))

    def test_build_prompt_uses_repo_rules_and_keeps_git_out_of_agent(self):
        publisher = self.load_publisher()
        self.assertTrue(hasattr(publisher, "build_prompt"), "build_prompt is missing")

        prompt = publisher.build_prompt(
            archive_name="aihot-简报-2026-07-13-1023.html",
            today_cn="2026年7月13日",
            today_iso="2026-07-13",
        )

        self.assertIn("AGENTS.md", prompt)
        self.assertIn("github-context.md", prompt)
        self.assertIn("archive/aihot-简报-2026-07-13-1023.html", prompt)
        self.assertIn("2026年7月13日", prompt)
        self.assertIn("只编辑 index.html", prompt)
        self.assertIn("不要执行 git", prompt)

    def test_validate_rendered_site_checks_date_archive_history_and_summaries(self):
        publisher = self.load_publisher()
        self.assertTrue(
            hasattr(publisher, "validate_rendered_site"),
            "validate_rendered_site is missing",
        )
        source = """
            <h1>AI HOT 每日简报</h1>
            <div class="summary">这是一段必须完整保留的摘要。</div>
            <h2>GitHub 今日趋势榜</h2>
        """
        previous = '<a href="archive/aihot-简报-2026-07-12-0400.html">旧刊</a>'
        rendered = """
            <h1>2026年7月13日</h1>
            <section class="money-sec" id="money"><h2>💰 今日搞钱参考</h2>
              <div class="item"><div class="angle">创业借鉴</div><div class="refs"><a href="https://example.com/one">参考一</a></div></div>
              <div class="item"><div class="angle">自媒体选题</div><div class="refs"><a href="https://example.com/two">参考二</a></div></div>
            </section>
            <section>GitHub 趋势榜</section>
            <p>这是一段必须完整保留的摘要。</p>
            <a href="archive/aihot-简报-2026-07-13-1023.html">原版</a>
            <a href="archive/aihot-简报-2026-07-12-0400.html">旧刊</a>
        """

        self.assertEqual(
            publisher.validate_rendered_site(
                previous_index=previous,
                rendered_index=rendered,
                source_html=source,
                archive_name="aihot-简报-2026-07-13-1023.html",
                today_cn="2026年7月13日",
                preserve_history=True,
            ),
            [],
        )

        broken = rendered.replace("这是一段必须完整保留的摘要。", "摘要被删了")
        errors = publisher.validate_rendered_site(
            previous_index=previous,
            rendered_index=broken,
            source_html=source,
            archive_name="aihot-简报-2026-07-13-1023.html",
            today_cn="2026年7月13日",
            preserve_history=True,
        )
        self.assertTrue(any("摘要" in error for error in errors), errors)

        broken_money = rendered.replace(
            'href="https://example.com/one"', 'data-missing-href="one"'
        )
        errors = publisher.validate_rendered_site(
            previous_index=previous,
            rendered_index=broken_money,
            source_html=source,
            archive_name="aihot-简报-2026-07-13-1023.html",
            today_cn="2026年7月13日",
            preserve_history=True,
        )
        self.assertTrue(any("搞钱" in error for error in errors), errors)

    def test_validate_rendered_site_allows_chinese_trend_rewrite_and_checks_top_h1(self):
        publisher = self.load_publisher()
        source = """
            <div class="summary">新闻完整摘要。</div>
            <h2>GitHub 本周趋势榜</h2>
            <a href="https://github.com/acme/widget">acme/widget</a>
            <div class="summary">English repository description.</div>
        """
        rendered = """
            <h1>2026年7月13日</h1>
            <section class="money-sec" id="money"><h2>💰 今日搞钱参考</h2>
              <div class="item"><div class="angle">创业借鉴</div><div class="refs"><a href="https://example.com/one">参考一</a></div></div>
              <div class="item"><div class="angle">求职谈资</div><div class="refs"><a href="https://example.com/two">参考二</a></div></div>
            </section>
            <p>新闻完整摘要。</p>
            <section>GitHub 趋势榜
              <li><a href="https://github.com/acme/widget">acme/widget</a>
              <span class="desc"><b>解决什么问题:</b>解决团队协作问题。<b>大致内容:</b>提供中文项目说明。</span></li>
            </section>
            <a href="archive/aihot-简报-2026-07-13-0400.html">原版</a>
        """
        self.assertEqual(
            publisher.validate_rendered_site(
                previous_index="",
                rendered_index=rendered,
                source_html=source,
                archive_name="aihot-简报-2026-07-13-0400.html",
                today_cn="2026年7月13日",
                preserve_history=True,
            ),
            [],
        )

        stale_h1 = rendered.replace(
            "<h1>2026年7月13日</h1>",
            "<h1>2026年7月12日</h1><p>正文提到 2026年7月13日</p>",
        )
        errors = publisher.validate_rendered_site(
            previous_index="",
            rendered_index=stale_h1,
            source_html=source,
            archive_name="aihot-简报-2026-07-13-0400.html",
            today_cn="2026年7月13日",
            preserve_history=True,
        )
        self.assertTrue(any("日期" in error for error in errors), errors)

    def test_validate_rendered_site_preserves_news_links_and_declared_counts(self):
        publisher = self.load_publisher()
        source = """
            <div class="sub">2026-07-13 · 最近 2 天精选 · 共 2 条</div>
            <a class="title" href="https://news.example.com/one">新闻一</a>
            <div class="summary">新闻一完整摘要。</div>
            <a class="title" href="https://news.example.com/two">新闻二</a>
            <div class="summary">新闻二完整摘要。</div>
            <h2>GitHub 本周趋势榜</h2>
            <a href="https://github.com/acme/one">acme/one</a>
            <a href="https://github.com/acme/two">acme/two</a>
        """
        rendered = """
            <h1>2026年7月13日</h1>
            <section id="today"><h2>今日精选</h2><span>2 条</span>
            <a href="https://news.example.com/one">新闻一</a><p>新闻一完整摘要。</p>
            <a href="https://news.example.com/two">新闻二</a><p>新闻二完整摘要。</p>
            </section>
            <section class="money-sec"><h2>今日搞钱参考</h2>
              <div class="angle">创业借鉴</div><div class="refs"><a href="https://news.example.com/one">参考一</a></div>
              <div class="angle">求职谈资</div><div class="refs"><a href="https://news.example.com/two">参考二</a></div>
            </section>
            <h2>GitHub 本周趋势榜 2 个项目</h2>
            <li><a href="https://github.com/acme/one">acme/one</a><span><b>解决什么问题:</b>解决一。<b>大致内容:</b>内容一。</span></li>
            <li><a href="https://github.com/acme/two">acme/two</a><span><b>解决什么问题:</b>解决二。<b>大致内容:</b>内容二。</span></li>
            <a href="archive/aihot-简报-2026-07-13-0400.html">原版</a>
        """
        self.assertEqual(
            publisher.validate_rendered_site(
                previous_index="",
                rendered_index=rendered,
                source_html=source,
                archive_name="aihot-简报-2026-07-13-0400.html",
                today_cn="2026年7月13日",
                preserve_history=True,
            ),
            [],
        )

        broken = rendered.replace(
            '<a href="https://news.example.com/two">新闻二</a>',
            '<span>新闻二</span>',
        ).replace("<span>2 条</span>", "<span>1 条</span>", 1)
        errors = publisher.validate_rendered_site(
            previous_index="",
            rendered_index=broken,
            source_html=source,
            archive_name="aihot-简报-2026-07-13-0400.html",
            today_cn="2026年7月13日",
            preserve_history=True,
        )
        self.assertTrue(any("来源链接" in error for error in errors), errors)
        self.assertTrue(any("精选数量" in error for error in errors), errors)

    def test_extract_github_repos_is_unique_and_skips_non_repo_paths(self):
        publisher = self.load_publisher()
        self.assertTrue(
            hasattr(publisher, "extract_github_repos"),
            "extract_github_repos is missing",
        )
        source = """
            <a href="https://github.com/acme/widget">one</a>
            <a href="https://github.com/acme/widget/issues">duplicate</a>
            <a href="https://github.com/blog/changelog">not a repo</a>
            <a href="https://github.com/other/tool?tab=readme">two</a>
        """

        self.assertEqual(
            publisher.extract_github_repos(source),
            ["acme/widget", "other/tool"],
        )

    def test_fetch_github_readme_decodes_gh_api_response(self):
        publisher = self.load_publisher()
        self.assertTrue(
            hasattr(publisher, "fetch_github_readme"),
            "fetch_github_readme is missing",
        )
        with tempfile.TemporaryDirectory() as tmp:
            fake_gh = Path(tmp) / "gh"
            encoded = base64.b64encode("中文 README 内容".encode()).decode()
            fake_gh.write_text(
                "#!/bin/sh\nprintf '%s\\n' '" + encoded + "'\n",
                encoding="utf-8",
            )
            os.chmod(fake_gh, 0o755)

            self.assertEqual(
                publisher.fetch_github_readme(fake_gh, "acme/widget"),
                "中文 README 内容",
            )

    def test_collector_is_vendored_and_collect_brief_validates_its_output(self):
        publisher = self.load_publisher()
        collector = ROOT / "scripts" / "aihot_daily.py"
        self.assertTrue(collector.is_file(), "采集器应纳入当前 Codex 项目")
        self.assertNotIn(".claude", collector.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            desktop.mkdir()
            output = desktop / "aihot-简报-2026-07-13-0400.html"
            fake_collector = root / "collector.py"
            fake_collector.write_text(
                "from pathlib import Path\n"
                f"p = Path({str(output)!r})\n"
                "p.write_text('<h1>AI HOT 每日简报</h1>', encoding='utf-8')\n"
                "print(p)\n",
                encoding="utf-8",
            )

            selected = publisher.collect_brief(
                generator=fake_collector,
                desktop=desktop,
                today_iso="2026-07-13",
                python_bin=Path(sys.executable),
            )
            self.assertEqual(selected, output.resolve())

            silent_collector = root / "silent.py"
            silent_collector.write_text("pass\n", encoding="utf-8")
            with self.assertRaises(publisher.PublishError):
                publisher.collect_brief(
                    generator=silent_collector,
                    desktop=desktop,
                    today_iso="2026-07-13",
                    python_bin=Path(sys.executable),
                )

    def test_main_returns_nonzero_records_failure_and_preserves_brief(self):
        publisher = self.load_publisher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            site = root / "site"
            state_dir = root / "state"
            self.git(root, "init", "--bare", str(remote))
            self.git(root, "init", str(site))
            self.git(site, "checkout", "-b", "main")
            self.git(site, "config", "user.name", "Test Publisher")
            self.git(site, "config", "user.email", "publisher@example.com")
            (site / "archive").mkdir()
            (site / "index.html").write_text(
                "<h1>2026年7月12日</h1>", encoding="utf-8"
            )
            (site / "AGENTS.md").write_text("规则", encoding="utf-8")
            self.git(site, "add", "index.html", "AGENTS.md", "archive")
            self.git(site, "commit", "-m", "initial")
            self.git(site, "remote", "add", "origin", str(remote))
            self.git(site, "push", "-u", "origin", "main")

            brief = root / "aihot-简报-2026-07-13-0400.html"
            brief.write_text("<h1>AI HOT 每日简报</h1>", encoding="utf-8")
            exit_code = publisher.main(
                [
                    "--site",
                    str(site),
                    "--brief",
                    str(brief),
                    "--date",
                    "2026-07-13",
                    "--codex",
                    "/usr/bin/false",
                    "--gh",
                    "/usr/bin/false",
                    "--expected-remote",
                    str(remote),
                    "--state-dir",
                    str(state_dir),
                    "--no-notify",
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertTrue(brief.is_file(), "失败时必须保留源简报")
            status = json.loads((state_dir / "status.json").read_text())
            self.assertEqual(status["status"], "FAILED")
            self.assertIn("Codex", status["message"])

    def test_publish_existing_brief_uses_remote_worktree_and_preserves_user_checkout(self):
        publisher = self.load_publisher()
        self.assertTrue(
            hasattr(publisher, "publish_existing_brief"),
            "publish_existing_brief is missing",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            site = root / "site"
            self.git(root, "init", "--bare", str(remote))
            self.git(root, "init", str(site))
            self.git(site, "checkout", "-b", "main")
            self.git(site, "config", "user.name", "Test Publisher")
            self.git(site, "config", "user.email", "publisher@example.com")
            (site / "archive").mkdir()
            (site / "archive" / "aihot-简报-2026-07-12-0400.html").write_text(
                "old archive", encoding="utf-8"
            )
            (site / "index.html").write_text(
                '<h1>2026年7月12日</h1><section>GitHub 趋势榜</section>'
                '<a href="archive/aihot-简报-2026-07-12-0400.html">旧刊</a>',
                encoding="utf-8",
            )
            (site / "AGENTS.md").write_text("只处理日报。", encoding="utf-8")
            self.git(site, "add", "index.html", "archive", "AGENTS.md")
            self.git(site, "commit", "-m", "initial")
            self.git(site, "remote", "add", "origin", str(remote))
            self.git(site, "push", "-u", "origin", "main")
            old_sha = self.git(site, "rev-parse", "HEAD")

            # Simulate user-owned dirty and untracked files in the primary checkout.
            (site / "index.html").write_text("LOCAL USER EDIT", encoding="utf-8")
            (site / ".DS_Store").write_bytes(b"finder")
            (site / "secret.txt").write_text("do not publish", encoding="utf-8")

            brief = root / "aihot-简报-2026-07-13-0400.html"
            brief.write_text(
                '<div class="summary">这是一段必须完整保留的摘要。</div>'
                '<h2>GitHub 今日趋势榜</h2>',
                encoding="utf-8",
            )
            fake_codex = root / "fake-codex"
            fake_codex.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import re
                    import sys
                    from pathlib import Path

                    if sys.argv[1:] == ["login", "status"]:
                        raise SystemExit(0)
                    prompt = sys.stdin.read()
                    archive = re.search(r"archive/([^。 ]+\\.html)", prompt).group(1)
                    Path("index.html").write_text(
                        '<h1>2026年7月13日</h1>'
                        '<section class="money-sec" id="money"><h2>💰 今日搞钱参考</h2>'
                        '<div class="item"><div class="angle">创业借鉴</div><div class="refs"><a href="https://example.com/one">参考一</a></div></div>'
                        '<div class="item"><div class="angle">自媒体选题</div><div class="refs"><a href="https://example.com/two">参考二</a></div></div>'
                        '</section>'
                        '<section>GitHub 趋势榜</section>'
                        '<p>这是一段必须完整保留的摘要。</p>'
                        f'<a href="archive/{archive}">今日原版</a>'
                        '<a href="archive/aihot-简报-2026-07-12-0400.html">旧刊</a>',
                        encoding="utf-8",
                    )
                    """
                ),
                encoding="utf-8",
            )
            os.chmod(fake_codex, 0o755)

            new_sha = publisher.publish_existing_brief(
                site=site,
                brief=brief,
                codex_bin=fake_codex,
                today_cn="2026年7月13日",
                today_iso="2026-07-13",
                expected_remote=None,
            )

            self.assertNotEqual(new_sha, old_sha)
            changed = self.git(
                site,
                "-c",
                "core.quotepath=false",
                "diff",
                "--name-only",
                old_sha,
                new_sha,
            ).splitlines()
            self.assertEqual(
                changed,
                [
                    "archive/aihot-简报-2026-07-13-0400.html",
                    "index.html",
                ],
            )
            self.assertEqual((site / "index.html").read_text(), "LOCAL USER EDIT")
            self.assertEqual((site / ".DS_Store").read_bytes(), b"finder")
            self.assertEqual((site / "secret.txt").read_text(), "do not publish")
            archived = self.git(
                site,
                "show",
                f"{new_sha}:archive/aihot-简报-2026-07-13-0400.html",
            )
            self.assertEqual(archived, brief.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
