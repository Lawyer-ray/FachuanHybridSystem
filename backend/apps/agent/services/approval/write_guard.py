"""写端点兜底（入口 C）—— agent 在多栏会话里调 REST 写端点，一律 409。

## 为什么 REST 层还要拦一道

多栏并答的写降级已有两道闸门，但两道都以**工具名**为判据，各有覆盖缺口：

- 工具面（pi 的 ``--exclude-tools``，见 ``services/chat/multi.py``）只对 pi 生效；
- 审批层（``policy.multi_lane_write_refusal``）只拦 ``MULTI_LANE_WRITE_TOOLS``
  里的名字——名字漏登记、或调用根本没经过 MCP 工具面（例如将来新增的写工具），
  都会静默放行。

真正落盘的只有 REST 端点。所以在这里按**会话**兜底：请求带
``X-Fachuan-Session``（= 调用方是 agent）且该会话正在多栏并答 → 409，文案
直接告诉模型改用 ``propose_write_patch`` 出草案，而不是只说「不行」。

## 判定只在「agent + 多栏」时成立

- **无会话头 → 一律放行**。律师在页面上点出来的动作（生成材料、应用 patch、
  保存到目录）没有会话头；一刀切会把律师自己的按钮打穿。
- **有会话头但查不到多栏登记 → 放行**（单栏 / 该轮多栏已收尾 / 缓存不可用）。
  口径与 ``policy.is_multi_lane_session`` 完全一致（那里已经把「查不到按单栏」
  写死，这里不另立一套）。

## 为什么是 409

这不是「没权限」：同一身份、单栏时同一个请求是合法的。它是「当前状态不允许
这样写」——409 + 可自纠文案让模型换路径，而不是以为工具坏了。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from asgiref.sync import sync_to_async

from apps.core.exceptions import ConflictError

from .policy import MULTI_LANE_WRITE_REFUSAL, is_multi_lane_session

logger = logging.getLogger(__name__)

#: agent 会话标识请求头。与 ``mcp_server/identity.py::SESSION_HEADER`` 同名同义：
#: 共享 MCP 把入站请求的会话标识原样透传给 REST（``mcp_server/client.py::_headers``）。
SESSION_HEADER = "x-fachuan-session"

#: 拒绝的错误码。前端与 MCP 侧据此把「多栏拒写」同其它 409（孤立冲突 / mtime
#: 失效）区分开。
MULTI_LANE_WRITE_CODE = "MULTI_LANE_WRITE_REFUSED"


def request_session_id(request: Any) -> str:
    """请求携带的 agent 会话标识；律师在页面手动操作时为空串。

    **只认字符串**：测试里常拿 ``MagicMock`` 当 request，``headers.get`` 会返回
    一个真值 Mock；若把它当会话 id 去查缓存，全仓库测试就会变成随机拒写。
    """
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    raw = headers.get(SESSION_HEADER)
    return raw.strip() if isinstance(raw, str) else ""


def multi_lane_session_of(session_ids: Iterable[str | None]) -> str | None:
    """返回第一个处于多栏并答的会话 id（没有 → ``None``）。

    多个候选的场景只有 patch 应用：请求头带的是「当前会话」，patch 行带的是
    「产出它的会话」，两者都要判。
    """
    for session_id in session_ids:
        if not isinstance(session_id, str):
            continue
        clean = session_id.strip()
        if clean and is_multi_lane_session(clean):
            return clean
    return None


def ensure_write_not_multi_lane(*, endpoint: str, session_ids: Iterable[str | None]) -> None:
    """任一候选会话处于多栏 → ``ConflictError``（409）；否则静默返回。

    同步版本，供同步端点（如 ``doc_converter`` 的 save-to-dir）与 async 包装层调用。
    ``endpoint`` 只进 ``errors`` 与日志，用于定位是哪个写端点拒的。
    """
    blocked = multi_lane_session_of(session_ids)
    if blocked is None:
        return
    logger.warning("多栏会话写端点拒绝 endpoint=%s session=%s", endpoint, blocked)
    raise ConflictError(
        message=MULTI_LANE_WRITE_REFUSAL,
        code=MULTI_LANE_WRITE_CODE,
        errors={"endpoint": endpoint, "session_id": blocked},
    )


async def ensure_request_not_multi_lane(request: Any, *, endpoint: str, session_ids: Iterable[str | None] = ()) -> None:
    """async 端点入口：请求头 + 端点自带的会话 id 一起判，多栏 → 409。

    没有任何候选会话（律师手动操作）时直接返回，连线程切换都不做。
    """
    candidates = [request_session_id(request), *session_ids]
    if not any(isinstance(session_id, str) and session_id.strip() for session_id in candidates):
        return
    # 缓存读在同步栈里（与 policy 同口径）：async 端点不能直接阻塞事件循环
    await sync_to_async(ensure_write_not_multi_lane, thread_sensitive=True)(endpoint=endpoint, session_ids=candidates)
