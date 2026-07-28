"""EMS 查询流程 — 状态机驱动。

重构自原线性流程，借鉴 Chrome 插件 (songda-chrome-extension) 的状态机模式：
- 6 种页面状态，每种状态有独立的超时和处理策略
- 每阶段有 StageTracker 追踪，错误时报告具体阶段
- AbortFlag 支持协作式取消
- 选择器从 selectors_config 加载，EMS 改版时只需改配置
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Final

from .browser_utils import (
    AbortFlag,
    StageTracker,
    click_first,
    click_first_non_disabled,
    detect_page_state,
    ensure_query_page,
    fill_first,
    has_any_text,
    has_any_visible,
    native_fill,
)
from .selectors_config import get_ems_selectors, get_ems_text, get_ems_timeouts

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("apps.express_query")

EMS_HOME_URL: Final[str] = "https://www.11183.com.cn/"
EMS_QUERY_URL: Final[str] = "https://www.11183.com.cn/?to=%2Fquery_express_delivery"


async def query_ems(
    page: Page,
    tracking_number: str,
    *,
    abort: AbortFlag | None = None,
    tracker: StageTracker | None = None,
) -> None:
    """EMS 查询主流程 — 状态机驱动。

    借鉴 Chrome 插件 waitUntilResultReady 的状态轮询模式：
    1. 进入页面 → 状态轮询
    2. 每种状态有独立处理逻辑和超时
    3. 支持中途取消（abort）
    """
    _abort = abort or AbortFlag()
    _tracker = tracker or StageTracker(tracking_number=tracking_number)
    timeouts = get_ems_timeouts()

    overall_deadline = asyncio.get_running_loop().time() + timeouts.get("overall", 600)
    login_deadline = timeouts.get("login", 300)
    captcha_deadline = timeouts.get("captcha", 300)
    result_deadline = timeouts.get("result", 240)
    page_load_timeout = timeouts.get("pageLoad", 90)
    poll_interval = timeouts.get("poll", 1.2)
    renavigate_after = timeouts.get("renavigateAfterUnknown", 15)

    clean_query_url = "https://www.11183.com.cn/query_express_delivery"

    # 阶段1: 进入页面
    _tracker.set("opening")
    await page.goto(EMS_QUERY_URL, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await asyncio.sleep(2)

    # 状态机轮询
    last_state = ""
    state_since = asyncio.get_running_loop().time()
    fill_attempts = 0
    renavigates = 0

    while True:
        _abort.check()

        # 总超时
        if asyncio.get_running_loop().time() > overall_deadline:
            raise TimeoutError(
                _tracker.error_message(f"EMS 查询总时长超时（{int(timeouts.get('overall', 600) / 60)} 分钟）")
            )

        # 检测并处理登录后重定向
        if await ensure_query_page(page, clean_query_url):
            last_state = ""
            state_since = asyncio.get_running_loop().time()
            fill_attempts = 0
            await asyncio.sleep(1)
            continue

        # 检测当前状态
        state = await detect_page_state(page, tracking_number=tracking_number)

        if state != last_state:
            last_state = state
            state_since = asyncio.get_running_loop().time()
        elapsed = asyncio.get_running_loop().time() - state_since

        logger.info("[EMS] state=%s, elapsed=%.1fs, fill_attempts=%d", state, elapsed, fill_attempts)

        # ── 状态分派 ────────────────────────────────────────

        if state == "resultReady":
            _tracker.set("resultReady")
            logger.info("[EMS] 物流信息已出现，准备打开详情页")
            return

        if state == "notFound":
            raise RuntimeError(_tracker.error_message(f"EMS 未查询到该单号：{tracking_number}"))

        if state == "loginRequired":
            _tracker.set("login")
            if elapsed > login_deadline:
                raise TimeoutError(_tracker.error_message(f"等待 EMS 登录超时（{int(login_deadline)} 秒）"))
            # 尝试点击登录按钮
            await _try_click_login(page)
            logger.info("[EMS] 等待用户登录... (%.0fs remaining)", login_deadline - elapsed)

        elif state == "captcha":
            _tracker.set("captcha")
            if elapsed > captcha_deadline:
                raise TimeoutError(_tracker.error_message(f"等待验证码完成超时（{int(captcha_deadline)} 秒）"))
            logger.info("[EMS] 检测到验证码，等待完成... (%.0fs remaining)", captcha_deadline - elapsed)

        elif state == "waitingResult":
            _tracker.set("waitingResult")
            if elapsed > result_deadline:
                raise TimeoutError(
                    _tracker.error_message(f"等待物流信息超时（{int(result_deadline)} 秒），请确认已完成验证")
                )
            logger.info("[EMS] 等待物流信息... (%.0fs remaining)", result_deadline - elapsed)

        elif state == "needFill":
            _tracker.set("fill")
            if fill_attempts >= 3:
                raise RuntimeError(_tracker.error_message("自动填写单号失败（已尝试 3 次），请检查输入框选择器配置"))
            if fill_attempts == 0 or elapsed > 8:
                fill_attempts += 1
                logger.info("[EMS] 正在填入单号 %s（第 %d 次）", tracking_number, fill_attempts)
                await _fill_and_submit(page, tracking_number)
                state_since = asyncio.get_running_loop().time()

        else:
            # unknown / loading
            _tracker.set("loading")
            if elapsed > renavigate_after and renavigates < 2:
                renavigates += 1
                logger.info("[EMS] 页面状态暂未识别，正在重新打开查询页...")
                await page.goto(EMS_QUERY_URL, wait_until="domcontentloaded")
                state_since = asyncio.get_running_loop().time()
            elif elapsed > page_load_timeout:
                raise TimeoutError(
                    _tracker.error_message(f"页面加载超时（{int(page_load_timeout)} 秒），未识别到查询区域")
                )

        await asyncio.sleep(poll_interval)

    # 如果循环正常结束（不应该到达这里），进入详情页
    _tracker.set("detail")
    await _open_ems_waybill_detail(page, tracking_number, _tracker)


async def _try_click_login(page: Page) -> bool:  # pragma: no cover
    """尝试点击登录按钮。"""
    login_entries = get_ems_selectors("loginEntryButtons")
    return await click_first(page, login_entries)


async def _fill_and_submit(page: Page, tracking_number: str) -> None:  # pragma: no cover
    """填入单号并点击查询。"""
    input_selectors = get_ems_selectors("trackingInputs")
    submit_selectors = get_ems_selectors("submitButtons")

    # 使用增强版 native_fill（fill 失败时 fallback 到逐字符输入）
    try:
        await native_fill(page, input_selectors, tracking_number)
    except Exception as e:
        logger.warning("[EMS] native_fill failed: %s", e)
        return

    await asyncio.sleep(0.5)

    # 点击查询按钮
    if not await click_first(page, submit_selectors):
        await page.keyboard.press("Enter")
    await asyncio.sleep(1)


async def _dismiss_ems_overlays(page: Page) -> None:  # pragma: no cover
    """关闭 EMS 弹窗（从配置加载选择器）。"""
    dismiss_selectors = get_ems_selectors("dismissOverlayButtons")

    for _ in range(5):
        closed_any = False

        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
        except Exception:
            pass

        for selector in dismiss_selectors:
            if await click_first(page, [selector]):
                closed_any = True

        # JS 兜底：关闭大弹窗
        try:
            clicked = await page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('body *'));
                for (const el of elements) {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    if (style.position === 'fixed' && Number(style.zIndex || '0') >= 100
                        && rect.width >= 300 && rect.height >= 200) {
                        const x = rect.right - 18;
                        const y = rect.top + 18;
                        const target = document.elementFromPoint(x, y);
                        if (target instanceof HTMLElement) { target.click(); return true; }
                    }
                }
                return false;
            }""")
            if clicked:
                closed_any = True
        except Exception:
            pass

        if not closed_any:
            break


async def _open_ems_waybill_detail(
    page: Page,
    tracking_number: str,
    tracker: StageTracker,
) -> None:  # pragma: no cover
    """EMS 打开详情 + 展开全部轨迹。"""
    tracker.set("detail")
    logger.info("[EMS] Opening detail for: %s", tracking_number)

    detail_selectors = get_ems_selectors("detailButtons")
    result_selectors = get_ems_selectors("resultContainers")

    deadline = asyncio.get_running_loop().time() + 45
    detail_entered = False

    while asyncio.get_running_loop().time() < deadline:
        await _dismiss_ems_overlays(page)

        # 点击运单号文本
        try:
            await click_first(page, [f"text={tracking_number}"])
        except Exception:
            pass

        # DOM 搜索点击详情按钮
        try:
            clicked = await page.evaluate(
                """(trackingNumber) => {
                    const target = String(trackingNumber).replace(/\\s+/g, '');
                    const els = Array.from(document.querySelectorAll('body *'));
                    for (const el of els) {
                        const text = String(el.innerText || '').replace(/\\s+/g, '');
                        if (!text || !text.includes(target)) continue;
                        let container = el;
                        for (let d = 0; d < 6 && container; d++) {
                            const btn = Array.from(container.querySelectorAll('button,a,span,div')).find(n => {
                                const t = String(n.innerText || '').trim();
                                return /查看详情|详情|物流详情|邮件详情|收寄详情/.test(t);
                            });
                            if (btn instanceof HTMLElement) { btn.click(); return true; }
                            container = container.parentElement;
                        }
                    }
                    return false;
                }""",
                tracking_number,
            )
            if clicked:
                detail_entered = True
                await asyncio.sleep(2)
        except Exception:
            pass

        if not detail_entered:
            if await click_first(page, detail_selectors):
                detail_entered = True
                await asyncio.sleep(2)

        # 确认进入详情页
        if detail_entered:
            if await has_any_visible(page, result_selectors):
                logger.info("[EMS] Detail page confirmed")
                break
        await asyncio.sleep(1)

    if not detail_entered:
        raise RuntimeError(tracker.error_message(f"EMS 详情页打开失败：{tracking_number}"))

    # 展开全部物流轨迹
    tracker.set("expand")
    await _ems_expand_all_tracking(page)


async def _ems_expand_all_tracking(page: Page) -> None:  # pragma: no cover
    """展开全部物流轨迹（从配置加载选择器）。"""
    expand_selectors = get_ems_selectors("expandButtons")
    expand_text = get_ems_text("expandKeywords")

    expanded_any = True
    max_rounds = 5

    for round_num in range(max_rounds):
        if not expanded_any and round_num > 0:
            break

        expanded_any = False

        # CSS 选择器 + 文本匹配
        for selector in expand_selectors:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                for idx in range(min(count, 3)):
                    target = locator.nth(idx)
                    try:
                        if await target.is_visible() and not await target.is_disabled():
                            await target.scroll_into_view_if_needed()
                            await target.click(force=True, timeout=2000)
                            expanded_any = True
                            await asyncio.sleep(1)
                    except Exception:
                        continue
            except Exception:
                continue

        # JS 兜底
        try:
            js_clicked = await page.evaluate(
                """(keywords) => {
                const els = Array.from(document.querySelectorAll(
                    'button, span, div, a, [role="button"]'
                ));
                for (const el of els) {
                    const t = (el.innerText || '').trim();
                    if (t.length > 20) continue;
                    if (!keywords.some(kw => t.includes(kw))) continue;
                    if (el.getBoundingClientRect().width === 0) continue;
                    if (el.disabled) continue;
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
                return false;
            }""",
                expand_text,
            )
            if js_clicked:
                expanded_any = True
                await asyncio.sleep(1)
        except Exception:
            pass

        await asyncio.sleep(1)

    # 滚动到底部确保加载
    try:
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
    except Exception:
        pass

    logger.info("[EMS] Tracking expansion complete")
