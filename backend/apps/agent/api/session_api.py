"""Agent 会话 API —— 会话 CRUD、消息历史、统计与手动压缩。

端点前缀：``/api/v1/agent``（会话子域）。
"""

from __future__ import annotations

import logging
from typing import Any

from ninja import Router
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..backends import available_kinds as available_backend_kinds
from ..models import AgentSession
from ..pi.rpc_client import PiError
from ..schemas import CompactOut, SessionIn, SessionOut, SessionRenameIn, SessionStatsOut
from ..services.session_service import create_session as create_session_record
from ..services.session_service import delete_session as delete_session_record
from ..services.session_service import get_session as get_session_record
from ..services.session_service import list_sessions as list_session_records
from ..services.session_service import rename_session as rename_session_record
from ..services.stats import latest_run_for_session
from ._helpers import _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 会话"], auth=JWTOrSessionAuth())


def _to_out(session: AgentSession) -> SessionOut:
    return SessionOut(
        session_id=str(session.session_id),
        title=session.title,
        status=session.status,
        llm_model=session.llm_model,
        # 历史会话无此字段值时兜底 `pi`，与引入 agent_kind 之前的行为一致
        agent_kind=getattr(session, "agent_kind", "") or "pi",
        origin=session.origin,
        case_id=session.case_id,
        contract_id=session.contract_id,
        task_state=session.task_state,
        task_id=session.task_id,
        task_error=session.task_error,
        task_finished_at=session.task_finished_at.isoformat() if session.task_finished_at else "",
        # annotate_scope_names 透传属性；未注水的单会话端点 getattr 兜底空串
        scope_name=getattr(session, "scope_name", "") or "",
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
    )


@router.post("/sessions", response=SessionOut)
async def create_session(request: Any, payload: SessionIn) -> SessionOut:  # pragma: no cover
    """新建会话。

    ``agent_kind`` 未注册时直接拒绝（HttpError 400），**不静默回退到 pi**：
    用户以为换了后端而实际没换，比直接报错难发现得多——会先归因于
    「新模型效果不行」，白白浪费一轮调试。
    空串仍允许（旧客户端不传），走模型默认值 `pi`。
    """
    agent_kind = (payload.agent_kind or "").strip() or "pi"
    if agent_kind not in available_backend_kinds():
        raise HttpError(
            400,
            f"未注册的 agent 后端：{agent_kind}；可选：{', '.join(available_backend_kinds())}",
        )
    session = await create_session_record(
        title=payload.title,
        user_id=_user_id(request),
        origin=payload.origin,
        case_id=payload.case_id,
        contract_id=payload.contract_id,
        agent_kind=agent_kind,
    )
    return _to_out(session)


@router.get("/sessions", response=list[SessionOut])
async def list_sessions(  # pragma: no cover
    request: Any,
    limit: int = 50,
    origin: str | None = None,
    case_id: int | None = None,
    contract_id: int | None = None,
) -> list[SessionOut]:
    """列出当前用户的会话。

    可按入口（origin）与案件 / 合同过滤。归属始终按当前用户过滤——
    ``case_id`` 只用于缩小范围，不能借它看到别人的会话。
    """
    sessions = await list_session_records(
        user_id=_user_id(request),
        limit=limit,
        origin=origin,
        case_id=case_id,
        contract_id=contract_id,
    )
    return [_to_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response=SessionOut)
async def get_session_detail(request: Any, session_id: str) -> SessionOut:  # pragma: no cover
    """会话详情（不归属当前用户时同样 404，不泄露存在性）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


@router.delete("/sessions/{session_id}")
async def delete_session(request: Any, session_id: str) -> dict[str, Any]:  # pragma: no cover
    """删除会话（级联删除消息与审批）。"""
    deleted = await delete_session_record(session_id=session_id, user_id=_user_id(request))
    return {"deleted": deleted}


@router.patch("/sessions/{session_id}", response=SessionOut)
async def update_session_title(
    request: Any, session_id: str, payload: SessionRenameIn
) -> SessionOut:  # pragma: no cover
    """重命名会话（侧边栏会话列表的改名入口）。"""
    if not payload.title.strip():
        raise HttpError(400, "标题不能为空")
    session = await rename_session_record(
        session_id=session_id,
        user_id=_user_id(request),
        title=payload.title,
    )
    if session is None:
        raise HttpError(404, "会话不存在")
    return _to_out(session)


@router.get("/sessions/{session_id}/stats", response=SessionStatsOut)
async def get_session_stats(request: Any, session_id: str) -> SessionStatsOut:  # pragma: no cover
    """会话 token 用量与上下文水位（读库即可，不起 pi 进程）。"""
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    latest = await latest_run_for_session(session)
    if latest is None:
        return SessionStatsOut(output_tokens=0, input_tokens=0, cache_read_tokens=0, cache_write_tokens=0)
    percent: float | None = None
    if latest.context_used_tokens is not None and latest.context_total_tokens:
        percent = round(latest.context_used_tokens / latest.context_total_tokens * 100, 1)
    return SessionStatsOut(
        output_tokens=latest.output_tokens,
        input_tokens=latest.input_tokens,
        cache_read_tokens=latest.cache_read_tokens,
        cache_write_tokens=latest.cache_write_tokens,
        context_used_tokens=latest.context_used_tokens,
        context_total_tokens=latest.context_total_tokens,
        context_percent=percent,
    )


@router.post("/sessions/{session_id}/compact", response=CompactOut)
async def compact_session_context(request: Any, session_id: str) -> CompactOut:  # pragma: no cover
    """手动压缩会话上下文（同步执行：起 pi 续写 session 文件，压缩完才返回）。

    摘要与自动压缩同源（``compaction-takeover`` 确定性编译，保案号/当事人/
    金额/期限锚点）。进程池忙时 429，pi 故障 502——都不吞。
    """
    session = await get_session_record(session_id=session_id, user_id=_user_id(request))
    if session is None:
        raise HttpError(404, "会话不存在")
    # 懒加载：测试经 compact_service 模块属性打桩 compact_session，
    # 顶层具名导入会在 import 时绑死真实函数，使桩静默失效。
    from ..services.compact_service import CompactBusyError, CompactNotNeededError, compact_session

    try:
        return CompactOut(**await compact_session(session=session, user_id=_user_id(request)))
    except CompactNotNeededError:
        return CompactOut(compacted=False)
    except CompactBusyError as exc:
        raise HttpError(429, str(exc)) from exc
    except PiError as exc:
        logger.error("手动压缩失败 session=%s: %s", session_id, exc)
        raise HttpError(502, "压缩失败，请稍后再试（详见服务端日志）") from exc
