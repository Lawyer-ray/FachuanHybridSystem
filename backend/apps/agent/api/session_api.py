"""Agent 会话 API —— 会话 CRUD、消息历史、统计与手动压缩。

端点前缀：``/api/v1/agent``（会话子域）。
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import asdict
from typing import Any

from asgiref.sync import sync_to_async
from ninja import Router
from ninja.errors import HttpError

from apps.core.security.auth import JWTOrSessionAuth

from ..backends import available_kinds as available_backend_kinds
from ..backends import get as get_backend
from ..backends.builtin import ensure_registered
from ..models import AgentSession
from ..pi.rpc_client import PiError
from ..schemas import BackendOptionOut, CompactOut, SessionIn, SessionOut, SessionRenameIn, SessionStatsOut
from ..services.session_service import create_session as create_session_record
from ..services.session_service import delete_session as delete_session_record
from ..services.session_service import get_session as get_session_record
from ..services.session_service import list_sessions as list_session_records
from ..services.session_service import rename_session as rename_session_record
from ..services.stats import latest_run_for_session
from ._helpers import _user_id

logger = logging.getLogger(__name__)

router = Router(tags=["Agent 会话"], auth=JWTOrSessionAuth())


#: kind → 用户可见名的缺省表。不认识的 kind 直接显示 kind 本身（新后端注册后
#: 前端至少不会看到一个空名字），所以这张表只列**需要中文/友好名**的后端。
_BACKEND_LABELS: dict[str, tuple[str, str]] = {
    "pi": ("Pi", "通用 agent 运行时，工具面与技能最全"),
    "dsh": ("DeepSeek Harness", "DeepSeek 官方 harness 运行时"),
}

#: dsh 的 Python SDK 模块名（可用性自检用）。
_DSH_SDK_MODULE = "deepseek_harness"


def _backend_option(
    kind: str,
    capabilities: dict[str, Any],
    *,
    available: bool,
    reason: str,
    models: list[str] | None = None,
) -> BackendOptionOut:
    """按缺省标签表拼一条选项（未登记的 kind 用 kind 自身当名字）。

    ``models`` 是本轮可选的模型清单，``default_model`` 取清单第一项——
    与 ``pool._resolve_model()`` 的回落口径一致（那里也是 ``models[0]``），
    否则 UI 预填的模型和实际不指定时用的模型会对不上。
    """
    label, description = _BACKEND_LABELS.get(kind, (kind, ""))
    model_names = list(models or [])
    return BackendOptionOut(
        kind=kind,
        label=label,
        description=description,
        available=available,
        reason=reason,
        capabilities=capabilities,
        models=model_names,
        default_model=model_names[0] if model_names else None,
    )


def _available_models() -> list[str]:
    """当前平台可选的模型清单（无可用平台 / 无模型时为空列表）。

    复用 ``pi.model_config._provider_models``：模型来源只能有一处定义，否则
    「能不能用」的判断与真正解析出来的模型会漂移（``_no_llm_provider_reason``
    用的是同一份）。同步 ORM，调用方负责 ``sync_to_async``。
    """
    from ..pi.model_config import _load_provider, _provider_models

    provider = _load_provider()
    if provider is None:
        return []
    return _provider_models(provider)


def _no_llm_provider_reason() -> str:
    """LLMProvider 是否可用；不可用时返回面向用户的原因，否则空串。

    同步 ORM，调用方负责用 ``sync_to_async`` 包一层（本端点是 async 的）。
    复用 ``pi.model_config._load_provider`` 而不是自己写一遍查询：模型来源只能
    有一处定义，否则「能不能用」的判断和真正解析出来的模型会漂移。
    """
    from ..pi.model_config import _load_provider, _provider_models

    provider = _load_provider()
    if provider is None:
        return "未配置可用的 LLM 平台（后台需启用至少一个 LLMProvider）"
    if not _provider_models(provider):
        return "LLM 平台未配置默认模型"
    return ""


def _dsh_probe() -> tuple[bool, str]:
    """dsh 后端现在能不能用：SDK 装了 + 有可用 LLMProvider。

    **只做进程内探测，不起 dsh 子进程**：切换器每次打开都会调本端点，为一次
    探测拉起 node 运行时（冷启动秒级）会拖慢整个面板。真正握手/建会话时的失败
    由对话链路报错——这里判的是「大概率能跑」，宁可漏报也不让面板卡住。

    SDK 缺失时不 import 它：``DshBackend`` 注册是延迟的，缺包时 import 会抛。
    """
    if importlib.util.find_spec(_DSH_SDK_MODULE) is None:
        return False, "未安装 DeepSeek Harness SDK（deepseek-harness-sdk）"
    provider_reason = _no_llm_provider_reason()
    if provider_reason:
        return False, provider_reason
    return True, ""


def _models_for_kind(kind: str, models: list[str]) -> list[str]:
    """某个后端实际能用的模型（平台清单按运行时收窄）。

    claude-agent 走 Anthropic Messages 协议，只有模型名含
    :data:`~apps.agent.backends.claude_agent_backend.ANTHROPIC_MODEL_MARKER` 的才能用
    （与它 ``select_anthropic_model`` 的判据同源：小写子串匹配）。把整份平台清单给它，
    前端就能选出「claude-agent + glm53」这种必然失败的组合（实测空正文 / 入口报错）。
    其余后端都走 OpenAI 兼容端点，用整份清单。
    """
    if kind != "claude-agent":
        return list(models)
    # 延迟 import：claude_agent_backend 只在注册了 claude-agent 时才需要
    from ..backends.claude_agent_backend import ANTHROPIC_MODEL_MARKER

    return [name for name in models if ANTHROPIC_MODEL_MARKER in name.lower()]


def _collect_backend_options() -> list[BackendOptionOut]:
    """列出可选后端及其可用性（同步：查注册表 + 查 LLMProvider，全在纯同步路径上）。"""
    ensure_registered()
    registered = available_backend_kinds()
    # 模型清单只查一次：三个后端共用同一份（都落到同一个网关），按 kind 再查
    # 三遍纯属浪费——这个端点每次打开切换器都会被调。
    models = _available_models()
    options: list[BackendOptionOut] = []
    for kind in registered:
        if kind == "dsh":
            available, reason = _dsh_probe()
        else:
            available, reason = True, ""
        options.append(
            _backend_option(
                kind,
                asdict(get_backend(kind).capabilities),
                available=available,
                reason=reason,
                models=_models_for_kind(kind, models),
            )
        )
    # dsh 未注册（缺 SDK / 未接好）时仍列出，置灰并说明原因：直接不出现会让用户
    # 以为「本系统没有这个后端」，而真相是「这里缺东西」——后者是可排查、可修的。
    if "dsh" not in registered:
        options.append(
            _backend_option(
                "dsh",
                {},
                available=False,
                reason="未注册 DshBackend（缺 DeepSeek Harness SDK 或接入未完成）",
                # 未注册 = 现在跑不了，不给模型清单，避免 UI 让用户在一个置灰的
                # 后边选完模型才发现用不了
                models=[],
            )
        )
    # 同理：antigravity 的门槛是「随 wheel 分发的平台二进制」，装不上（非 mac/linux x86/arm
    # 的机器、或 uv lock 没同步）时它连注册都没有。列出来 + 置灰 + 说清缺什么，
    # 比让它从菜单里消失更容易排查。
    if "antigravity" not in registered:
        options.append(
            _backend_option(
                "antigravity",
                {},
                available=False,
                reason="未注册 AntigravityBackend（缺 google-antigravity SDK 或平台无对应 wheel）",
                models=[],
            )
        )
    return options


@router.get("/backends", response=list[BackendOptionOut])
async def list_backends(request: Any) -> list[BackendOptionOut]:
    """列出可用的 agent 后端（前端切换器用）。

    ``available=False`` 的选项要在前端置灰并显示 ``reason``——用户若选了它，
    报错会发生在**建完会话之后**，而 ``agent_kind`` 是会话级属性、不能中途改，
    只能换个后端重开。所以可用性必须能提前问出来。
    未注册的 dsh 也会以置灰条目出现（见 ``_collect_backend_options``）。
    """
    return await sync_to_async(_collect_backend_options, thread_sensitive=True)()


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
