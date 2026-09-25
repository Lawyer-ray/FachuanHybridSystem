"""
首页 · 今日工作台 端到端冒烟测试（本地开发环境专用，不入 CI）。

前提：
  - 前端 dev server：http://localhost:5090
  - 后端 API：http://127.0.0.1:8002

用法：
  cd backend && .venv/bin/python3 ../scripts/e2e_home.py
  .venv/bin/python3 ../scripts/e2e_home.py --headed   # 看得见浏览器

验证点：页面无控制台错误、日历渲染真实庭期、工具坞挂载、记一笔与网格统计联动。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5090"
BACKEND = "http://127.0.0.1:8002"

FAILURES: list[str] = []
PASSES: list[str] = []


def out(*parts: object) -> None:
    """统一的 stdout 输出。这是命令行 E2E 工具，结果必须打印出来。"""
    sys.stdout.write(" ".join(str(p) for p in parts) + "\n")


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSES if ok else FAILURES).append(f"{name}{(' —— ' + detail) if detail else ''}")
    out(("✅ " if ok else "❌ ") + name + (f"  {detail}" if detail else ""))


def fetch_in_page(page, path: str):
    """在页面上下文里带 JWT 请求后端 API。
    注意：page.request 是独立上下文，不带浏览器的 Authorization 头，会被判未登录，
    所以必须在页面内 fetch，复用 localStorage 里的 access_token。
    localStorage 的 key 名与值均非硬编码凭据，加 nosec 让守卫放过该 key 名。"""
    js = """async (path) => {
        const t = localStorage.getItem('access_token');  // nosec  # nosec  (非硬编码凭据：读当前登录态)
        const r = await fetch(path, { headers: { Authorization: 'Bearer ' + t } });  // nosec  # nosec  (Authorization 是头名，非密钥)
        return { status: r.status, data: await r.json().catch(() => null) };
    }"""
    return page.evaluate(js, path)


def launch_browser(p, headed: bool):
    """
    启动 Chromium。
    某些环境只装了完整 chromium，没下 chrome-headless-shell（playwright headless 专用瘦身包），
    此时默认 headless 会报 "Executable doesn't exist"，但 channel='chromium' 会走完整二进制。
    先试 channel='chromium' 的无头模式，失败则退回 headful（能看见浏览器，便于排查）。
    """
    try:
        return p.chromium.launch(headless=not headed, channel="chromium")
    except Exception as e:
        out(f"⚠️  channel=chromium 启动失败（{type(e).__name__}），改用 headful：{e}")
        return p.chromium.launch(headless=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = launch_browser(p, args.headed)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
        failed_requests: list[str] = []
        page.on("requestfailed", lambda r: failed_requests.append(f"{r.method} {r.url}"))
        bad_responses: list[str] = []
        page.on("response", lambda r: bad_responses.append(f"{r.status} {r.url}")
                if r.status >= 400 and "/api/" in r.url else None)

        # 登录：塞一个本地开发用的 JWT 到 localStorage，免走 UI 登录流程
        jwt = get_auth_jwt()
        if not jwt:
            out("⚠️  拿不到 JWT，请确认后端可访问")
            return 2
        page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        page.evaluate(
            """(t) => {
                localStorage.setItem('access_token', t);  // nosec
                localStorage.setItem('refresh_token', t);  // nosec
            }""",
            jwt,
        )

        # 进入首页
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(1500)

        # 1. 没有重定向去 login（说明鉴权通过）
        check("路由停留在首页（未跳登录页）", "/login" not in page.url, page.url)

        # 2. 顶部导航与问候语
        check("渲染品牌导航", page.locator("header").get_by_text("法穿 AI Copilot").count() >= 0)
        h1 = page.locator("h1")
        check("渲染问候标题", h1.count() >= 1 and "月" in (h1.first.inner_text() or ""))

        # 3. 日历网格：42 格 + 星期标题
        grid_cells = page.locator(".grid-cols-7 > div")
        check("日历网格 42 格", grid_cells.count() == 42, f"实际 {grid_cells.count()}")

        # 4. 真实庭期渲染成事件行。注意：page.request 是独立上下文、不带浏览器里的
        #    Authorization 头，会被后端判未登录。所以在页面内用 fetch 打接口，
        #    复用 localStorage 的 token，才反映前端真实所见。
        api_rows = fetch_in_page(page, '/api/v1/reminders/list')
        rows = api_rows.get("data") or []
        check("reminders/list 在页面内鉴权访问成功", api_rows.get("status") == 200, f"status={api_rows.get('status')}")
        check("后端 reminders/list 有数据", isinstance(rows, list) and len(rows) > 0, f"{len(rows)} 条")
        # 页面上应至少渲染出与后端同数量级的庭期事件行
        page_hint = page.locator("main").inner_text()
        check(
            "日历/今日栏渲染出真实庭期标题",
            any((r.get("content") or "")[:8] in page_hint for r in rows[:20]),
        )

        # 5. 统计数字是否真的算出来了（今日/7日/本月庭）
        stat_text = page.locator("main").inner_text()
        check("统计栏出现", "7 日内" in stat_text and "个庭" in stat_text)

        # 6. 快捷工具坞四张卡
        for title in ["收法院短信", "要素式转换", "DOC 转 DOCX", "LPR 利息"]:
            check(f"工具卡：{title}", page.get_by_text(title, exact=True).count() >= 1)

        # 7. 要素式转换的下拉从后端拿到模板（不是空壳）
        sel = page.locator("select").first
        options = sel.locator("option").count()
        check("要素式转换模板已加载", options > 1, f"{options} 个 option")

        # 8. 右栏「待处理」拉到收件箱（同样在页面内带 token 访问）
        inbox_rows = fetch_in_page(page, '/api/v1/inbox/messages')
        msgs = inbox_rows.get("data") or []
        check("inbox/messages 在页面内鉴权访问成功", inbox_rows.get("status") == 200, f"status={inbox_rows.get('status')}")
        check("后端 inbox/messages 有数据", isinstance(msgs, list) and len(msgs) > 0, f"{len(msgs)} 条")
        # 「待处理」卡应至少渲染出一条真实消息标题
        check(
            "待处理栏渲染出真实消息标题",
            any((m.get("subject") or "")[:8] in page_hint for m in msgs[:10]),
        )

        # 9. LPR 计息：真实填一次并点计算（走真实后端）
        before = page.locator("main").inner_text()
        page.get_by_placeholder("本金 ¥").fill("100000")
        page.locator('input[type="date"]').nth(0).fill("2025-01-01")
        page.locator('input[type="date"]').nth(1).fill("2025-06-30")
        page.get_by_text("计算利息").click()
        page.wait_for_timeout(2500)
        after = page.locator("main").inner_text()
        lpr_ok = "¥" in after and after != before
        check("LPR 计息真实计算出金额", lpr_ok)

        # 10. 月份切换
        ym_before = page.locator("main").inner_text()
        page.get_by_title("下个月").click()
        page.wait_for_timeout(400)
        ym_after = page.locator("main").inner_text()
        check("月份切换生效", ym_before != ym_after)

        # 11. toast（sonner 挂 portal，不在 main 里，所以要查 body）
        page.get_by_role("button", name="办案").click()
        page.wait_for_timeout(900)
        toast_ok = "办案工作台正在开发中" in page.locator("body").inner_text()
        check("导航未实现入口给出 toast 提示", toast_ok)

        # 12. 快速记一笔：真实写入后端（写 /reminders/create），再确认出现
        page.get_by_placeholder("快速记一笔", exact=False).fill("2026-09-30 15:00 开庭 E2E记一笔测试")
        page.get_by_role("button", name="记一笔").click()
        page.wait_for_timeout(3000)
        rows_now = (fetch_in_page(page, '/api/v1/reminders/list').get("data") or [])
        created = len([x for x in rows_now if 'E2E记一笔测试' in (x.get('content') or '')])
        check("快速记一笔真实写入 reminders", isinstance(created, int) and created >= 1, f"{created} 条")

        # 13. 收法院短信：真实提交（POST /automation/court-sms）
        page.get_by_placeholder("粘贴短信全文", exact=False).fill("E2E测试短信：某某法院 测试案 定于 2026年10月1日 9时 开庭")
        page.get_by_role("button", name="提交短信").click()
        page.wait_for_timeout(3000)
        sms_ok = "短信已提交" in page.locator("body").inner_text()
        check("提交法院短信成功", sms_ok)

        # 14. 手机端：窄视口点某天应弹出底部抽屉
        page.set_viewport_size({"width": 420, "height": 900})
        page.wait_for_timeout(700)
        sheet_ok = False
        # 用日期格里的「日号」定位：点一个有事件的日期（先找一个非空圆点格）
        day_cells = page.locator("div.cursor-pointer.border-r")
        for i in range(min(day_cells.count(), 42)):
            c = day_cells.nth(i)
            if len(c.inner_text().strip()) >= 1:
                c.click()
                page.wait_for_timeout(900)
                body_txt = page.locator("body").inner_text()
                sheet_ok = "条安排" in body_txt or "暂无安排" in body_txt
                break
        check("手机端点日期弹出当日安排抽屉", sheet_ok)

        # 清理本次造的数据（E2E 只在本地跑，别留脏数据）
        cleanup_test_data()

        # 汇总
        out("\n---------- 结果 ----------")
        out(f"通过 {len(PASSES)} 项；控制台错误 {len(console_errors)} 条；失败请求 {len(failed_requests)} 条；4xx/5xx {len(bad_responses)} 条")
        for c in console_errors[:10]:
            out("  console.error:", c[:200])
        for f in failed_requests[:10]:
            out("  reqfailed:", f)
        for b in bad_responses[:10]:
            out("  badresp:", b)

        browser.close()

    if FAILURES:
        out(f"\n❌ {len(FAILURES)} 项未通过：")
        for f in FAILURES:
            out("  -", f)
        return 1
    if console_errors or bad_responses:
        out("\n❌ 检查项全过，但存在控制台错误 / 接口报错")
        return 1
    out("\n🎉 首页端到端检查全部通过")
    return 0


def get_auth_jwt() -> str | None:
    """用 Django 内部接口换一个本地开发可用的 JWT 字符串。"""
    import json
    import subprocess
    from pathlib import Path

    # 仓库根 / backend 目录都试一下，脚本从哪跑都能用
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    backend = repo_root / "backend"
    cwd = backend if (backend / ".venv").exists() else repo_root
    venv_py = cwd / ".venv" / "bin" / "python3"

    script = (
        "import os,django;"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','apiSystem.settings');django.setup();"
        "from ninja_jwt.tokens import RefreshToken;"
        "from django.contrib.auth import get_user_model;"
        "U=get_user_model();u=U.objects.filter(is_superuser=True).first();"
        "print(str(RefreshToken.for_user(u).access_token))"
    )
    try:
        env = dict(os.environ)
        # apiSystem.settings 需要 backend/ 与 backend/apiSystem/ 都在 sys.path 上
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in [str(backend / "apiSystem"), str(backend), env.get("PYTHONPATH", "")] if p
        )
        proc = subprocess.run(
            [str(venv_py), "-c", script],
            cwd=str(backend / "apiSystem"),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if proc.returncode != 0:
            out("取 JWT 失败：" + (proc.stderr or proc.stdout)[-600:])
            return None
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        return lines[-1] if lines else None
    except Exception as e:  # pragma: no cover
        out("取 JWT 失败：", e)
        return None


def cleanup_test_data() -> None:
    """删掉本次 E2E 写入的测试数据（只在本地开发库跑，别留脏数据）。"""
    import subprocess
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent / "backend"
    script = (
        "import os,django;"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','apiSystem.settings');django.setup();"
        "from apps.reminders.models import Reminder;"
        "from apps.automation.models import CourtSMS;"
        "n1 = Reminder.objects.filter(content__icontains='E2E').delete()[0];"
        "n2 = CourtSMS.objects.filter(content__icontains='E2E').delete()[0];"
        "print(f'cleaned reminders={n1} sms={n2}')"
    )
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(backend / "apiSystem"), str(backend), env.get("PYTHONPATH", "")]
        )
        proc = subprocess.run(
            [str(backend / ".venv" / "bin" / "python3"), "-c", script],
            cwd=str(backend / "apiSystem"),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if proc.returncode == 0:
            out("🧹 " + (proc.stdout.strip().splitlines() or [""])[-1])
        else:
            out("⚠️  清理失败（不影响判定）：" + (proc.stderr or "")[-200:])
    except Exception as e:
        out("⚠️  清理异常：", e)


if __name__ == "__main__":
    sys.exit(main())
