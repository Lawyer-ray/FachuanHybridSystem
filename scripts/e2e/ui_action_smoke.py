"""真机自证：无头浏览器 + MCP 真调，跑一遍 confirm / guarded 的四条链路。

## 这条命令证明什么

单元测试能证明「协议翻译对」，证明不了下面四件事真的发生在同一台机器上：

1. **confirm 同意**：MCP 真调 → 审批卡弹出 → 点「同意」→ 页面真的写库 →
   服务端回库核出 ``verified=true``，审计 ``outcome=ok``；
2. **confirm 拒绝**：点「拒绝」→ 材料包零变化、审计 ``outcome=denied``；
3. **guarded 删除（两层都过）**：服务端审批同意 + 前端本地「确认执行」→
   包真的不在、审计 ``verified=true``；
4. **guarded 删除（本地取消）**：审批同意 + 本地「取消」→ 包还在、审计
   ``outcome=aborted``。

四条都是「真浏览器 + 真 MCP + 真库」。任何一条不成立都非零退出，并打印差异。

## 为什么需要先发一句聊天

审批请求走的是会话的 SSE 总线（``approval_request`` 帧），而总线只在**一轮对话
的流还开着**时才有订阅者。所以每个动作前都会先发一句需要长回答的话，用它的
流窗口承载审批卡；这不是测模型回答，只是把订阅通道打开。这一句会真的调模型
（有 token 成本），脚本跑完会关掉浏览器，服务端按断流收尾。

## 数据边界

- 只碰本脚本创建的材料包（subject 前缀 ``E2E-``）与专用会话；跑完在 ``finally``
  里删包、删会话；
- **审计行一行都不删**：它们是证据，脚本会把本次会话留下的行打印出来；
- 不碰任何既有材料包，也不改既有业务数据（judge / delete 只作用在自造包上）；
- 截图写到 ``/tmp/fachuan-e2e-shots/<时间戳>/``，不进仓库。

## 前置与退出码

三个服务（5090 / 8002 / 8011）任一不通：默认 ``skip`` 并退出 0（CI 不因环境
红）；``--require`` 时视为前置失败、退出 2。断言失败退出 1；建会话/造包/铸票
这类准备失败退出 2。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import (
    FRONTEND_BASE,
    Credential,
    E2eError,
    call_mcp_tool,
    create_session,
    delete_pack,
    delete_session,
    get_pack,
    list_ui_actions,
    mcp_result_payload,
    mcp_result_text,
    out,
    pack_fingerprint,
    pack_status,
    probe_services,
    resolve_credential,
    upload_pack,
)

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # 主函数会给出安装提示并 skip；这里只让模块能 import
    PlaywrightError = RuntimeError  # type: ignore[misc,assignment]
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]

#: 审批卡最多等这么久（需求口径：120s）。
APPROVAL_WAIT_SECONDS = 120.0
#: 一次 MCP 工具调用最多等这么久（审批 + 页面执行 + 回执 + 核实）。
ACTION_WAIT_SECONDS = 240.0
#: 审计行 / 材料包状态的收敛窗口（回执与核实都是异步落库）。
SETTLE_WAIT_SECONDS = 30.0
#: 等 SSE 首帧的窗口：首帧到达 = 后端已把本会话登记进事件总线。
STREAM_WAIT_SECONDS = 60.0

#: 开流用的问题：要长到足够覆盖审批卡出现的窗口，且不诱导模型调高危工具。
STREAM_PROMPT = (
    "请写一份完整的民事起诉状范文：标题、当事人信息、诉讼请求、事实与理由、证据清单、落款都要写全；"
    "正文不少于 1500 字，分小节展开，不要省略或用省略号代替。"
)


class PhaseFailure(RuntimeError):
    """一段断言失败；``infra=True`` 表示链路本身没走通（后续阶段不再空等）。"""

    def __init__(self, message: str, *, infra: bool = False, diff: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.infra = infra
        self.diff = diff or {}


@dataclass(frozen=True)
class PhaseSpec:
    """一段实测：动作、参数、点哪个按钮、期望的审计与材料包结局。"""

    key: str
    title: str
    action: str
    args: dict[str, Any]
    decide: str
    expect_outcome: str
    expect_verified: bool | None = None
    expect_status: str | None = None
    expect_unchanged: bool = False
    expect_absent: bool = False


@dataclass
class PhaseResult:
    """一段实测的结论（主函数用它决定退出码与汇总表）。"""

    spec: PhaseSpec
    passed: bool
    detail: str


class McpCallThread:
    """在 daemon 线程里跑一次 MCP 调用，主线程同时操作浏览器。

    daemon 而不是 ThreadPoolExecutor：审批卡没出现时那个调用可能还阻塞在服务端
    的审批等待里，非 daemon 线程会让解释器退出时继续 join，脚本就挂住了。
    """

    def __init__(self, credential: Credential, session_id: str, tool: str, arguments: dict[str, Any]) -> None:
        self._credential = credential
        self._session_id = session_id
        self._tool = tool
        self._arguments = arguments
        self._done = threading.Event()
        self._result: dict[str, Any] | None = None
        self._error: Exception | None = None
        self._thread = threading.Thread(target=self._run, name=f"mcp-{tool}", daemon=True)

    def _run(self) -> None:
        try:
            self._result = call_mcp_tool(
                self._credential.token,
                self._session_id,
                self._tool,
                self._arguments,
                timeout=ACTION_WAIT_SECONDS,
            )
        except (E2eError, ValueError, OSError) as exc:
            self._error = exc
        finally:
            self._done.set()

    def start(self) -> None:
        self._thread.start()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: float) -> dict[str, Any]:
        if not self._done.wait(timeout):
            raise PhaseFailure(
                f"MCP 调用 {self._tool} 在 {timeout:.0f}s 内没有返回（审批可能一直没人批）",
                infra=True,
            )
        if self._error is not None:
            if isinstance(self._error, E2eError):
                raise PhaseFailure(f"MCP 调用失败：{self._error}", infra=True) from self._error
            raise self._error
        if self._result is None:
            raise PhaseFailure("MCP 调用结束但没有返回结果", infra=True)
        return self._result


def _browser_bootstrap(token: str, session_id: str) -> str:
    """页面加载前注入：登录态 + 会话 id + SSE 首帧观测器。

    SSE 观测器挂在 ``window.fetch`` 上：审批请求要等后端把本会话登记进事件总线
    （``bus.register``）才可能送达，而那时第一帧 SSE 一定已经发出。只等
    ``POST /messages`` 的响应头不够——Django 先发头、后跑异步生成器，头到不代表
    订阅已登记。
    """
    return (
        "(() => {"
        f"const token = {json.dumps(token)};"
        f"const sessionId = {json.dumps(session_id)};"
        "try {"
        "localStorage.setItem('access_token', token);"
        "localStorage.setItem('copilot:session', sessionId);"
        "} catch (error) {}"
        "const sse = { seen: false, ended: false, frames: 0 };"
        "Object.defineProperty(window, '__fachuanE2eSse', { value: sse, configurable: true });"
        "const nativeFetch = window.fetch.bind(window);"
        "window.fetch = function (input, init) {"
        "  const pending = nativeFetch(input, init);"
        "  const url = typeof input === 'string' ? input : (input && input.url) || '';"
        "  const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();"
        "  if (method !== 'POST' || !url.includes('/agent/sessions/') || !url.includes('/messages')) return pending;"
        "  return pending.then((response) => {"
        "    try {"
        "      const clone = response.clone();"
        "      if (!clone.body) return response;"
        "      const reader = clone.body.getReader();"
        "      const decoder = new TextDecoder();"
        "      (async () => {"
        "        try {"
        "          while (true) {"
        "            const step = await reader.read();"
        "            if (step.done) break;"
        "            const text = decoder.decode(step.value, { stream: true });"
        "            if (text.includes('data:')) { sse.seen = true; sse.frames += 1; }"
        "          }"
        "        } catch (error) {}"
        "        sse.ended = true;"
        "      })();"
        "    } catch (error) {}"
        "    return response;"
        "  });"
        "};"
        "})();"
    )


def _screenshot(page: Any, shot_dir: Path, spec: PhaseSpec, step: str) -> None:
    """截图失败不影响断言（它是诊断材料，不是证据本体）。"""
    try:
        page.screenshot(path=str(shot_dir / f"{spec.key}-{step}.png"))
    except PlaywrightError:
        pass


def _reset_sse_state(page: Any) -> None:
    page.evaluate(
        "() => { const state = window.__fachuanE2eSse;"
        " if (state) { state.seen = false; state.ended = false; state.frames = 0; } }"
    )


def _wait_first_sse_frame(page: Any) -> bool:
    """等到第一帧 SSE；返回是否等到。

    没有首帧就**不能**往下发动作：审批卡要等后端 ``bus.register`` 之后才可能送达，
    而「响应头到了」不等于「订阅已登记」（Django 先发头、后跑异步生成器）。
    """
    try:
        page.wait_for_function(
            "() => !!(window.__fachuanE2eSse && window.__fachuanE2eSse.seen)",
            timeout=int(STREAM_WAIT_SECONDS * 1000),
        )
        return True
    except PlaywrightTimeoutError:
        return False


def _ensure_stream(page: Any, box: Any, spec: PhaseSpec, shot_dir: Path) -> None:
    """发一句需要长回答的话，并确认流真的开起来了（最多重开一次）。"""
    for attempt in (1, 2):
        _reset_sse_state(page)
        box.click()
        box.fill(STREAM_PROMPT)
        box.press("Enter")
        if not _wait_first_sse_frame(page):
            raise PhaseFailure(
                f"{STREAM_WAIT_SECONDS:.0f}s 内没观测到 SSE 首帧（聊天流没起来，审批卡无处可弹）",
                infra=True,
                diff={"url": page.url, "body": page.inner_text("body")[:800]},
            )
        ended = bool(page.evaluate("() => !!(window.__fachuanE2eSse && window.__fachuanE2eSse.ended)"))
        if not ended:
            return
        out(f"[warn] 第 {attempt} 轮流在本轮动作前就结束了，重开一轮")
        page.wait_for_timeout(500)
    raise PhaseFailure("聊天流在动作下发前就结束（无法承载审批卡）", infra=True)


def _open_page(browser: Any, credential: Credential, session_id: str, spec: PhaseSpec, shot_dir: Path) -> tuple[Any, Any, Any, list[str]]:
    """新上下文打开材料预处理页 + AI 面板，返回 ``(context, page, textarea, page_errors)``。"""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        context.add_init_script(_browser_bootstrap(credential.token, session_id))
        page = context.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)[:300]))
        page.goto(f"{FRONTEND_BASE}/material-prep", wait_until="networkidle", timeout=60_000)
        if "/login" in page.url:
            raise PhaseFailure(
                "页面被重定向到登录页：注入的 access token 无效或已过期（换 FACHUAN_E2E_TOKEN / 重新铸票）",
                infra=True,
            )
        _screenshot(page, shot_dir, spec, "01-page")
        page.evaluate("window.dispatchEvent(new CustomEvent('copilot:launch', { detail: null }))")
        box = page.locator("textarea").first
        box.wait_for(state="visible", timeout=20_000)
        page.wait_for_timeout(800)
        _screenshot(page, shot_dir, spec, "02-copilot")
        return context, page, box, page_errors
    except (PhaseFailure, PlaywrightError):
        try:
            context.close()
        except PlaywrightError:
            pass
        raise


def _approval_card(page: Any, action: str) -> Any | None:
    """按卡片标题精确定位审批卡根节点（避免页面上别的「同意」按钮）。"""
    title = page.locator(f"span:text-is('需要确认：{action}')")
    if title.count() == 0:
        return None
    return title.first.locator("xpath=../..")


def _wait_approval_card(page: Any, spec: PhaseSpec, call: McpCallThread) -> Any:
    """等本动作的审批卡出现；工具调用先返回 = 链路没走通，立刻带证据失败。"""
    deadline = time.monotonic() + APPROVAL_WAIT_SECONDS
    while time.monotonic() < deadline:
        card = _approval_card(page, spec.action)
        if card is not None:
            return card
        if call.done:
            result = call.wait(1.0)
            text = mcp_result_text(result)[:1000]
            raise PhaseFailure(
                "工具调用在审批卡出现前就返回了（多半是页面没有订阅者 / delivered=false）",
                infra=True,
                diff={"tool_result": result, "tool_text": text},
            )
        page.wait_for_timeout(500)
    raise PhaseFailure(f"等了 {APPROVAL_WAIT_SECONDS:.0f}s 没出现 {spec.action} 的审批卡", infra=True)


def _click_local_confirm(page: Any, *, confirm: bool) -> None:
    """guarded 的本层二次确认：点「确认执行」或「取消」。"""
    dialog = page.get_by_role("dialog").filter(has_text="需要你确认")
    dialog.wait_for(state="visible", timeout=60_000)
    label = "确认执行" if confirm else "取消"
    dialog.get_by_role("button", name=label, exact=True).first.click()
    page.wait_for_timeout(300)


def _decide(page: Any, card: Any, spec: PhaseSpec) -> None:
    """按本段的口径操作审批卡（同意 / 拒绝 / 同意后再做本地确认）。"""
    if spec.decide == "deny":
        card.get_by_role("button", name="拒绝", exact=True).first.click()
        page.wait_for_timeout(300)
        card.get_by_role("button", name="确认拒绝", exact=True).first.click()
        return
    card.get_by_role("button", name="同意", exact=True).first.click()
    page.wait_for_timeout(250)
    # critical 档的首击只解锁，按钮会变成「再次确认执行」；本脚本两条动作是 high，
    # 这里顺手兼容一下，避免部署把风险下限抬高时静默卡住。
    again = card.get_by_role("button", name="再次确认执行", exact=True)
    if again.count() > 0:
        again.first.click()
    if spec.decide == "guarded-confirm":
        _click_local_confirm(page, confirm=True)
    elif spec.decide == "guarded-cancel":
        _click_local_confirm(page, confirm=False)


def _wait_audit_row(credential: Credential, session_id: str, spec: PhaseSpec) -> dict[str, Any]:
    """等审计行收敛到本段要的 ``outcome``（以及 ``verified``，若本段声明了）。"""
    deadline = time.monotonic() + SETTLE_WAIT_SECONDS
    candidates: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        rows = list_ui_actions(credential.token)
        candidates = [row for row in rows if str(row.get("session_id") or "") == session_id]
        for row in candidates:
            if row.get("action") != spec.action or row.get("outcome") != spec.expect_outcome:
                continue
            if spec.expect_verified is None or row.get("verified") is True:
                return row
        time.sleep(0.5)
    hint = ""
    if spec.expect_verified and any(
        row.get("action") == spec.action
        and row.get("outcome") == spec.expect_outcome
        and row.get("verified") is None
        for row in candidates
    ):
        hint = (
            "；已收到回执但 verified=null：多半是 MCP 的 2s 回执窗口没等到页面（observed=false），"
            "核实器因此没跑。负载高时重跑，或给共享 MCP 设 FACHUAN_UI_ACTION_ACK_WAIT=8"
        )
    raise PhaseFailure(
        f"审计台账没收敛到 action={spec.action} outcome={spec.expect_outcome}"
        + (" verified=true" if spec.expect_verified else "")
        + hint,
        diff={"audit_rows": candidates},
    )


def _wait_pack_outcome(credential: Credential, pack_id: int, spec: PhaseSpec, before: dict[str, Any]) -> dict[str, Any] | None:
    """等材料包落到本段期望的样子；失败时把 before/after 一起交给调用方打印。"""
    deadline = time.monotonic() + SETTLE_WAIT_SECONDS
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = get_pack(credential.token, pack_id)
        if spec.expect_absent:
            if last is None:
                return None
        elif last is not None:
            if spec.expect_status is not None and pack_status(last) == spec.expect_status:
                return last
            if spec.expect_unchanged and pack_fingerprint(last) == before:
                return last
        time.sleep(0.4)
    diff: dict[str, Any] = {
        "before": before,
        "after_exists": last is not None,
        "after": pack_fingerprint(last) if last is not None else None,
        "expect_status": spec.expect_status,
        "expect_unchanged": spec.expect_unchanged,
        "expect_absent": spec.expect_absent,
    }
    raise PhaseFailure(f"材料包 {pack_id} 没有落到期望结局", diff=diff)


def _run_phase(
    browser: Any,
    credential: Credential,
    session_id: str,
    spec: PhaseSpec,
    pack_id: int,
    shot_dir: Path,
) -> dict[str, Any]:
    """跑完一段：开流 → MCP 下发 → 点卡 → 等审计/包状态。"""
    before_pack = get_pack(credential.token, pack_id)
    if before_pack is None:
        raise PhaseFailure(f"起始材料包 {pack_id} 不存在（造数阶段出了问题）", infra=True)
    before = pack_fingerprint(before_pack)
    before_status = pack_status(before_pack)
    if spec.expect_status is not None and before_status == spec.expect_status:
        raise PhaseFailure(f"起始状态已经是 {spec.expect_status}，无法证明是这次动作改的", infra=True)

    context, page, box, page_errors = _open_page(browser, credential, session_id, spec, shot_dir)
    call: McpCallThread | None = None
    try:
        _ensure_stream(page, box, spec, shot_dir)
        _screenshot(page, shot_dir, spec, "03-streaming")
        call = McpCallThread(credential, session_id, spec.action, spec.args)
        call.start()
        out(f"[{spec.key}] 已下发 {spec.action}({json.dumps(spec.args, ensure_ascii=False)})")

        card = _wait_approval_card(page, spec, call)
        _screenshot(page, shot_dir, spec, "04-approval-card")
        out(f"[{spec.key}] 审批卡已出现")
        _decide(page, card, spec)
        _screenshot(page, shot_dir, spec, "05-decided")

        result = call.wait(ACTION_WAIT_SECONDS)
        payload = mcp_result_payload(result)
        if payload.get("pending"):
            out(
                f"[{spec.key}][warn] 工具在 2s 回执窗口内没等到页面（observed=false）："
                "核实器不会跑，本段的 verified 断言很可能红"
            )
        out(f"[{spec.key}] 工具返回: {json.dumps(payload or mcp_result_text(result)[:500], ensure_ascii=False)[:800]}")
        _screenshot(page, shot_dir, spec, "06-after-action")

        row = _wait_audit_row(credential, session_id, spec)
        after_pack = _wait_pack_outcome(credential, pack_id, spec, before)
        if page_errors:
            out(f"[{spec.key}][warn] 页面 JS 错误: {page_errors[-3:]}")
        after_status = pack_status(after_pack) if after_pack is not None else "<已删除>"
        return {
            "audit": row,
            "before_status": before_status,
            "after_status": after_status,
        }
    finally:
        try:
            context.close()
        except PlaywrightError:
            pass


def _cleanup(credential: Credential | None, session_id: str, created_packs: list[int]) -> None:
    """先打印审计（证据），再删自造包与会话；**绝不删审计行**。"""
    if credential is not None and session_id:
        try:
            rows = [row for row in list_ui_actions(credential.token) if str(row.get("session_id") or "") == session_id]
            out(f"[audit] 本次会话留下 {len(rows)} 行审计（不删除，保留为证据）:")
            for row in rows:
                out("[audit]", json.dumps(row, ensure_ascii=False))
        except E2eError as exc:
            out("[audit][warn] 读审计台账失败:", exc)

    if credential is None:
        return
    for pack_id in created_packs:
        try:
            detail = get_pack(credential.token, pack_id)
            if detail is None:
                out(f"[cleanup] 材料包 {pack_id} 已不存在（guarded 删除链路已生效）")
                continue
            subject = str(detail.get("subject") or "")
            if not subject.startswith("E2E-"):
                out(f"[cleanup][warn] 材料包 {pack_id} 标题不是 E2E- 前缀，跳过删除: {subject!r}")
                continue
            delete_pack(credential.token, pack_id)
            out(f"[cleanup] 已删除材料包 {pack_id}")
        except E2eError as exc:
            out(f"[cleanup][warn] 删材料包 {pack_id} 失败:", exc)
    if session_id:
        try:
            delete_session(credential.token, session_id)
            out(f"[cleanup] 已删除会话 {session_id}（审计行按 SET_NULL 保留）")
        except E2eError as exc:
            out("[cleanup][warn] 删会话失败:", exc)


def _make_phases(packs: dict[str, int]) -> list[PhaseSpec]:
    """四段实测 = 四条链路（每条一个自造包，互不影响）。"""
    return [
        PhaseSpec(
            key="judge-approve",
            title="① confirm 同意：judge → done",
            action="ui_material_prep_judge",
            args={"packId": packs["judge-approve"], "target": "done"},
            decide="approve",
            expect_outcome="ok",
            expect_verified=True,
            expect_status="done",
        ),
        PhaseSpec(
            key="judge-deny",
            title="② confirm 拒绝：judge → filed 被拒，包零变化",
            action="ui_material_prep_judge",
            args={"packId": packs["judge-deny"], "target": "filed"},
            decide="deny",
            expect_outcome="denied",
            expect_unchanged=True,
        ),
        PhaseSpec(
            key="delete-confirm",
            title="③ guarded 删除：审批同意 + 本地确认执行 → 包不存在",
            action="ui_material_prep_delete_pack",
            args={"packId": packs["delete-confirm"]},
            decide="guarded-confirm",
            expect_outcome="ok",
            expect_verified=True,
            expect_absent=True,
        ),
        PhaseSpec(
            key="delete-cancel",
            title="④ guarded 删除：审批同意 + 本地取消 → 包还在",
            action="ui_material_prep_delete_pack",
            args={"packId": packs["delete-cancel"]},
            decide="guarded-cancel",
            expect_outcome="aborted",
            expect_unchanged=True,
        ),
    ]


def _create_packs(credential: Credential, stamp: str, created_packs: list[int]) -> dict[str, int]:
    """造四个专用材料包；返回 ``key → pack_id``。

    ``created_packs`` 在**每个包造出来时立刻**追加，不等到函数返回：第三个包上传失败
    时，前两个也必须进清理清单，否则它们会变成无主的 ``E2E-`` 包留在库里。
    """
    suffixes = ("judge-allow", "judge-deny", "delete-allow", "delete-cancel")
    keys = ("judge-approve", "judge-deny", "delete-confirm", "delete-cancel")
    packs: dict[str, int] = {}
    for key, suffix in zip(keys, suffixes, strict=True):
        subject = f"E2E-{stamp}-{uuid.uuid4().hex[:6]}-{suffix}"
        payload = upload_pack(credential.token, subject)
        pack_id = int(payload["id"])
        packs[key] = pack_id
        created_packs.append(pack_id)
        out(f"[setup] 已造材料包 {pack_id} subject={subject}")
    return packs


def main() -> int:
    parser = argparse.ArgumentParser(description="真机自证：UI 动作 confirm / guarded 四链路")
    parser.add_argument(
        "--require",
        action="store_true",
        help="前置服务不全时直接失败（默认 skip 并退出 0，避免 CI 因环境红）",
    )
    args = parser.parse_args()

    services = probe_services()
    for name, port, ready in services:
        out(f"[preflight] {name} :{port} {'up' if ready else 'DOWN'}")
    missing = [f"{name}:{port}" for name, port, ready in services if not ready]
    if missing:
        message = "前置服务未就绪：" + "、".join(missing)
        if args.require:
            out("[fail]", message, "（--require：本地自证必须全通）")
            return 2
        out("[skip]", message, "（按约定 skip，退出 0；本地自证请加 --require）")
        return 0

    if sync_playwright is None:
        out("[skip] 缺 playwright。装法：pip install playwright && playwright install chromium")
        out("       本脚本用后端 venv 里的那份（backend/.venv/bin/python）。")
        return 0

    try:
        credential = resolve_credential()
    except E2eError as exc:
        out("[fail]", exc)
        return 2
    identity = f"用户={credential.username}" if credential.username else "（env 提供的票）"
    out(f"[auth] 身份票来源={credential.source} {identity}")

    session_id = ""
    created_packs: list[int] = []
    try:
        try:
            session_id = create_session(credential.token, f"E2E-ui-action-{int(time.time())}")
            out(f"[setup] 专用会话 {session_id}")
            stamp = time.strftime("%Y%m%d-%H%M%S")
            packs = _create_packs(credential, stamp, created_packs)
        except E2eError as exc:
            out("[fail] 准备阶段失败:", exc)
            return 2

        shot_dir = Path("/tmp") / "fachuan-e2e-shots" / stamp
        try:
            shot_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            out("[fail] 建截图目录失败:", exc)
            return 2
        out(f"[setup] 截图目录 {shot_dir}")

        phases = _make_phases(packs)
        results: list[PhaseResult] = []
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=True)
                except PlaywrightError as exc:
                    out("[skip] Chromium 起不来：", str(exc)[:400])
                    out("       pip install playwright && playwright install chromium")
                    return 2 if args.require else 0
                try:
                    for spec in phases:
                        try:
                            evidence = _run_phase(browser, credential, session_id, spec, spec.args["packId"], shot_dir)
                            detail = (
                                f"审计 outcome={evidence['audit'].get('outcome')} "
                                f"verified={evidence['audit'].get('verified')} "
                                f"decision={evidence['audit'].get('decision')} | "
                                f"包状态 {evidence['before_status'] or '∅'} → {evidence['after_status']}"
                            )
                            results.append(PhaseResult(spec=spec, passed=True, detail=detail))
                            out(f"[{spec.key}] ✅ {spec.title} | {detail}")
                        except PhaseFailure as exc:
                            results.append(PhaseResult(spec=spec, passed=False, detail=str(exc)))
                            out(f"[{spec.key}] ❌ {spec.title} | {exc}")
                            for key, value in exc.diff.items():
                                out(f"    {key}: {json.dumps(value, ensure_ascii=False, default=str)[:2000]}")
                            if exc.infra:
                                out("[abort] 链路本身没走通，剩余阶段不再空等")
                                break
                        except PlaywrightError as exc:
                            detail = f"浏览器操作失败：{exc}"
                            results.append(PhaseResult(spec=spec, passed=False, detail=detail))
                            out(f"[{spec.key}] ❌ {spec.title} | {detail}")
                            out("[abort] 浏览器链路没走通，剩余阶段不再空等")
                            break
                finally:
                    browser.close()
        except PlaywrightError as exc:
            out("[fail] 浏览器链路异常:", str(exc)[:500])
            return 2

        out("")
        out("═══ 四段结果 ═══")
        for result in results:
            mark = "✅" if result.passed else "❌"
            out(f"{mark} {result.spec.key}: {result.detail}")
        executed = len(results)
        passed = sum(1 for result in results if result.passed)
        out(f"合计 {passed}/{executed} 通过（共 4 段）")
        if passed != len(phases):
            return 1
        return 0
    finally:
        _cleanup(credential, session_id, created_packs)


if __name__ == "__main__":
    sys.exit(main())
