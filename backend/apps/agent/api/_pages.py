"""附件/文件夹引用分页渲染端点的共享参数校验与结果装配。

``/attachments/{id}/pages`` 与 ``/folder-refs/pages`` 两个端点同构（三段状态：
参数非法 400 / 无权或不存在 404 / 渲染失败 200 + error 错误码），参数校验与
RenderResult → schema 的翻译集中在这里，避免两处逐字重复。
"""

from __future__ import annotations

import base64
import re
from typing import Any

from ninja.errors import HttpError

from ..schemas import AttachmentPageOut, AttachmentPagesOut

#: 页面图 dpi 钳制区间：低于 72 字迹糊成色块，高于 300 单页就几十 MB base64
_PAGES_DPI_MIN = 72
_PAGES_DPI_MAX = 300
_PAGES_DPI_DEFAULT = 150
#: 单次最多取几页（上限即默认值）：一张页面图进模型上下文要几百到上千 token，
#: 放开会让一次调用吃满上下文
_PAGES_MAX_PAGES = 10
#: 单个页范围 token：``3`` 或 ``1-3``（与 T1 parse_pages 的接受面一致）
_PAGES_TOKEN_RE = re.compile(r"^\d+(-\d+)?$")


def _reject_unsyntactic_pages(spec: str) -> None:
    """只挡「不是合法页范围语法」的入参（越界不在这里判，交给渲染门面）。

    允许的形态与 T1 ``parse_pages`` 对齐：``all`` / ``3`` / ``1-3`` / ``1,3,5``。
    """
    raw = (spec or "").strip().lower()
    if raw == "all":
        return
    tokens = [piece.strip() for piece in raw.replace("，", ",").split(",")]
    tokens = [piece for piece in tokens if piece]
    if not tokens or not all(_PAGES_TOKEN_RE.match(piece) for piece in tokens):
        raise HttpError(400, f"pages 不合法：{spec!r}（示例：1-3 / 7 / all）")


def _parse_max_pages(raw: str) -> int:
    """``max_pages`` 钳到 [1, 10]；非数字直接 400（不静默当成默认值）。

    静默回落会让调用方以为「要了 20 页却只给了 10 页是文档问题」——实际是
    参数写错。这里宁可报错。
    """
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, f"max_pages 须为整数，收到：{raw!r}") from exc
    return max(1, min(value, _PAGES_MAX_PAGES))


def _parse_dpi(raw: str) -> int:
    """``dpi`` 钳到 [72, 300]；非数字 400。

    越界只钳不报错：调用方要的是能看的图，把 600 压到 300 比报错更有用。
    """
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HttpError(400, f"dpi 须为整数，收到：{raw!r}") from exc
    return max(_PAGES_DPI_MIN, min(value, _PAGES_DPI_MAX))


def _parse_page_params(*, pages: str, dpi: str, format: str, max_pages: str) -> tuple[str, int, str, int]:
    """校验并归一化分页参数，返回 ``(pages_spec, dpi, fmt, max_pages)``。

    语法错误在进渲染前就挡成 400：门面把 ValueError（语法错与越界）统一折成
    page_out_of_range 的 200 响应，调用方会误以为「页码写对了但文档没这些页」，
    实际是参数本身不合语法——这两种情况的下一步动作完全不同。越界仍交给
    门面返回 page_out_of_range（需要真实页数才知道）。
    """
    fmt = (format or "png").strip().lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg"):
        raise HttpError(400, f"format 仅支持 png / jpeg，收到：{format!r}")
    requested_dpi = _parse_dpi(dpi)
    requested_max = _parse_max_pages(max_pages)
    pages_spec = (pages or "").strip()
    if not pages_spec:
        raise HttpError(400, "pages 不能为空（示例：1-3 / 7 / all）")
    _reject_unsyntactic_pages(pages_spec)
    return pages_spec, requested_dpi, fmt, requested_max


def _strategy_value(strategy: Any) -> str:
    """``RenderStrategy`` → 字符串值（``StrEnum`` 的 value；普通字符串原样返回）。"""
    value = getattr(strategy, "value", strategy)
    return str(value)


def _error_code(error: Any) -> str:
    """RenderError（StrEnum）→ 错误码字符串；成功时为 ""。"""
    if error is None:
        return ""
    return str(getattr(error, "value", error))


def _to_page_out(page: Any) -> AttachmentPageOut:
    """T1 的 RenderedPage → 对外页图 schema（字段名翻译集中在这里，别散落到调用点）。

    ``has_text_layer`` 在 T1 里没有独立字段：它的判定口径就是「文字层够长，
    走文本策略」，所以 ``strategy is TEXT`` 或 ``text`` 非空即视为有文字层。
    """
    strategy_is_text = _strategy_value(page.strategy) == "text"
    image_bytes = page.image_bytes or b""
    return AttachmentPageOut(
        page=int(page.page_no),
        mime=str(page.mime or ""),
        # 二进制 → base64 只在这一处做；空字节绝不编码成「看起来正常」的空串
        b64=base64.b64encode(image_bytes).decode("ascii") if image_bytes else "",
        bytes=len(image_bytes),
        width=int(page.width),
        height=int(page.height),
        has_text_layer=strategy_is_text or bool((page.text or "").strip()),
        # 文字层页不出图（b64 为空），但**必须把文字带出去**：
        # 否则调用方只知道「这页有文字」却拿不到文字——解析服务一旦转异步
        # 就会卡成「有字但读不到」，实测踩到过（扫描件/正常 PDF 都会中）。
        text=str(page.text or "") if strategy_is_text or (page.text or "").strip() else "",
        error=_error_code(page.error),
        detail=str(page.detail or ""),
    )


def _summarize_strategy(pages: list[Any]) -> str:
    """整次结果的形态汇总：全 text / 全 image / mixed（MCP 据此决定要不要走视觉通道）。"""
    kinds = {_strategy_value(page.strategy) for page in pages}
    if not kinds:
        return ""
    if kinds <= {"text"}:
        return "text"
    if kinds <= {"page_image", "source_image"}:
        return "image"
    return "mixed"


def _build_notices(outcome: Any, *, requested_max: int) -> list[str]:
    """把「被截断 / 整份失败」这类必须让调用方知道的事写进 notices。

    截断一定要说：静默少给页会让模型把「后面那些页不存在」当成文档事实。
    """
    notices: list[str] = []
    if outcome.truncated_pages > 0:
        notices.append(
            f"超过 max_pages={requested_max} 限制，还有 {outcome.truncated_pages} 页未渲染（可用 pages 参数分段取）"
        )
    if outcome.error is not None and outcome.detail:
        notices.append(f"{_error_code(outcome.error)}：{outcome.detail}")
    return notices


def _pages_out(outcome: Any, *, requested_max: int) -> AttachmentPagesOut:
    """RenderResult → 对外分页 schema（两个端点共用同一装配口径）。"""
    return AttachmentPagesOut(
        attachment_id=outcome.attachment_id,
        filename=outcome.filename,
        mime=outcome.mime,
        total_pages=outcome.total_pages,
        pages_returned=[_to_page_out(page) for page in outcome.pages],
        strategy=_summarize_strategy(outcome.pages),
        error=_error_code(outcome.error),
        detail=outcome.detail,
        notices=_build_notices(outcome, requested_max=requested_max),
        truncated_pages=outcome.truncated_pages > 0,
    )
