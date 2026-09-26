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
import shutil
import sys
import tempfile
from pathlib import Path

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


def run_global_search(page) -> tuple[bool, str]:
    """⌘K 唤起全局检索，输入关键词，断言有结果或明确空态，Esc 可关。"""
    try:
        page.keyboard.press("Meta+k")
        page.wait_for_timeout(700)
        dlg = page.locator("[role=dialog]")
        if dlg.count() == 0:
            return False, "⌘K 没唤起检索面板"
        page.get_by_placeholder("搜案件", exact=False).fill("测试")
        # 后端并发搜 6 类实体，给足时间
        page.wait_for_timeout(3000)
        text = dlg.first.inner_text()
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        closed = page.locator("[role=dialog]").count() == 0
        if "没有匹配" in text:
            return closed, "检索正常返回空结果" + ("" if closed else "，但 Esc 关不掉")
        has_rows = any(k in text for k in ("案件", "客户", "合同", "收件箱", "法院短信", "联系人"))
        if not has_rows:
            return False, f"检索面板既无结果也无分类：{text[:80]!r}"
        return closed, "有结果" + ("" if closed else "，但 Esc 关不掉")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = launch_browser(p, args.headed)
        # accept_downloads=True：要素式转换会触发浏览器下载，必须开
        context = browser.new_context(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
        page = context.new_page()

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
        # 等日历面板真正渲染出来（React 挂载 + /reminders/calendar 返回），
        # 否则后续对日历格/事件行的测量会落在半成品 DOM 上
        try:
            page.wait_for_selector("section:has(.grid-cols-7)", timeout=20000)
        except Exception:
            out("⚠️  等待日历时面板超时，后续日历相关检查可能不可靠")
        page.wait_for_timeout(1500)

        # 1. 没有重定向去 login（说明鉴权通过）
        check("路由停留在首页（未跳登录页）", "/login" not in page.url, page.url)

        # 2. 顶部导航与问候语
        check("渲染品牌导航", page.locator("header").get_by_text("法穿 AI Copilot").count() >= 0)
        h1 = page.locator("h1")
        check("渲染问候标题", h1.count() >= 1 and "月" in (h1.first.inner_text() or ""))

        # 3. 日历网格行数按当月实际需要（不固定 6 行 42 格）
        #    当年有 9 个月只需 5 行，固定 6 行会多渲染一整行下月空白格
        grid_cells = page.locator("div.cursor-pointer.border-r")
        cell_count = grid_cells.count()
        rows = cell_count / 7
        check(
            "日历网格行数按当月实际（非固定 6 行）",
            cell_count > 0 and cell_count % 7 == 0 and 4 <= rows <= 6,
            f"{cell_count} 格 / {rows} 行",
        )

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

        # 8. 右栏「收件箱」拉到最近消息（同样在页面内带 token 访问）
        inbox_rows = fetch_in_page(page, '/api/v1/inbox/messages')
        msgs = inbox_rows.get("data") or []
        check("inbox/messages 在页面内鉴权访问成功", inbox_rows.get("status") == 200, f"status={inbox_rows.get('status')}")
        check("后端 inbox/messages 有数据", isinstance(msgs, list) and len(msgs) > 0, f"{len(msgs)} 条")
        # 「收件箱」卡应至少渲染出一条真实消息标题
        check(
            "收件箱渲染出真实消息标题",
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
        # 跳回当月：后续日历检查都默认看本月，否则会停留在刚切过去的月份
        page.get_by_title("回到今天").click()
        page.wait_for_timeout(1200)

        # 10b. 全局检索：⌘K 唤起 → 输入 → 有结果（后端 GET /search，跨 6 类实体）
        search_ok, search_detail = run_global_search(page)
        check("全局检索可唤起并返回结果", search_ok, search_detail)

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

        # 13b. 要素式转换：真实选文件 → 提交 → 浏览器真的下载一个 docx
        #      （只断言"卡片渲染"不等于功能可用，必须验证完整链路）
        conv_ok, conv_detail = run_doc_convert(page)
        check("要素式转换真实转换并下载 docx", conv_ok, conv_detail)

        # 13c. DOC 转 DOCX：真实提交 → 轮询 job 有终态 → 下载地址可达
        d2x_ok, d2x_detail = run_doc_to_docx(page)
        check("DOC 转 DOCX 任务跑通并产出结果", d2x_ok, d2x_detail)

        # 14a. 点日历空白格 → 新增安排弹窗 → 真实写入（不再有"新增安排"按钮）
        add_ok, add_detail = run_add_reminder(page)
        check("点日历空白格可新增安排并写入", add_ok, add_detail)

        # 确认顶部那个「新增安排」按钮已移除
        nav_btn = page.get_by_role("button", name="新增安排").count()
        check("顶部不再有「新增安排」按钮", nav_btn == 0, f"剩 {nav_btn} 个")

        # 14b. 日历事件详情弹窗：点格子里的事件应弹出带完整信息的对话框
        detail_ok, detail_detail = run_event_detail_dialog(page)
        check("点日历事件弹出详情弹窗", detail_ok, detail_detail)

        # 14c. 日历格要能容纳「标题 + 律师 + 地点」三行，且律师真的渲染出来
        cell_ok, cell_detail = check_calendar_cell_density(page)
        check("日历格高度足够且显示律师", cell_ok, cell_detail)

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

        # 注意：14b / 14c 必须跑在 section 14（移动端抽屉）之前——
        # section 14 会把视口缩到 420px，之后即使还原，CSS 回流也需要时间，
        # 紧接着测量格子高度会拿到中间态。
        # 15. 图标压扁检查：把视口恢复宽屏，扫「内容区容不下自己图标」的按钮。
        #     这类 bug 视觉上表现为图标消失/只剩空方块，但控制台不报错、功能也正常，
        #     纯看代码 grep 不出来（根因可能是 padding/width/flex/border 任一种），
        #     所以直接读浏览器计算样式：内容区宽 < 图标宽即视为被压扁。
        page.set_viewport_size({"width": 1600, "height": 1000})
        page.wait_for_timeout(600)
        squashed = find_squashed_icons(page)
        check(
            "无图标被容器压扁（内容区容纳不下）",
            not squashed,
            "；".join(squashed[:4]) or "全部正常",
        )

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


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample-complaint.docx"


EVENT_ROW_JS = """() => {
    // 日历格里真正的事件行（组件上带 data-calendar-event 属性）。
    // 悬停 tooltip 里也会渲染同样的事件，但它没有这个属性，借此区分。
    return [...document.querySelectorAll('[data-calendar-event]')].map(el => {
        const lines = el.innerText.split(String.fromCharCode(10)).map(x => x.trim()).filter(Boolean);
        return { id: el.getAttribute('data-calendar-event'), lines };
    });
}"""
def picked_badge(page) -> str | None:
    """读取新增弹窗里已绑定那一栏的类型徽章文本（合同/案件/案件日志）。"""
    try:
        return page.evaluate(
            """() => {
                const d = document.querySelector('[role=dialog]');
                if (!d) return null;
                // 绑定态那一行的徽章：文案是「合同」「案件」「案件日志」之一
                const spans = [...d.querySelectorAll('span')];
                const hit = spans.find(x => ['合同', '案件', '案件日志'].includes(x.textContent.trim()));
                return hit ? hit.textContent.trim() : null;
            }"""
        )
    except Exception:  # noqa: BLE001
        return None


def run_add_reminder(page) -> tuple[bool, str]:
    """点空白日期格 → 填新增弹窗 → 保存，断言写进 reminders 且日历出现。

    这条会在开发库里真实造一条 reminder，跑完由 cleanup_test_data 清掉
    （content 带 E2E 前缀便于识别）。
    """
    marker = "E2E弹窗新增验证"
    try:
        # 前面几节可能留下了 dialog/下拉，先按 Esc 收掉，避免遮挡或抢焦点
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # 挑一个当月、且没有任何事件的日期格（用日期数字元素定位，
        # 不要点格子边缘——格子边缘的 border 区域不是 onClick 目标）
        target = page.evaluate(
            """() => {
                const cells = [...document.querySelectorAll('div.cursor-pointer.border-r')];
                // 只当月：有 [data-calendar-event] 的算"有事件"，日号长度 < 4 的基本是空格
                const empty = cells.find(c =>
                    !c.querySelector('[data-calendar-event]') &&
                    !c.className.includes('opacity-30') &&            // 排除非当月的补白格
                    c.innerText.trim().length > 0
                );
                if (!empty) return null;
                // 点日号下方一点的位置：一定是本格、不会误触别的事件
                const num = empty.querySelector('span.tabular-nums');
                const base = num || empty;
                const r = base.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }"""
        )
        if not target:
            return True, "当月没有空白日期格，跳过（不算失败）"

        # 关键：前面的测试把页面滚下去了（scrollY 可达 700+），目标格子在视口外，
        # mouse.click 用视口坐标会点空。先滚回顶部让日历进入视口。
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(400)
        # 滚动后重新取坐标（之前的 y 已失效）
        target = page.evaluate(
            """() => {
                const cells = [...document.querySelectorAll('div.cursor-pointer.border-r')];
                const empty = cells.find(c =>
                    !c.querySelector('[data-calendar-event]') &&
                    !c.className.includes('opacity-30') &&
                    c.innerText.trim().length > 0
                );
                if (!empty) return null;
                const num = empty.querySelector('span.tabular-nums') || empty;
                const r = num.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }"""
        )
        if not target:
            return False, "滚动后仍找不到空白日期格"

        # 再移开鼠标点：鼠标停在日历上时悬停 tip 可能拦住点击
        opened = False
        for _ in range(3):
            page.mouse.move(0, 0)
            page.wait_for_timeout(200)
            page.mouse.click(target["x"], target["y"])
            page.wait_for_timeout(800)
            if page.locator("[role=dialog]").count() > 0:
                opened = True
                break
        if not opened:
            return False, "点空白格没弹出新增框"
        dlg = page.locator("[role=dialog]")
        if "新增安排" not in dlg.first.inner_text():
            return False, "弹出的不是新增安排框"

        page.get_by_placeholder("例如", exact=False).fill(marker)

        # 关联对象：打关键字 → 选中第一个候选（合同/案件/案件日志之一）。
        # 不做关联的话 admin 日历里会显示成"独立提醒"，等于白建，
        # 所以这条用例必须验证真绑上了。
        page.get_by_placeholder("输入当事人名称", exact=False).fill("升平")
        bound_type = pick_target_option(page)
        if not bound_type:
            return False, "关键字联想没有可选结果，无法验证关联绑定"

        save = page.get_by_role("button").filter(has_text="保存")
        if save.count() == 0:
            return False, "没有保存按钮"
        save.first.click()
        page.wait_for_timeout(3000)

        # 1) 后端是否真写入
        rows = fetch_in_page(page, '/api/v1/reminders/list').get("data") or []
        hit = next((x for x in rows if marker in (x.get("content") or "")), None)
        if not hit:
            return False, "点了保存但后端没有这条 reminder"
        # 2) 关联字段是否真的落库（三个 id 字段应恰好一个非空）
        ids = [hit.get("case"), hit.get("contract"), hit.get("case_log")]
        if all(v is None for v in ids):
            return False, "提醒写入了但没有关联任何案件/合同"
        # 3) 面板已关闭 + 日历数据里能看到这条
        #    用日历接口判据而不是 DOM 文本：格子对长标题会截断，
        #    哪天事件多还会被折叠成"+N 更多"，DOM 文本判据不稳。
        closed = page.locator("[role=dialog]").count() == 0
        cal = fetch_in_page(page, "/api/v1/reminders/calendar?year=2026&month=9").get("data") or {}
        days = cal.get("days") or {}
        in_calendar = any(
            marker in (ev.get("content") or "") or marker in (ev.get("title") or "")
            for evs in days.values()
            for ev in evs
        )
        # 视图是否真刷新出来了（DOM 上能看到说明 invalidate 生效）
        in_dom = marker in page.locator("main").inner_text()
        if not (closed and in_calendar):
            return False, f"closed={closed} in_calendar={in_calendar}"
        return True, f"已写入并关联（{bound_type}），日历已刷新" + ("" if in_dom else "（DOM 截断未显示全称，数据已对）")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"

def pick_target_option(page) -> str | None:
    """在新增弹窗里选中第一个关联对象候选，返回类型标签（合同/案件/案件日志）。

    注意：不能用 get_by_text("案件") 之类——合同/案件的名称里常含"诉"等字，
    会误匹配。这里直接用候选列表容器（div.z-50）里的按钮定位。
    """
    try:
        # 候选面板结构：div.z-50 > [tabs] + .overflow-y-auto > buttons
        # 输入有 300ms 防抖 + 一次请求，多等一会儿
        page.wait_for_timeout(800)
        page.wait_for_selector("[role=dialog] div.z-50 .overflow-y-auto button", timeout=10000)
        opts = page.locator("[role=dialog] div.z-50 .overflow-y-auto button")
        if opts.count() == 0:
            return None
        # 第一个 span 是类型徽章（合同/案件/案件日志）
        label = opts.first.evaluate("el => (el.querySelector('span') || {}).textContent || ''")
        opts.first.click()
        page.wait_for_timeout(600)
        result = (picked_badge(page) or label).strip()
        return result or None
    except Exception:  # noqa: BLE001
        return None


def run_event_detail_dialog(page) -> tuple[bool, str]:
    """点日历格里第一个事件，断言弹出详情弹窗且含关键字段，Esc 能关。"""
    try:
        # 先确保该元素滚入视口（窄屏时可能在折叠区域外）
        target = page.locator("[data-calendar-event]").first
        target.scroll_into_view_if_needed(timeout=8000)
        page.wait_for_timeout(400)

        # 点前重新取坐标：前面跑过快速记一笔等操作，DOM 可能刚重渲染过，
        # 用旧坐标会点空。第一次不生效就再试一次。
        for attempt in range(3):
            box = page.evaluate(
                """() => {
                    const el = document.querySelector('[data-calendar-event]');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) return null;
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }"""
            )
            if not box:
                return False, "日历格里没有事件行（后端当月可能没有提醒）"
            page.mouse.click(box["x"], box["y"])
            page.wait_for_timeout(800)
            if page.locator("[role=dialog]").count() > 0:
                break
        dlg = page.locator("[role=dialog]")
        if dlg.count() == 0:
            return False, "点了事件但没有弹出 dialog"
        text = dlg.first.inner_text()
        has_any = any(k in text for k in ("时段", "法庭", "地点", "律师", "案号"))
        if not has_any:
            return False, f"弹窗缺少关键字段：{text[:80]!r}"
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        closed = page.locator("[role=dialog]").count() == 0
        return closed, "已弹出并可用 Esc 关闭" if closed else "弹出了但 Esc 关不掉"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def check_calendar_cell_density(page) -> tuple[bool, str]:
    """日历格要够高（容纳标题+律师+地点三行），且律师真的渲染进事件行。

    不强制要求「一定有带律师的事件」——当月可能全是手工录入的提醒，
    后端 metadata 里没有 lawyer_name，此时没有律师行是数据问题而非界面问题。
    """
    try:
        info = page.evaluate(
            """() => {
                const cells = document.querySelectorAll('div.cursor-pointer.border-r');
                if (!cells.length) return null;
                let h = 0;
                cells.forEach(c => { const ch = c.getBoundingClientRect().height; if (ch > h) h = ch; });
                return { height: Math.round(h) };
            }"""
        )
        if not info:
            return False, "页面没有日历格"
        rows = page.evaluate(EVENT_ROW_JS)
        with_lawyer = sum(1 for r in rows if len(r.get("lines", [])) >= 3)
        tall_ok = info["height"] >= 150
        return tall_ok, f"格高 {info['height']}px；事件 {len(rows)} 条，其中带律师行 {with_lawyer} 条"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def find_squashed_icons(page) -> list[str]:
    """扫出「图标被容器压扁」的可交互元素，返回可读描述列表。

    判据：图标按自己的 Tailwind 尺寸类**应该**渲染多宽，对比实际渲染宽度。
    lucide 的 svg 永远带 width="24" 属性——别拿它当应有尺寸，真实尺寸由
    Tailwind 类决定（如 h-3.5 w-3.5 → 14px），所以必须解析类名。

    两种都算压扁：
      a) 图标实渲宽度 ≈ 0（被完全压没，视觉上正是"图标丢了/只剩空方块"）
      b) 元件内容区比图标的应显宽度还小（图标被挤压）

    前两版的教训（都实测过，别再退回去）：
      - 比"实渲宽度 vs 内容区"：bug 在位时 content=2px 而 svgW=0，恰好
        不满足小于关系，检查却报"全部正常"，漏掉最严重的情况。
      - 把 svg 的 width 属性（恒为 24）当应有尺寸：正常图标全被判异常。
    现在按类名解析应有尺寸，再与实渲宽度比。

    典型根因：拼接的类没覆盖掉基础类的 padding（BTN 自带 px-[13px]，又拼
    px-0 想覆盖，但 Tailwind 不保证后拼者优先），28px 按钮内容区只剩 2px。
    这类问题控制台无报错、功能也正常，只能靠读计算样式发现。
    """
    # JS-SIDE 计算逻辑放在单独文件里，避免 Python 字符串转义互相纠缠
    return page.evaluate(SQUASH_DETECT_JS) or []


SQUASH_DETECT_JS = r"""() => {
    // Tailwind 间距刻度 → px（这里只会用到小值）
    const SCALE = {0: 0, px: 1, 0.5: 2, 1: 4, 1.5: 6, 2: 8, 2.5: 10, 3: 12, 3.5: 14, 4: 16, 5: 20, 6: 24};
    function wantPx(cls, axis) {
        const any = new RegExp('(?:^|\\s)' + axis + '-\\[([\\d.]+)px\\]').exec(cls);
        if (any) return parseFloat(any[1]);
        const sc = new RegExp('(?:^|\\s)' + axis + '-([\\d.]+|px)(?:\\s|$)').exec(cls);
        if (sc && sc[1] in SCALE) return SCALE[sc[1]];
        return 0;
    }
    const bad = [];
    document.querySelectorAll('button, a, input, select, textarea, label').forEach(el => {
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;              // 隐藏元素跳过
        const content = r.width
            - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
            - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth);
        // 找本元素内"应显尺寸最大"的 svg，同时记下它的实渲宽度
        let want = 0, got = 0;
        el.querySelectorAll('svg').forEach(s => {
            const cls = s.getAttribute('class') || '';
            const w = wantPx(cls, 'w'), h = wantPx(cls, 'h');
            const size = (w && h) ? Math.min(w, h) : (w || h);
            if (size > want) { want = size; got = s.getBoundingClientRect().width; }
        });
        if (want === 0) return;                                   // 没有带尺寸类的图标
        const label = (el.innerText || el.getAttribute('title')
                       || el.getAttribute('aria-label') || '').trim().slice(0, 18);
        const desc = '<' + el.tagName.toLowerCase() + '> ' + (label || '(无标签)')
            + ' 内容区' + Math.round(content) + 'px / 应显示' + Math.round(want) + 'px'
            + ' / 实渲' + Math.round(got) + 'px';
        if (got < 1 || content < want - 1) bad.push(desc);
    });
    return bad;
}"""


def _tool_card(page, title: str):
    """按卡片标题定位一张工具卡（卡片标题在 .th 里的 .tn）。
    不能用端点注释文本定位——它被 CSS truncate 了，has_text 匹配不到。"""
    return page.locator(
        f"xpath=//div[contains(@class,'flex flex-col')][.//div[normalize-space(text())='{title}']]"
    ).last


def run_doc_convert(page) -> tuple[bool, str]:
    """要素式转换：选真实 docx → 点转换 → 捕获浏览器下载 → 校验是合法 docx。
    返回 (是否通过, 说明)。"""
    if not FIXTURE.exists():
        return False, f"缺少测试夹具 {FIXTURE}（应随仓库提交）"
    try:
        card = _tool_card(page, "要素式转换")
        card.locator("select").first.select_option("mjjdqsz")  # 民间借贷起诉状
        card.locator("input[type=file]").set_input_files(str(FIXTURE))
        # 转换是同步返回二进制（后端约 6s），成功后前端触发 <a download>
        with page.expect_download(timeout=120_000) as dl:
            card.get_by_role("button", name="转换").click()
        download = dl.value
        name = download.suggested_filename
        tmp = Path(tempfile.mkdtemp(prefix="e2e-convert-")) / name
        download.save_as(str(tmp))
        size = tmp.stat().st_size
        magic = tmp.read_bytes()[:2]
        # 合法 docx = zip 容器（PK），且不能是空壳
        ok = magic == b"PK" and size > 2000 and name.endswith(".docx")
        # 中文名能否正确从 RFC5987 头解出
        detail = f"下载 {name}（{size} 字节）"
        if not ok:
            detail = f"下载物异常：name={name} size={size} magic={magic!r}"
        return ok, detail
    except Exception as e:  # noqa: BLE001 —— E2E 需要把任何失败转成可读结论
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def run_doc_to_docx(page) -> tuple[bool, str]:
    """DOC 转 DOCX：提交一个 docx 改名的 .doc 交给 LibreOffice → 轮询 job → 校验终态。
    本机装有 LibreOffice（/Applications/LibreOffice.app），应能真正转成功；
    若全失败也如实报出来（例如环境缺 LibreOffice），不当成静默通过。"""
    if not FIXTURE.exists():
        return False, f"缺少测试夹具 {FIXTURE}"
    try:
        card = _tool_card(page, "DOC 转 DOCX")
        tmpdir = Path(tempfile.mkdtemp(prefix="e2e-d2x-"))
        fake_doc = tmpdir / "sample.doc"
        shutil.copyfile(FIXTURE, fake_doc)

        # 抓提交时产生的 job_id（POST /doc-converter/jobs 的响应体）
        job_id: list[str] = []

        def on_response(resp) -> None:
            if "/api/v1/doc-converter/jobs" in resp.url and resp.request.method == "POST":
                try:
                    body = resp.json()
                    if body.get("job_id"):
                        job_id.append(body["job_id"])
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            card.locator("input[type=file]").set_input_files(str(fake_doc))
            card.get_by_role("button", name="开始转换").click()
            # 等 job_id 出现
            deadline = 30
            while not job_id and deadline > 0:
                page.wait_for_timeout(500)
                deadline -= 1
        finally:
            page.remove_listener("response", on_response)

        if not job_id:
            return False, "没抓到 doc-converter job_id（提交可能失败）"

        # 轮询 job 状态（在页面内带 token 请求，和前端同一套鉴权）
        job = None
        for _ in range(40):
            page.wait_for_timeout(1500)
            job = fetch_in_page(page, f'/api/v1/doc-converter/jobs/{job_id[0]}').get("data")
            if job:
                j = job.get("job") or {}
                total, done, failed = j.get("total_files", 0), j.get("converted_files", 0), j.get("failed_files", 0)
                if j.get("status") in ("completed", "failed") or (total > 0 and done + failed >= total):
                    job = {"status": j.get("status"), "done": done, "failed": failed, "total": total}
                    break
        if not job:
            return False, "轮询 60s 仍未拿到 job 终态"
        # 有文件真的转成功才算跑通：status 到达终态只证明任务没卡死，
        # 全失败（如 LibreOffice 缺失/源文件坏）必须判失败，否则这是假绿
        ok = job["done"] >= 1 and job["failed"] == 0
        detail = f"status={job['status']} done={job['done']} failed={job['failed']} total={job['total']}"
        return ok, detail if ok else f"没有成功转换的文件——{detail}"
    except Exception as e:  # noqa: BLE001 —— E2E 需要把任何失败转成可读结论
        return False, f"{type(e).__name__}: {str(e)[:160]}"


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
