"""JTN 案件选择弹窗（layui）的公共操作与验证。

盖章/归档共用同一「搜索案件」弹窗模式：iframe 内表格勾选 radio → 父页面
layui 层点「选择」回填主页面。历史坑（两次踩中）：查询异步重渲染会清掉已
勾选的 radio；行未勾上时点「选择」，OA 弹「请选择对应的案件信息」且弹窗
保持打开——脚本若不验证就继续，后续表单控件会被弹窗遮罩挡住（cloakbrowser
报 ElementNotReceivingEventsError: element is covered by <DIV>）。

本模块提供：勾选校验（click → 校验 checked → 强制置位 + change 事件）、
「选择」点击、警告层检测与关闭，以及「点选择 → 验证弹窗关闭/处理警告」的
确认循环。弹窗关闭是回填成功的唯一可信信号。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger("apps.oa_filing.case_dialog")

# 勾选目标案件的 radio：已勾选则跳过点击；点击未生效时强制置位并派发
# change 事件（仅 DOM click 可能不触发 OA 的选中状态同步）
_SELECT_RADIO_FN = """(expected) => {
    const radios = document.querySelectorAll('input[type="radio"]');
    for (const radio of radios) {
        const row = radio.closest('tr');
        if (!row) continue;
        const tds = row.querySelectorAll('td');
        if (tds.length < 2) continue;
        const caseNo = tds[1].textContent.trim();
        if (caseNo === expected) {
            if (!radio.checked) radio.click();
            if (!radio.checked) radio.checked = true;
            radio.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
    }
    return false;
}"""

# 「选择」弹窗是否仍打开：以带「选择」按钮的可见 layui 层为准
_IS_DIALOG_OPEN_FN = """() => {
    const layers = document.querySelectorAll(".layui-layer");
    for (const layer of layers) {
        if (layer.style.display === "none") continue;
        for (const a of layer.querySelectorAll("a")) {
            if (a.innerText.trim() === "选择") return true;
        }
    }
    return false;
}"""

# 检测并关闭「请选择对应的案件信息」警告层，命中返回文案
_DISMISS_ALERT_FN = """() => {
    const layers = document.querySelectorAll(".layui-layer");
    for (const layer of layers) {
        if (layer.style.display === "none") continue;
        const text = (layer.innerText || "").trim();
        if (text.includes("请选择对应的案件信息")) {
            for (const a of layer.querySelectorAll("a")) {
                const t = a.innerText.trim();
                if (t === "确定" || t === "关闭") { a.click(); return text; }
            }
        }
    }
    return null;
}"""

_CLICK_CHOOSE_FN = """() => {
    const layers = document.querySelectorAll(".layui-layer");
    for (const layer of layers) {
        for (const a of layer.querySelectorAll("a")) {
            if (a.innerText.trim() === "选择") { a.click(); return true; }
        }
    }
    return false;
}"""


async def select_case_radio_in_frame(frame: Any, case_no: str) -> bool:
    """在弹窗 iframe 当前列表中勾选目标案件的 radio，行存在即返回 True。

    列表来源不区分（初始加载或查询结果）。勾选后校验 checked，未生效则强制
    设置并派发 change 事件，避免「找到了案件却选不中」。
    """
    selected = await frame.evaluate(_SELECT_RADIO_FN, case_no)
    return bool(selected)


async def is_case_dialog_open(page: Any) -> bool:
    """案件选择弹窗（带「选择」按钮的 layui 层）是否仍打开。"""
    return bool(await page.evaluate(_IS_DIALOG_OPEN_FN))


async def dismiss_case_alert(page: Any) -> str | None:
    """检测并关闭「请选择对应的案件信息」警告层，命中返回其文案。"""
    text = await page.evaluate(_DISMISS_ALERT_FN)
    return text if isinstance(text, str) else None


async def confirm_case_selection(
    page: Any,
    case_no: str,
    find_frame: Callable[[Any], Awaitable[Any]],
    *,
    wait_after_click: float,
    max_attempts: int = 3,
) -> None:
    """点「选择」回填并验证弹窗真正关闭，失败重试。

    Args:
        page: 父页面（layui 层所在 DOM）。
        case_no: 目标案件编号（重试重新勾选时用）。
        find_frame: 重新定位弹窗 iframe 的异步回调（重试前表格可能已重渲染）。
        wait_after_click: 点击「选择」后的等待秒数（与调用方既有节奏一致）。
        max_attempts: 最大尝试次数。

    Raises:
        RuntimeError: 重试耗尽后弹窗仍未关闭（回填失败）。
    """
    for attempt in range(1, max_attempts + 1):
        if await is_case_dialog_open(page):
            await page.evaluate(_CLICK_CHOOSE_FN)
            await asyncio.sleep(wait_after_click)

        alert = await dismiss_case_alert(page)
        if alert is not None:
            logger.warning("OA 提示「%s」，重新勾选案件后重试（第 %d/%d 次）", alert, attempt, max_attempts)
            frame = await find_frame(page)
            if frame is None or not await select_case_radio_in_frame(frame, case_no):
                raise RuntimeError(f"重试勾选案件失败: {case_no}")
            continue

        if not await is_case_dialog_open(page):
            return
        logger.warning("案件选择弹窗未关闭，重试（第 %d/%d 次）", attempt, max_attempts)

    raise RuntimeError("案件选择弹窗回填失败：多次尝试后仍未关闭（详见上方警告日志）")
