"""综合结论的引用核验 —— 把 `Synthesis.unverified` 真正填上。

## 为什么必须有这一步

综合 agent 的 prompt 要求"只使用候选里出现过的法条与案号"，但它**验不了候选本身
对不对**。不核验时 `unverified` 恒为空——前端 `SynthesisCard` 的「未核验」区块永远
不出现，等于对律师说"都核过了"。

## 核验走哪条路

复用既有威科链路（`LawVerificationService.check_references`）：凭证解密、E-13 域名
白名单、登录与插件探测都在那一层，**不重写**。它在 app 层，不需要经过 MCP。

## 不占全局同步线程

`check_references` 是同步阻塞的（威科登录 + HTTP/Playwright IO），一次可能几分钟。
放进 `sync_to_async(thread_sensitive=True)` 等于占住全进程唯一的同步线程，期间所有
同样走它的同步 ORM 都得排队。所以这里改用专用线程池（:data:`_VERIFY_EXECUTOR`），
线程里用完数据库连接就关掉（连接按线程持有，不关会随线程池常驻而泄漏）。

## 失败一律降级为"未核验"，不阻断综合

综合稿本身有价值，核验不了不该把它一起丢掉。三种降级都在 `note` 里说清：

- 本所没有威科凭证 → 「只做了格式检查」；
- 插件没装 / 凭证无权限 / 威科登录失败 → 「核验未执行：<原因>」；
- 核验跑了但有条目没兜住 → 逐条进 `unverified`（这才是正常产出）。

**取消不是失败**：`asyncio.CancelledError` 原样上抛（见 `control_flow.MUST_PROPAGATE`）。
取消只能停止「等待」，线程里正在跑的威科调用无法中途打断，会自然结束、结果丢弃。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from asgiref.sync import sync_to_async
from django.db import connections

from apps.agent.services.chat.citation_check import extract_statute_refs
from apps.legal_research.services.credential_resolver import resolve_weike_credential_id

from .control_flow import MUST_PROPAGATE

logger = logging.getLogger(__name__)

#: 核验线程名前缀（日志与测试据此确认核验没跑在 asgiref 的全局同步线程里）。
VERIFY_THREAD_PREFIX = "weike-verify"

#: 同时在跑的威科核验上限。每个都是一次登录 + 核查，多了只会被威科限流。
VERIFY_MAX_WORKERS = 4

#: 专用线程池：模块级常驻（不随 ``asyncio.run`` 的默认线程池一起被等待关闭——
#: 取消后不必等那次威科调用跑完才能收尾）。
_VERIFY_EXECUTOR = ThreadPoolExecutor(max_workers=VERIFY_MAX_WORKERS, thread_name_prefix=VERIFY_THREAD_PREFIX)

#: 后端返回的"这条法规没问题"取值（插件侧约定，见 law_verification_service）。
_VALID_STATUSES = frozenset({"valid", "ok"})
#: 失效类取值：命中即算未核验（哪怕 status 写着 valid）。
_INVALID_VALIDITY = frozenset({"invalid", "repealed", "abolished"})


def _describe(item: dict[str, Any]) -> str:
    """一条核验结果 → 给人看的一句话（进 `unverified`）。"""
    name = str(item.get("law_name") or "").strip() or "（未识别法规）"
    article = item.get("article_num")
    label = f"《{name}》" if name and not name.startswith("《") else name
    if article:
        label = f"{label}第 {article} 条"
    status = str(item.get("status") or "").strip() or "unknown"
    validity = str(item.get("validity") or "").strip()
    detail = f"状态 {status}" + (f" / 效力 {validity}" if validity else "")
    return f"{label}：{detail}"


def _is_verified(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    validity = str(item.get("validity") or "").lower()
    return status in _VALID_STATUSES and validity not in _INVALID_VALIDITY


def _call_and_close_db(func: Callable[..., Any], kwargs: dict[str, Any]) -> Any:
    """在核验线程里执行 ``func``，结束时关闭**本线程**的数据库连接。"""
    try:
        return func(**kwargs)
    finally:
        connections.close_all()


async def _run_in_verify_thread(func: Callable[..., Any], **kwargs: Any) -> Any:
    """把一次同步阻塞调用交给专用线程池，不占 asgiref 的全局同步线程。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_VERIFY_EXECUTOR, _call_and_close_db, func, kwargs)


async def verify_synthesis_citations(
    *,
    text: str,
    credential_id: int | None,
    user: Any,
) -> tuple[list[str], str]:
    """核验综合稿里的法规引用。

    Returns:
        ``(unverified, note)``：``unverified`` 是**未核验条目的中文描述**（直接进
        `Synthesis.unverified`）；``note`` 是本次覆盖口径（`""` = 全量核验且全通过）。

    Raises:
        asyncio.CancelledError: 本次综合被取消（不当成核验失败）。
    """
    body = str(text or "").strip()
    if not body:
        return [], "空正文，未核验"

    # 凭证**自己找**：credential_id 是实现细节（一张表里混着法院/OA/工商/邮箱/威科），
    # 不该让律师或模型去猜 6 和 7 有什么区别。解析口径见 credential_resolver。
    # 这是一次短查询，留在 thread_sensitive 线程里没有排队代价。
    resolved_id = await sync_to_async(resolve_weike_credential_id, thread_sensitive=True)(
        user=user, explicit=credential_id
    )
    if not resolved_id:
        # 不是失败：没有威科账号就是"没查"。写成"未配置"而不是"未通过核验"，
        # 否则律师会以为查过了且有问题。
        return [], "本所未配置威科先行账号凭证，本次只做了格式检查，未做外部核验"

    from apps.legal_research.services.law_verification_service import LawVerificationService

    service = LawVerificationService()
    try:
        payload = await _run_in_verify_thread(
            service.check_references, text=body, credential_id=int(resolved_id), user=user
        )
    except MUST_PROPAGATE:
        raise
    except BaseException as exc:
        # 核验失败**不阻断综合**：稿子本身有价值，只是这一批引用没核到。失败面太杂
        # （插件缺失 / 凭证无权限 / 登录失败 / 网络），逐类接只会漏，所以宽口径接住；
        # 取消与进程退出已在上一条 except 放行。异常类型进日志，不进用户文案。
        logger.warning("综合稿引用核验失败（不阻断）", exc_info=True)
        return [], f"核验未执行：{type(exc).__name__}"

    references = payload.get("references") if isinstance(payload, dict) else None
    if not references:
        # **防静默假绿**：后端返回空有两种可能——
        #   (a) 文末确实没有法规引用；
        #   (b) 抽取器没认出来（实测过：旧正则不认「第 874 条」的写法，
        #       整篇综合稿一条都抽不到，被当成"没有引用"，unverified 空着 = 假通过）。
        # 用本地抽取器交叉验证：本地抽到而核验没返回，就必须如实告诉律师"没核成"。
        local = extract_statute_refs(body)
        if local:
            logger.warning("核验返回 0 条，但本地抽出 %d 条引用，按未核验处理", len(local))
            return [f"《{ref.law_name}》未核验（核验服务未返回该条结果）" for ref in local], (
                f"抽出 {len(local)} 条引用，但核验未返回结果；请人工核对"
            )
        return [], "核验已执行，但文末未识别到法规引用"

    unverified = [_describe(item) for item in references if not _is_verified(item)]
    if not unverified:
        return [], ""
    return unverified, f"核验已执行：{len(unverified)} 条未通过"


__all__ = ["VERIFY_THREAD_PREFIX", "verify_synthesis_citations"]
